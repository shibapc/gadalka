from typing import Dict

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.main import main_menu_keyboard
from app.keyboards.payment import payment_confirm_keyboard
from app.keyboards.services import services_keyboard
from app.logger import get_logger
from app.models import BookingSession
from app.services.booking import get_service_by_id, now_ekb, validate_birth_date
from app.storage import storage
from app.texts import (
    ask_birth_date_text,
    ask_name_text,
    ask_problem_text,
    booking_prompt_text,
    ask_payment_proof_text,
    payment_proof_received_text,
    queue_confirmation_text,
    payment_prompt_text,
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
    await callback.message.edit_text(booking_prompt_text(), reply_markup=services_keyboard(session.service_id))
    await callback.answer()


@booking_router.callback_query(F.data.startswith("service:"))
async def handle_service(callback: CallbackQuery) -> None:
    service_id = callback.data.split(":", 1)[1]
    session = get_session(callback.from_user.id)
    session.service_id = service_id
    session.step = "birth_date"
    await callback.message.edit_text(service_selected_text(service_id))
    await callback.message.answer(ask_birth_date_text())
    await callback.answer("Услуга выбрана")


@booking_router.message(F.text)
async def handle_steps(message: Message) -> None:
    session = get_session(message.from_user.id)
    if not session.step:
        return

    text = message.text.strip()

    if session.step == "birth_date":
        ok, parsed = validate_birth_date(text)
        if not ok:
            await message.answer(parsed)
            return
        session.birth_date = parsed
        session.step = "name"
        await message.answer(ask_name_text())
        return

    if session.step == "name":
        session.name = text
        session.step = "problem"
        await message.answer(ask_problem_text())
        return

    if session.step == "problem":
        session.problem = text
        session.step = "payment_confirm"
        await message.answer(payment_prompt_text(), reply_markup=payment_confirm_keyboard())
        return

    if session.step == "payment_proof":
        await message.answer(ask_payment_proof_text())
        return


@booking_router.callback_query(F.data == "confirm_payment")
async def handle_confirm_payment(callback: CallbackQuery) -> None:
    session = get_session(callback.from_user.id)
    if session.step != "payment_confirm":
        await callback.answer("Начните запись через /start", show_alert=True)
        return
    if not (session.service_id and session.birth_date and session.name and session.problem):
        await callback.answer("Не хватает данных для записи. Начните заново через /start.", show_alert=True)
        reset_session(callback.from_user.id)
        return
    position = storage.add_request(
        user_id=callback.from_user.id,
        service_id=session.service_id,
        birth_date=session.birth_date,
        name=session.name,
        problem=session.problem,
    )
    session.last_position = position
    session.step = "payment_proof"
    log.info(
        "Queue added user=%s service=%s position=%s",
        callback.from_user.id,
        session.service_id,
        position,
    )
    await callback.message.edit_text(queue_confirmation_text(session))
    await callback.message.answer(ask_payment_proof_text())
    await callback.answer("Заявка создана")


@booking_router.callback_query(F.data == "back:home")
async def handle_back_home(callback: CallbackQuery) -> None:
    reset_session(callback.from_user.id)
    from app.texts import build_start_text

    await callback.message.edit_text(build_start_text(), reply_markup=main_menu_keyboard())
    await callback.answer()
