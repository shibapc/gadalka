from typing import Dict

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.contact import contact_keyboard
from app.keyboards.main import main_menu_keyboard
from app.keyboards.payment import payment_confirm_keyboard
from app.keyboards.priority import priority_keyboard
from app.keyboards.services import services_keyboard
from app.logger import get_logger
from app.models import BookingSession
from app.services.booking import get_service_by_id, get_service_price, now_ekb, validate_birth_date
from app.storage import storage
from app.texts import (
    ask_birth_date_text,
    ask_full_name_text,
    ask_intuitive_number_text,
    ask_name_text,
    ask_problem_brief_text,
    ask_problem_text,
    booking_prompt_text,
    ask_phone_text,
    queue_confirmation_text,
    service_selected_text,
)


booking_router = Router()

user_sessions: Dict[int, BookingSession] = {}
log = get_logger(__name__)


def reset_session(user_id: int) -> BookingSession:
    user_sessions[user_id] = BookingSession()
    return user_sessions[user_id]


def get_session(user_id: int) -> BookingSession:
    return user_sessions.setdefault(user_id, BookingSession())


@booking_router.callback_query(F.data == "start_booking")
async def handle_start_booking(callback: CallbackQuery) -> None:
    session = reset_session(callback.from_user.id)
    await callback.message.edit_text(
        booking_prompt_text(),
        reply_markup=services_keyboard(session.service_id),
        parse_mode=None,
    )
    await callback.answer()


@booking_router.callback_query(F.data.startswith("service:"))
async def handle_service(callback: CallbackQuery) -> None:
    service_id = callback.data.split(":", 1)[1]
    session = get_session(callback.from_user.id)
    session.service_id = service_id
    await callback.message.edit_text(service_selected_text(service_id))
    if service_id == "consult":
        await callback.message.answer("Запись на гадание пока в разработке.", reply_markup=main_menu_keyboard())
        await callback.answer("В разработке")
        return
    if service_id == "express":
        session.is_urgent = False
        session.price = get_service_price(service_id)
        session.step = "birth_date"
        await callback.message.answer(ask_birth_date_text())
        await callback.answer("Услуга выбрана")
        return
    session.step = "priority"
    await callback.message.answer(
        "Выберите тип записи:\n- Обычная — в общей очереди\n- Срочная — в начало очереди (без доплаты)\n",
        reply_markup=priority_keyboard(),
    )
    await callback.answer("Услуга выбрана")


@booking_router.callback_query(F.data.startswith("priority:"))
async def handle_priority(callback: CallbackQuery) -> None:
    choice = callback.data.split(":", 1)[1]
    session = get_session(callback.from_user.id)
    if choice not in ("normal", "urgent"):
        await callback.answer()
        return
    session.is_urgent = choice == "urgent"
    session.price = get_service_price(session.service_id or "")
    session.step = "birth_date"
    await callback.message.answer(ask_birth_date_text())
    await callback.answer("Тип выбран")


@booking_router.message(F.text)
async def handle_steps(message: Message) -> None:
    session = get_session(message.from_user.id)
    if not session.step:
        return

    text = message.text.strip()

    if session.step == "review":
        if len(text) < 100:
            await message.answer("Отзыв должен быть минимум 100 символов. Попробуйте ещё раз.")
            return
        full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name]))
        storage.add_review(
            user_id=message.from_user.id,
            service_id=session.service_id or "",
            text=text,
            user_username=message.from_user.username,
            user_fullname=full_name or None,
            name=session.review_name,
            birth_date=session.review_birth_date,
            order_created_at=session.review_order_created_at,
            order_id=session.review_order_id,
        )
        await message.answer("Спасибо за отзыв!", reply_markup=main_menu_keyboard())
        reset_session(message.from_user.id)
        return

    if session.step == "birth_date":
        ok, parsed = validate_birth_date(text)
        if not ok:
            await message.answer(parsed)
            return
        session.birth_date = parsed
        session.step = "name"
        if session.service_id == "express":
            await message.answer(ask_full_name_text())
        else:
            await message.answer(ask_name_text())
        return

    if session.step == "name":
        session.name = text
        if session.service_id == "express":
            session.step = "intuition_number"
            await message.answer(ask_intuitive_number_text())
        else:
            session.step = "problem"
            await message.answer(ask_problem_text())
        return

    if session.step == "intuition_number":
        try:
            number = int(text)
        except ValueError:
            await message.answer("Введите число от 0 до 22.")
            return
        if number < 0 or number > 22:
            await message.answer("Введите число от 0 до 22.")
            return
        session.intuitive_number = number
        session.step = "problem"
        await message.answer(ask_problem_brief_text())
        return

    if session.step == "problem":
        if session.service_id == "express" and session.intuitive_number is not None:
            session.problem = f"Интуитивная цифра: {session.intuitive_number}\nЗапрос: {text}"
        else:
            session.problem = text
        session.step = "phone"
        await message.answer(ask_phone_text(), reply_markup=contact_keyboard())
        return

    # waiting for payment now handled in payment handler
    return


@booking_router.callback_query(F.data == "review_skip")
async def handle_review_skip(callback: CallbackQuery) -> None:
    session = get_session(callback.from_user.id)
    if session.step != "review":
        await callback.answer()
        return
    if isinstance(session.review_order_id, int):
        storage.set_review_skipped(session.review_order_id)
    reset_session(callback.from_user.id)
    await callback.message.answer("Спасибо! Возвращаю в меню.", reply_markup=main_menu_keyboard())
    await callback.answer()


@booking_router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    session = get_session(message.from_user.id)
    if session.step != "waiting_payment":
        await message.answer("Не удалось связать оплату с заявкой. Начните заново через /start.")
        return
    if not (session.service_id and session.birth_date and session.name and session.problem):
        await message.answer("Не хватает данных для записи. Начните заново через /start.")
        reset_session(message.from_user.id)
        return
    full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name]))
    position = storage.add_request(
        user_id=message.from_user.id,
        service_id=session.service_id,
        birth_date=session.birth_date,
        name=session.name,
        problem=session.problem,
        user_username=message.from_user.username,
        user_fullname=full_name or None,
        is_urgent=session.is_urgent,
        price=session.price or get_service_price(session.service_id or ""),
        phone=session.phone,
        payment_status="paid",
    )
    log.info(
        "Queue added (paid) user=%s service=%s position=%s",
        message.from_user.id,
        session.service_id,
        position,
    )
    await message.answer(queue_confirmation_text(session), reply_markup=main_menu_keyboard())
    reset_session(message.from_user.id)


@booking_router.callback_query(F.data == "back:home")
async def handle_back_home(callback: CallbackQuery) -> None:
    reset_session(callback.from_user.id)
    from app.texts import build_start_text

    await callback.message.edit_text(build_start_text(), reply_markup=main_menu_keyboard())
    await callback.answer()
