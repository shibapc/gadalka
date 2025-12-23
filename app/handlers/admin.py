from typing import List, Dict

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest

from app.config import settings
from app.keyboards.main import main_menu_keyboard
from app.logger import get_logger
from app.storage import storage
from app.services.booking import get_service_by_id


admin_router = Router()
log = get_logger(__name__)


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
    pay_map = {"pending": "неоплачено", "awaiting_review": "ожидает проверки", "paid": "оплачено"}
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
    urgent = "срочно" if item.get("is_urgent") else "обычно"
    contact_text = f"@{contact}" if username else contact
    phone = item.get("phone") or "—"
    return (
        f"#{item.get('position')} – {item.get('name')} / ДР: {item.get('birth_date')} / услуга: {item.get('service_id')} ({urgent} {price_text})\n"
        f"Оплата: {pay} | Сеанс: {sess} | Чек: {'да' if item.get('payment_proof') else 'нет'} | Контакт: {contact_text} | Телефон: {phone}"
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


# --- Инлайн UI ---
PAGE_SIZE = 5


def build_filter_buttons(current: str, service_id: str | None) -> List[List[InlineKeyboardButton]]:
    service_code = service_id or "all"
    row1 = [
        ("paid", "✅ Оплачено"),
        ("done", "✔️ Проведено"),
        ("notdone", "❌ Не проведено"),
    ]
    row2 = [
        ("all", "Все"),
        ("arch", "Архив"),
    ]

    def btn(code: str, label: str) -> InlineKeyboardButton:
        prefix = "☑️ " if code == current else ""
        return InlineKeyboardButton(text=prefix + label, callback_data=f"adm:list:{code}:{service_code}:1")

    return [
        [btn(code, label) for code, label in row1],
        [btn(code, label) for code, label in row2],
    ]


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
    return items


def build_list_view(filter_key: str, page: int, service_id: str | None) -> tuple[str, InlineKeyboardMarkup]:
    items = load_items(filter_key, service_id)
    total = len(items)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    chunk = items[start:end]
    titles = {"all": "Все", "paid": "Оплачено", "done": "Проведено", "notdone": "Не проведено", "arch": "Архив"}
    lines = [f"Фильтр: {titles.get(filter_key, filter_key)}, страница {page}, всего {total}"]
    if service_id:
        lines.append(f"Раздел: {service_label(service_id)}")
    if filter_key == "arch":
        total_orders, total_sum = storage.history_stats(service_id=service_id)
        lines.append(f"Статистика: всего заказов {total_orders}, сумма {total_sum}₽")
    if not chunk:
        lines.append("Записей нет.")
    else:
        sess_map = {"pending": "не проведён", "done": "проведён"}
        for item in chunk:
            sess = sess_map.get(item.get("session_status"), item.get("session_status"))
            if filter_key == "arch":
                lines.append(f"#{item.get('archive_id')} – {item.get('name')} ({sess})")
            else:
                lines.append(f"#{item.get('position')} – {item.get('name')} ({sess})")
    kb_rows = []
    service_code = service_id or "all"
    for item in chunk:
        if filter_key != "arch":
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"#{item.get('position')} ▶️",
                        callback_data=f"adm:item:{filter_key}:{service_code}:{item.get('position')}",
                    )
                ]
            )
    # Навигация
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:list:{filter_key}:{service_code}:{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:list:{filter_key}:{service_code}:{page+1}"))
    if nav:
        kb_rows.append(nav)
    # Фильтры
    kb_rows.extend(build_filter_buttons(filter_key, service_id))
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb_rows)


