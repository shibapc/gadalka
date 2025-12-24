from typing import Dict, List

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest

from app.config import settings
from app.keyboards.main import main_menu_keyboard
from app.handlers.booking import get_session
from app.logger import get_logger
from app.storage import storage
from app.services.booking import get_service_by_id


admin_router = Router()
log = get_logger(__name__)
admin_send_targets: Dict[int, Dict[str, int | str]] = {}


def is_super_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


def is_moderator(user_id: int) -> bool:
    return user_id in settings.MODERATOR_IDS or is_super_admin(user_id)


def service_label(service_id: str) -> str:
    label_map = {"consult": "Гадание", "express": "Экспресс-расклад"}
    if service_id in label_map:
        return label_map[service_id]
    service = get_service_by_id(service_id) or {}
    return service.get("title") or service_id


def split_express_problem(problem: str | None) -> tuple[str | None, str | None]:
    if not problem:
        return None, None
    prefix = "Интуитивная цифра: "
    if problem.startswith(prefix):
        rest = problem[len(prefix):]
        if "\nЗапрос: " in rest:
            number_part, text_part = rest.split("\nЗапрос: ", 1)
            return number_part.strip() or None, text_part.strip() or None
    return None, problem


def format_entry(item: dict) -> str:
    pay_map = {"pending": "неоплачено", "paid": "оплачено"}
    sess_map = {"pending": "не проведён", "done": "проведён"}
    pay = pay_map.get(item.get("payment_status"), item.get("payment_status"))
    sess = sess_map.get(item.get("session_status"), item.get("session_status"))
    username = item.get("user_username")
    contact = username or item.get("user_fullname") or f"id:{item.get('user_id')}"
    price = item.get("price")
    if price is None:
        service = get_service_by_id(item.get("service_id", "")) or {}
        price = service.get("price", 2500)
    price_text = f"{price}₽"
    urgent = "срочно" if item.get("is_urgent") else ""
    contact_text = f"@{contact}" if username else contact
    phone = item.get("phone") or "—"
    return (
        f"№{item.get('position')} – {item.get('name')} / ДР: {item.get('birth_date')} / услуга: {item.get('service_id')} ({urgent} {price_text})\n"
        f"Оплата: {pay} | Сеанс: {sess} | Контакт: {contact_text} | Телефон: {phone}"
    )


def admin_summary(limit: int = 20) -> str:
    items = storage.list_all()
    if not items:
        return "Очередь пуста."
    lines = ["Очередь (последние):"]
    for item in items[:limit]:
        lines.append(format_entry(item))
    if len(items) > limit:
        lines.append(f"... всего {len(items)} записей")
    return "\n".join(lines)


def build_admin_menu(super_admin: bool) -> str:
    if super_admin:
        return (
            "Админ-меню (высший уровень):\n"
            "- /admin_done <позиция> –отметить сеанс проведённым\n"
            "- /admin_undone <позиция> –вернуть сеанс в pending\n"
            "- /admin_show –показать очередь\n"
            "- /admin_paid –оплаченные\n"
            "- /admin_send <позиция> –отправить расклад по экспресс-заявке\n"
            "- /admin_send_cancel –отменить отправку расклада\n"
            "- /admin_delete <позиция> –удалить/архивировать (позиции сдвигаются)\n"
            "- /admin_history –показать архив (последние)\n"
            "Инлайн-меню: /admin (кнопки фильтров/пагинации/действий)\n"
        )
    return "Модератор: доступен просмотр очереди через /admin_show, /admin_paid, /admin_history и инлайн-меню /admin."


