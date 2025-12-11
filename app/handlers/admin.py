from typing import List, Dict

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.keyboards.main import main_menu_keyboard
from app.logger import get_logger
from app.storage import storage


admin_router = Router()
log = get_logger(__name__)


def is_super_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


def is_moderator(user_id: int) -> bool:
    return user_id in settings.MODERATOR_IDS or is_super_admin(user_id)


def format_entry(item: dict) -> str:
    pay_map = {"pending": "неоплачено", "awaiting_review": "ожидает проверки", "paid": "оплачено"}
    sess_map = {"pending": "не проведён", "done": "проведён"}
    pay = pay_map.get(item.get("payment_status"), item.get("payment_status"))
    sess = sess_map.get(item.get("session_status"), item.get("session_status"))
    return (
        f"#{item.get('position')} — {item.get('name')} / ДР: {item.get('birth_date')} / услуга: {item.get('service_id')}\n"
        f"Оплата: {pay} | Сеанс: {sess} | Чек: {'да' if item.get('payment_proof') else 'нет'}"
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
            "- /admin_pay <позиция> — отметить оплату как paid\n"
            "- /admin_unpay <позиция> — вернуть в pending\n"
            "- /admin_done <позиция> — отметить сеанс проведённым\n"
            "- /admin_undone <позиция> — вернуть сеанс в pending\n"
            "- /admin_show — показать очередь\n"
            "- /admin_pending — заявки с чеками, ожидают проверки\n"
            "- /admin_paid — оплаченные\n"
            "- /admin_unconfirmed — без оплаты (pending/awaiting_review)\n"
            "- /admin_delete <позиция> — удалить/архивировать (позиции сдвигаются)\n"
            "- /admin_history — показать архив (последние)\n"
            "Инлайн-меню: /admin (кнопки фильтров/пагинации/действий)\n"
        )
    return "Модератор: доступен просмотр очереди через /admin_show, /admin_pending, /admin_paid, /admin_unconfirmed, /admin_history и инлайн-меню /admin."


# --- Инлайн UI ---
PAGE_SIZE = 5


def build_filter_buttons(current: str) -> List[List[InlineKeyboardButton]]:
    row1 = [
        ("paid", "✅ Оплачено"),
        ("unconf", "⏳ Неоплачено"),
    ]
    row2 = [
        ("all", "Все"),
        ("await", "Чеки"),
        ("arch", "Архив"),
    ]

    def btn(code: str, label: str) -> InlineKeyboardButton:
        prefix = "☑️ " if code == current else ""
        return InlineKeyboardButton(text=prefix + label, callback_data=f"adm:list:{code}:1")

    return [
        [btn(code, label) for code, label in row1],
        [btn(code, label) for code, label in row2],
    ]


def load_items(filter_key: str) -> List[Dict]:
    if filter_key == "paid":
        return storage.list_by_payment_status(["paid"])
    if filter_key == "unconf":
        return storage.list_by_payment_status(["pending", "awaiting_review"])
    if filter_key == "await":
        return [item for item in storage.list_all() if item.get("payment_status") == "awaiting_review"]
    if filter_key == "arch":
        return storage.list_history(limit=100)
    return storage.list_all()