def build_item_actions(
    item: Dict,
    super_admin: bool,
    has_proof: bool,
    filter_key: str,
    service_id: str | None,
) -> InlineKeyboardMarkup:
    pos = item.get("position")
    service_code = service_id or "all"
    rows = []
    if super_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if item.get("session_status") == "done" else "⬜ ") + "Сеанс проведён",
                    callback_data=f"adm:session:{pos}:done",
                ),
                InlineKeyboardButton(
                    text=("✅ " if item.get("session_status") != "done" else "⬜ ") + "Сеанс не проведён",
                    callback_data=f"adm:session:{pos}:pending",
                ),
            ]
        )
        rows.append([InlineKeyboardButton(text="Удалить в архив", callback_data=f"adm:delete:{service_code}:{pos}")])
    rows.append([InlineKeyboardButton(text="⬅️ К списку", callback_data=f"adm:list:{filter_key}:{service_code}:1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@admin_router.message(Command("admin"))
async def handle_admin_root(message: Message) -> None:
    user_id = message.from_user.id
    if not is_moderator(user_id):
        await message.answer("Нет доступа.")
        return
    await message.answer(build_admin_menu(is_super_admin(user_id)), parse_mode=None)
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
        await message.answer(f"Заявка #{pos} архивирована и удалена из очереди. Позиции пересчитаны.", parse_mode=None)
    else:
        await message.answer("Позиция не найдена", parse_mode=None)


@admin_router.message(Command("admin_history"))
async def handle_admin_history(message: Message) -> None:
    if not is_moderator(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await send_service_select(message, "arch")


@admin_router.callback_query(F.data == "adm:clear_history")
async def cb_clear_history(callback: CallbackQuery) -> None:
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    storage.clear_history()
    await callback.message.edit_text("Архив очищен.", parse_mode=None)
    await callback.answer("Очищено")


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
        await message.answer(f"Оплата для #{pos} установлена: paid")
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
        await message.answer(f"Оплата для #{pos} установлена: pending")
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
        await message.answer(f"Сеанс для #{pos} установлен: done")
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
        await message.answer(f"Сеанс для #{pos} установлен: pending")
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
    pay_map = {"pending": "неоплачено", "awaiting_review": "ожидает проверки", "paid": "оплачено"}
    sess_map = {"pending": "не проведён", "done": "проведён"}
    pay = pay_map.get(item.get("payment_status"), item.get("payment_status"))
    sess = sess_map.get(item.get("session_status"), item.get("session_status"))
    price = item.get("price")
    if price is None:
        service = get_service_by_id(item.get("service_id", "")) or {}
        price = service.get("price", 2500)
    price_text = f"{price}₽"
    urgent = "срочно" if item.get("is_urgent") else "обычно"
    lines = [
        f"Заявка #{item.get('position')}",
        f"Имя: {item.get('name')}",
        f"ДР: {item.get('birth_date')}",
        f"Услуга: {item.get('service_id')} ({urgent} {price_text})",
        f"Оплата: {pay}",
        f"Сеанс: {sess}",
        f"Чек: {'да' if item.get('payment_proof') else 'нет'}",
        f"Интуитивная цифра: {split_express_problem(item.get('problem'))[0] or '—'}",
        f"Описание: {split_express_problem(item.get('problem'))[1] or '—'}",
        f"Создано: {item.get('created_at')}",
        f"Контакт: {contact_text}",
        f"Телефон: {phone}",
    ]
    kb = build_item_actions(
        item,
        is_super_admin(callback.from_user.id),
        bool(item.get("payment_proof")),
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


@admin_router.callback_query(F.data.startswith("adm:proof:"))
async def cb_admin_proof(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, pos_str = callback.data.split(":", 2)
    pos = int(pos_str)
    item = storage.get_by_position(pos)
    proof = item.get("payment_proof") if item else None
    if not proof:
        await callback.answer("Чека нет", show_alert=True)
        return
    file_id = proof.get("file_id") if isinstance(proof, dict) else None
    ftype = proof.get("type") if isinstance(proof, dict) else "unknown"
    if not file_id:
        await callback.answer("Чека нет", show_alert=True)
        return
    if ftype == "photo":
        await callback.message.answer_photo(photo=file_id, caption=f"Чек по заявке #{pos}")
    else:
        await callback.message.answer_document(document=file_id, caption=f"Чек по заявке #{pos}")
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:architem:"))
async def cb_admin_architem(callback: CallbackQuery) -> None:
    # архивные элементы не раскрываем
    await callback.answer("Просмотр архивной заявки отключен", show_alert=True)