def build_service_select_keyboard(filter_key: str = "all") -> InlineKeyboardMarkup:
    rows = []
    for service in settings.SERVICES:
        label = service_label(service["id"])
        rows.append([InlineKeyboardButton(text=label, callback_data=f"adm:service:{service['id']}:{filter_key}")])
    rows.append([InlineKeyboardButton(text="📊 Статистика продаж", callback_data="adm:stats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_service_select(message: Message, filter_key: str) -> None:
    await message.answer("Выберите раздел:", reply_markup=build_service_select_keyboard(filter_key), parse_mode=None)


def parse_list_callback(data: str) -> tuple[str, str | None, int]:
    parts = data.split(":")
    if len(parts) == 4:
        _, _, filter_key, page_str = parts
        service_id = None
    else:
        _, _, filter_key, service_id, page_str = parts
        if service_id == "all":
            service_id = None
    return filter_key, service_id, int(page_str)


def parse_item_callback(data: str) -> tuple[str, str | None, int]:
    parts = data.split(":")
    if len(parts) == 4:
        _, _, filter_key, pos_str = parts
        service_id = None
    else:
        _, _, filter_key, service_id, pos_str = parts
        if service_id == "all":
            service_id = None
    return filter_key, service_id, int(pos_str)


def start_send_to_user(
    admin_id: int,
    user_id: int,
    position: int,
    service_id: str,
    name: str | None,
    birth_date: str | None,
    order_created_at: str | None,
) -> None:
    admin_send_targets[admin_id] = {
        "user_id": user_id,
        "position": position,
        "service_id": service_id,
        "name": name or "",
        "birth_date": birth_date or "",
        "order_created_at": order_created_at or "",
        "order_id": None,
    }


# --- Инлайн UI ---
PAGE_SIZE = 5


def build_filter_buttons(current: str, service_id: str | None) -> List[List[InlineKeyboardButton]]:
    if current in ("reviews", "arch"):
        return []
    service_code = service_id or "all"
    items = [
        ("all", "Все"),
        ("done", "✅ Проведено"),
        ("notdone", "❌ Не проведено"),
        ("arch", "🗑 Архив"),
        ("reviews", "💬 Отзывы"),
    ]

    def btn(code: str, label: str) -> InlineKeyboardButton:
        prefix = "✓ " if code == current else ""
        return InlineKeyboardButton(text=prefix + label, callback_data=f"adm:list:{code}:{service_code}:1")

    return [[btn(code, label)] for code, label in items]


def load_items(filter_key: str, service_id: str | None) -> List[Dict]:
    if filter_key == "paid":
        items = storage.list_by_payment_status(["paid"])
    elif filter_key == "done":
        items = [item for item in storage.list_all() if item.get("session_status") == "done"]
    elif filter_key == "notdone":
        items = [item for item in storage.list_all() if item.get("session_status") != "done"]
    elif filter_key == "arch":
        items = storage.list_history(limit=100)
    else:
        items = storage.list_all()
    if service_id:
        items = [item for item in items if item.get("service_id") == service_id]
    if filter_key != "arch":
        items = [item for item in items if item.get("payment_status") == "paid"]
    return items


def build_list_view(filter_key: str, page: int, service_id: str | None) -> tuple[str, InlineKeyboardMarkup]:
    if filter_key == "stats":
        total_orders, total_sum = storage.history_stats()
        lines = [
            "Статистика продаж",
            f"Всего заказов: {total_orders}",
            f"Сумма: {total_sum}₽",
        ]
        kb_rows = [[InlineKeyboardButton(text="⬅️ В меню", callback_data="adm:menu:all")]]
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb_rows)

    if filter_key == "reviews":
        live_items = storage.list_all()
        arch_items = storage.list_history(limit=1000)
        if service_id:
            live_items = [item for item in live_items if item.get("service_id") == service_id]
            arch_items = [item for item in arch_items if item.get("service_id") == service_id]
        items = []
        for item in live_items:
            items.append({"kind": "live", "item": item, "created_at": item.get("created_at", "")})
        for item in arch_items:
            items.append({"kind": "arch", "item": item, "created_at": item.get("created_at", "")})
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    else:
        items = load_items(filter_key, service_id)
    total = len(items)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    chunk = items[start:end]
    titles = {
        "all": "Все",
        "paid": "Оплачено",
        "done": "Проведено",
        "notdone": "Не проведено",
        "arch": "Архив",
        "reviews": "Отзывы",
        "stats": "Статистика",
    }
    if filter_key == "reviews":
        lines = [f"Отзывы (страница {page}). Выбери отзыв:"]
    else:
        lines = [f"Фильтр: {titles.get(filter_key, filter_key)}, страница {page}, всего {total}"]
    if service_id:
        lines.append(f"Раздел: {service_label(service_id)}")
    if not chunk:
        lines.append("Записей нет.")
    else:
        if filter_key == "reviews":
            pass
        else:
            sess_map = {"pending": "не проведён", "done": "проведён"}
            for item in chunk:
                sess = sess_map.get(item.get("session_status"), item.get("session_status"))
                if filter_key == "arch":
                    lines.append(f"№{item.get('archive_id')} – {item.get('name')} ({sess})")
                else:
                    lines.append(f"№{item.get('position')} – {item.get('name')} ({sess})")
    kb_rows = []
    service_code = service_id or "all"
    for idx, item in enumerate(chunk):
        if filter_key == "reviews":
            order = item["item"]
            name = order.get("name") or order.get("user_fullname") or f"id:{order.get('user_id')}"
            birth_date = order.get("birth_date") or "—"
            review = storage.get_review_for_order(order.get("order_id"))
            mark = "✅" if review else "❌"
            order_no = total - (start + idx)
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"№{order_no} {name} | {birth_date} {mark}",
                        callback_data=f"adm:review:{service_code}:{order.get('order_id')}",
                    )
                ]
            )
        elif filter_key not in ("arch", "reviews"):
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"№{item.get('position')}",
                        callback_data=f"adm:item:{filter_key}:{service_code}:{item.get('position')}",
                    )
                ]
            )
    # Фильтры
    kb_rows.extend(build_filter_buttons(filter_key, service_id))
    # Навигация
    if start > 0:
        kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm:list:{filter_key}:{service_code}:{page-1}")])
    if end < total:
        kb_rows.append([InlineKeyboardButton(text="➡️ Далее", callback_data=f"adm:list:{filter_key}:{service_code}:{page+1}")])
    kb_rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="adm:menu:all")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb_rows)