def build_list_view(filter_key: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    items = load_items(filter_key)
    total = len(items)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    chunk = items[start:end]
    titles = {"all": "Все", "paid": "Оплачено", "unconf": "Неоплач.", "await": "Чеки", "arch": "Архив"}
    lines = [f"Фильтр: {titles.get(filter_key, filter_key)}, страница {page}, всего {total}"]
    if not chunk:
        lines.append("Записей нет.")
    else:
        for item in chunk:
            lines.append(format_entry(item))
    kb_rows = []
    for item in chunk:
        kb_rows.append([InlineKeyboardButton(text=f"#{item.get('position')} ▶️", callback_data=f"adm:item:{filter_key}:{item.get('position')}")])
    # Навигация
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:list:{filter_key}:{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:list:{filter_key}:{page+1}"))
    if nav:
        kb_rows.append(nav)
    # Фильтры
    kb_rows.extend(build_filter_buttons(filter_key))
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb_rows)


def build_item_actions(item: Dict, super_admin: bool, has_proof: bool, filter_key: str) -> InlineKeyboardMarkup:
    pos = item.get("position")
    pay_status = item.get("payment_status")
    sess_status = item.get("session_status")
    rows = []
    if super_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if pay_status == "paid" else "⬜ ") + "Оплачено",
                    callback_data=f"adm:pay:{pos}:paid",
                ),
                InlineKeyboardButton(
                    text=("✅ " if pay_status != "paid" else "⬜ ") + "Не опл.",
                    callback_data=f"adm:pay:{pos}:pending",
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if sess_status == "done" else "⬜ ") + "Сеанс ✅",
                    callback_data=f"adm:session:{pos}:done",
                ),
                InlineKeyboardButton(
                    text=("✅ " if sess_status != "done" else "⬜ ") + "Сеанс ⏳",
                    callback_data=f"adm:session:{pos}:pending",
                ),
            ]
        )
        rows.append([InlineKeyboardButton(text="Удалить в архив", callback_data=f"adm:delete:{pos}")])
    if has_proof:
        rows.append([InlineKeyboardButton(text="📎 Показать чек", callback_data=f"adm:proof:{pos}")])
    rows.append([InlineKeyboardButton(text="⬅️ К списку", callback_data=f"adm:list:{filter_key}:1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@admin_router.message(Command("admin"))
async def handle_admin_root(message: Message) -> None:
    user_id = message.from_user.id
    if not is_moderator(user_id):
        await message.answer("Нет доступа.")
        return
    await message.answer(build_admin_menu(is_super_admin(user_id)), parse_mode=None)
    text, kb = build_list_view("all", 1)
    await message.answer(text, reply_markup=kb, parse_mode=None)


@admin_router.message(Command("admin_show"))
async def handle_admin_show(message: Message) -> None:
    user_id = message.from_user.id
    if not is_moderator(user_id):
        await message.answer("Нет доступа.")
        return
    text, kb = build_list_view("all", 1)
    await message.answer(text, reply_markup=kb, parse_mode=None)


def parse_position(args: str) -> int | None:
    try:
        return int(args.strip())
    except Exception:
        return None


@admin_router.message(Command("admin_pending"))
async def handle_admin_pending(message: Message) -> None:
    if not is_moderator(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    text, kb = build_list_view("await", 1)
    await message.answer(text, reply_markup=kb, parse_mode=None)


@admin_router.message(Command("admin_paid"))
async def handle_admin_paid(message: Message) -> None:
    if not is_moderator(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    text, kb = build_list_view("paid", 1)
    await message.answer(text, reply_markup=kb, parse_mode=None)


@admin_router.message(Command("admin_unconfirmed"))
async def handle_admin_unconfirmed(message: Message) -> None:
    if not is_moderator(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    text, kb = build_list_view("unconf", 1)
    await message.answer(text, reply_markup=kb, parse_mode=None)


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
    text, kb = build_list_view("arch", 1)
    await message.answer(text, reply_markup=kb, parse_mode=None)


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
@admin_router.callback_query(F.data.startswith("adm:list:"))
async def cb_admin_list(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, filter_key, page_str = callback.data.split(":", 3)
    page = int(page_str)
    text, kb = build_list_view(filter_key, page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=None)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("adm:item:"))
async def cb_admin_item(callback: CallbackQuery) -> None:
    if not is_moderator(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, filter_key, pos_str = callback.data.split(":", 3)
    pos = int(pos_str)
    item = storage.get_by_position(pos)
    if not item:
        await callback.answer("Не найдено", show_alert=True)
        return
    lines = [
        f"Заявка #{item.get('position')}",
        f"Имя: {item.get('name')}",
        f"ДР: {item.get('birth_date')}",
        f"Услуга: {item.get('service_id')}",
        f"Оплата: {item.get('payment_status')}",
        f"Сеанс: {item.get('session_status')}",
        f"Чек: {'да' if item.get('payment_proof') else 'нет'}",
        f"Создано: {item.get('created_at')}",
    ]
    kb = build_item_actions(item, is_super_admin(callback.from_user.id), bool(item.get("payment_proof")), filter_key)
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
    _, _, pos_str = callback.data.split(":", 2)
    pos = int(pos_str)
    if storage.delete_and_archive(pos):
        text, kb = build_list_view("all", 1)
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