def build_item_actions(
    item: Dict,
    super_admin: bool,
    filter_key: str,
    service_id: str | None,
) -> InlineKeyboardMarkup:
    pos = item.get("position")
    service_code = service_id or "all"
    rows = []
    if super_admin:
        sess_done = item.get("session_status") == "done"
        if item.get("result_sent") and item.get("order_id"):
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📨 Посмотреть расклад",
                        callback_data=f"adm:result:{item.get('order_id')}",
                    )
                ]
            )
        elif item.get("service_id") == "express" and item.get("payment_status") == "paid":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📨 Отправить расклад",
                        callback_data=f"adm:send:{service_code}:{pos}",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if sess_done else "") + "Сеанс проведён",
                    callback_data=f"adm:session:{pos}:done",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if not sess_done else "") + "Сеанс не проведён",
                    callback_data=f"adm:session:{pos}:pending",
                )
            ]
        )
        rows.append([InlineKeyboardButton(text="🗑 Удалить в архив", callback_data=f"adm:delete:{service_code}:{pos}")])
    rows.append([InlineKeyboardButton(text="⬅️ К списку", callback_data=f"adm:list:{filter_key}:{service_code}:1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@admin_router.message(Command("admin"))
async def handle_admin_root(message: Message) -> None:
    user_id = message.from_user.id
    if not is_moderator(user_id):
        await message.answer("Нет доступа.")
        return
    await send_service_select(message, "all")


@admin_router.message(Command("admin_show"))
async def handle_admin_show(message: Message) -> None:
    user_id = message.from_user.id
    if not is_moderator(user_id):
        await message.answer("Нет доступа.")
        return
    await send_service_select(message, "all")


def parse_position(args: str) -> int | None:
    try:
        return int(args.strip())
    except Exception:
        return None


@admin_router.message(Command("admin_paid"))
async def handle_admin_paid(message: Message) -> None:
    if not is_moderator(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await send_service_select(message, "paid")


@admin_router.message(Command("admin_send"))
async def handle_admin_send(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not (pos := parse_position(args[1])):
        await message.answer("Укажите позицию: /admin_send <номер>")
        return
    item = storage.get_by_position(pos)
    if not item or item.get("service_id") != "express":
        await message.answer("Заявка не найдена или не относится к экспресс-раскладу.")
        return
    if item.get("payment_status") != "paid":
        await message.answer("Нельзя отправить расклад до оплаты.")
        return
    start_send_to_user(
        message.from_user.id,
        item.get("user_id"),
        pos,
        item.get("service_id"),
        item.get("name"),
        item.get("birth_date"),
        item.get("created_at"),
    )
    admin_send_targets[message.from_user.id]["order_id"] = item.get("order_id")
    await message.answer(
        "Отправьте текст/фото/документ пользователю. Для отмены: /admin_send_cancel",
    )


@admin_router.message(Command("admin_delete"))
async def handle_admin_delete(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not (pos := parse_position(args[1])):
        await message.answer("Укажите позицию: /admin_delete <номер>")
        return
    if storage.delete_and_archive(pos):
        await message.answer(f"Заявка №{pos} архивирована и удалена из очереди. Позиции пересчитаны.")
    else:
        await message.answer("Позиция не найдена")


@admin_router.message(Command("admin_history"))
async def handle_admin_history(message: Message) -> None:
    if not is_moderator(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await send_service_select(message, "arch")


@admin_router.message(Command("admin_send_cancel"))
async def handle_admin_send_cancel(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    if admin_send_targets.pop(message.from_user.id, None):
        await message.answer("Отправка отменена.")
    else:
        await message.answer("Нет активной отправки.")


@admin_router.callback_query(F.data == "adm:clear_history")
async def cb_clear_history(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, очистить", callback_data="adm:clear_history_confirm")],
            [InlineKeyboardButton(text="Нет, назад", callback_data="adm:clear_history_cancel")],
        ]
    )
    await callback.message.answer(
        "Очистить архив? Это действие нельзя отменить.",
        reply_markup=kb,
    )
    await callback.answer()


@admin_router.callback_query(F.data == "adm:clear_history_confirm")
async def cb_clear_history_confirm(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    storage.clear_history()
    await callback.message.edit_text("Архив очищен.")
    await callback.answer("Очищено")


@admin_router.callback_query(F.data == "adm:clear_history_cancel")
async def cb_clear_history_cancel(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Очистка архива отменена.")
    await callback.answer("Отменено")


@admin_router.message(Command("admin_pay"))
async def handle_admin_pay(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not (pos := parse_position(args[1])):
        await message.answer("Укажите позицию: /admin_pay <номер>")
        return
    if storage.update_payment_status(pos, "paid"):
        log.info("Payment marked paid by %s for position %s", message.from_user.id, pos)
        await message.answer(f"Оплата для №{pos} установлена: paid")
    else:
        await message.answer("Позиция не найдена")


@admin_router.message(Command("admin_unpay"))
async def handle_admin_unpay(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not (pos := parse_position(args[1])):
        await message.answer("Укажите позицию: /admin_unpay <номер>")
        return
    if storage.update_payment_status(pos, "pending"):
        log.info("Payment marked pending by %s for position %s", message.from_user.id, pos)
        await message.answer(f"Оплата для №{pos} установлена: pending")
    else:
        await message.answer("Позиция не найдена")


@admin_router.message(Command("admin_done"))
async def handle_admin_done(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not (pos := parse_position(args[1])):
        await message.answer("Укажите позицию: /admin_done <номер>")
        return
    if storage.update_session_status(pos, "done"):
        log.info("Session marked done by %s for position %s", message.from_user.id, pos)
        await message.answer(f"Сеанс для №{pos} установлен: done")
    else:
        await message.answer("Позиция не найдена")


@admin_router.message(Command("admin_undone"))
async def handle_admin_undone(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not (pos := parse_position(args[1])):
        await message.answer("Укажите позицию: /admin_undone <номер>")
        return
    if storage.update_session_status(pos, "pending"):
        log.info("Session marked pending by %s for position %s", message.from_user.id, pos)
        await message.answer(f"Сеанс для №{pos} установлен: pending")
    else:
        await message.answer("Позиция не найдена")


# --- Callback-based UI ---
@admin_router.callback_query(F.data.startswith("adm:service:"))
async def cb_admin_service(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, service_id, filter_key = callback.data.split(":", 3)
    text, kb = build_list_view(filter_key, 1, service_id)
    if filter_key == "arch":
        kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Очистить архив", callback_data="adm:clear_history")])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=None)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=kb, parse_mode=None)
    await callback.answer()


@admin_router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    text, kb = build_list_view("stats", 1, None)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=None)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=kb, parse_mode=None)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:menu:"))
async def cb_admin_menu(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await send_service_select(callback.message, "all")
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:send:"))
async def cb_admin_send(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":", 3)
    if len(parts) == 3:
        _, _, pos_str = parts
    else:
        _, _, _, pos_str = parts
    pos = int(pos_str)
    item = storage.get_by_position(pos)
    if not item or item.get("service_id") != "express":
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if item.get("payment_status") != "paid":
        await callback.answer("Сначала нужна оплата", show_alert=True)
        return
    start_send_to_user(
        callback.from_user.id,
        item.get("user_id"),
        pos,
        item.get("service_id"),
        item.get("name"),
        item.get("birth_date"),
        item.get("created_at"),
    )
    admin_send_targets[callback.from_user.id]["order_id"] = item.get("order_id")
    await callback.message.answer(
        "Отправьте текст/фото/документ пользователю. Для отмены: /admin_send_cancel",
        parse_mode=None,
    )
    await callback.answer("Готово")


@admin_router.callback_query(F.data.startswith("adm:review:"))
async def cb_admin_review(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":", 3)
    if len(parts) == 3:
        _, _, order_str = parts
        service_id = None
    else:
        _, _, service_id, order_str = parts
        if service_id == "all":
            service_id = None
    order_id = int(order_str)
    item = storage.get_by_order_id(order_id) or storage.get_history_by_order_id(order_id)
    if not item:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    name = item.get("name") or item.get("user_fullname") or f"id:{item.get('user_id')}"
    birth_date = item.get("birth_date") or "—"
    review = storage.get_review_for_order(item.get("order_id"))
    if review:
        created = review.get("created_at") or "—"
        text = review.get("text") or "—"
    else:
        created = item.get("review_skipped_at") or "—"
        text = "—"
    header = f"Отзыв по заявке №{order_id}\nФИО: {name}\nДР: {birth_date}\nДата: {created}\n\nОтзыв:\n{text}"
    service_code = service_id or "all"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="К отзывам", callback_data=f"adm:list:reviews:{service_code}:1")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="adm:menu:all")],
        ]
    )
    await callback.message.edit_text(header, reply_markup=kb, parse_mode=None)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:result:"))
async def cb_admin_result(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, order_str = callback.data.split(":", 2)
    order_id = int(order_str)
    item = storage.get_by_order_id(order_id) or storage.get_history_by_order_id(order_id)
    if not item:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    payload = item.get("result_payload") if isinstance(item, dict) else None
    if not isinstance(payload, dict):
        await callback.answer("Расклад не найден", show_alert=True)
        return
    ptype = payload.get("type")
    if ptype == "photo" and payload.get("file_id"):
        await callback.message.answer_photo(
            photo=payload["file_id"],
            caption=payload.get("caption") or f"Расклад по заявке №{order_id}",
        )
    elif ptype == "document" and payload.get("file_id"):
        await callback.message.answer_document(
            document=payload["file_id"],
            caption=payload.get("caption") or f"Расклад по заявке №{order_id}",
        )
    elif ptype == "text":
        text = payload.get("text") or "—"
        await callback.message.answer(f"Расклад по заявке №{order_id}:\n\n{text}", parse_mode=None)
    else:
        await callback.answer("Расклад не найден", show_alert=True)
        return
    await callback.answer("Отправлено")


@admin_router.callback_query(F.data.startswith("adm:list:"))
async def cb_admin_list(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    filter_key, service_id, page = parse_list_callback(callback.data)
    text, kb = build_list_view(filter_key, page, service_id)
    if filter_key == "arch":
        kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Очистить архив", callback_data="adm:clear_history")])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=None)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=kb, parse_mode=None)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:item:"))
async def cb_admin_item(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    filter_key, service_id, pos = parse_item_callback(callback.data)
    item = storage.get_by_position(pos)
    if not item:
        await callback.answer("Не найдено", show_alert=True)
        return
    username = item.get("user_username")
    contact_base = username or item.get("user_fullname") or f"id:{item.get('user_id')}"
    contact_text = f"@{contact_base}" if username else contact_base
    phone = item.get("phone") or "—"
    pay_map = {"pending": "неоплачено", "paid": "оплачено"}
    sess_map = {"pending": "не проведён", "done": "проведён"}
    pay = pay_map.get(item.get("payment_status"), item.get("payment_status"))
    sess = sess_map.get(item.get("session_status"), item.get("session_status"))
    price = item.get("price")
    if price is None:
        service = get_service_by_id(item.get("service_id", "")) or {}
        price = service.get("price", 2500)
    price_text = f"{price}₽"
    urgent = "срочно" if item.get("is_urgent") else ""
    lines = [
        f"Заявка №{item.get('position')}",
        f"Имя: {item.get('name')}",
        f"ДР: {item.get('birth_date')}",
        f"Услуга: {item.get('service_id')} ({urgent} {price_text})",
        f"Оплата: {pay}",
        f"Сеанс: {sess}",
        f"Расклад: {'отправлен ✅' if item.get('result_sent') else 'не отправлен ❌'}",
        f"Интуитивная цифра: {split_express_problem(item.get('problem'))[0] or '—'}",
        f"Описание: {split_express_problem(item.get('problem'))[1] or '—'}",
        f"Создано: {item.get('created_at')}",
        f"Контакт: {contact_text}",
        f"Телефон: {phone}",
    ]
    kb = build_item_actions(
        item,
        is_super_admin(callback.from_user.id),
        filter_key,
        service_id,
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=kb, parse_mode=None)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:pay:"))
async def cb_admin_pay(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, pos_str, status = callback.data.split(":", 3)
    pos = int(pos_str)
    if storage.update_payment_status(pos, status):
        await callback.answer("Обновлено")
    else:
        await callback.answer("Не найдено", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm:session:"))
async def cb_admin_session(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, pos_str, status = callback.data.split(":", 3)
    pos = int(pos_str)
    if storage.update_session_status(pos, status):
        item = storage.get_by_position(pos)
        if not item:
            await callback.answer("Не найдено", show_alert=True)
            return
        username = item.get("user_username")
        contact_base = username or item.get("user_fullname") or f"id:{item.get('user_id')}"
        contact_text = f"@{contact_base}" if username else contact_base
        phone = item.get("phone") or "—"
        pay_map = {"pending": "неоплачено", "paid": "оплачено"}
        sess_map = {"pending": "не проведён", "done": "проведён"}
        pay = pay_map.get(item.get("payment_status"), item.get("payment_status"))
        sess = sess_map.get(item.get("session_status"), item.get("session_status"))
        price = item.get("price")
        if price is None:
            service = get_service_by_id(item.get("service_id", "")) or {}
            price = service.get("price", 2500)
        price_text = f"{price}₽"
        urgent = "срочно" if item.get("is_urgent") else ""
        lines = [
            f"Заявка №{item.get('position')}",
            f"Имя: {item.get('name')}",
            f"ДР: {item.get('birth_date')}",
            f"Услуга: {item.get('service_id')} ({urgent} {price_text})",
        f"Оплата: {pay}",
        f"Сеанс: {sess}",
        f"Расклад: {'отправлен ✅' if item.get('result_sent') else 'не отправлен ❌'}",
        f"Интуитивная цифра: {split_express_problem(item.get('problem'))[0] or '—'}",
        f"Описание: {split_express_problem(item.get('problem'))[1] or '—'}",
        f"Создано: {item.get('created_at')}",
        f"Контакт: {contact_text}",
        f"Телефон: {phone}",
        ]
        kb = build_item_actions(item, True, "all", item.get("service_id"))
        await callback.message.answer("\n".join(lines), reply_markup=kb, parse_mode=None)
        await callback.answer("Обновлено")
    else:
        await callback.answer("Не найдено", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm:delete:"))
async def cb_admin_delete(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":", 3)
    if len(parts) == 3:
        _, _, pos_str = parts
        service_id = None
    else:
        _, _, service_id, pos_str = parts
        if service_id == "all":
            service_id = None
    pos = int(pos_str)
    if storage.delete_and_archive(pos):
        text, kb = build_list_view("all", 1, service_id)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=None)
        await callback.answer("Удалено и обновлено")
    else:
        await callback.answer("Не найдено", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm:architem:"))
async def cb_admin_architem(callback: CallbackQuery) -> None:
    # архивные элементы не раскрываем
    await callback.answer("Просмотр архивной заявки отключен", show_alert=True)


@admin_router.message(F.text | F.photo | F.document, lambda message: message.from_user.id in admin_send_targets)
async def handle_admin_send_result(message: Message) -> None:
    if not is_super_admin(message.from_user.id):
        return
    target = admin_send_targets.get(message.from_user.id)
    if message.text and message.text.strip().lower() in ("/admin_send_cancel", "/cancel"):
        admin_send_targets.pop(message.from_user.id, None)
        await message.answer("Отправка отменена.")
        return
    user_id = int(target["user_id"])
    position = int(target["position"])
    service_id = str(target.get("service_id") or "")
    review_name = str(target.get("name") or "")
    review_birth_date = str(target.get("birth_date") or "")
    review_order_created_at = str(target.get("order_created_at") or "")
    review_order_id = target.get("order_id")
    payload = None
    if message.photo:
        file_id = message.photo[-1].file_id
        await message.bot.send_photo(user_id, photo=file_id, caption=message.caption or None)
        payload = {"type": "photo", "file_id": file_id, "caption": message.caption or None}
    elif message.document:
        await message.bot.send_document(user_id, document=message.document.file_id, caption=message.caption or None)
        payload = {"type": "document", "file_id": message.document.file_id, "caption": message.caption or None}
    elif message.text:
        await message.bot.send_message(user_id, message.text)
        payload = {"type": "text", "text": message.text}
    else:
        await message.answer("Отправьте текст, фото или документ.")
        return
    session = get_session(user_id)
    session.step = "review"
    session.service_id = service_id
    session.review_name = review_name or None
    session.review_birth_date = review_birth_date or None
    session.review_order_created_at = review_order_created_at or None
    session.review_order_id = review_order_id if isinstance(review_order_id, int) else None
    if isinstance(review_order_id, int) and payload:
        storage.set_result_sent(review_order_id, payload)
    await message.bot.send_message(
        user_id,
        "Хочешь помочь нам исправить какие-то недостатки или пожелать чего-то нового? "
        "Напиши отзыв (минимум 100 символов).",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Нет, спасибо", callback_data="review_skip")]]
        ),
    )
    admin_send_targets.pop(message.from_user.id, None)
    await message.answer(f"Расклад отправлен пользователю (заявка №{position}).")
