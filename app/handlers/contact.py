from aiogram import F, Router
from aiogram.types import Message, ReplyKeyboardRemove

from app.logger import get_logger
from app.services.booking import get_service_by_id
from app.texts import ask_phone_text, payment_prompt_text
from app.keyboards.payment import payment_confirm_keyboard
from app.handlers.booking import get_session


contact_router = Router()
log = get_logger(__name__)


@contact_router.message(F.contact)
async def handle_contact(message: Message) -> None:
    session = get_session(message.from_user.id)
    if session.step != "phone":
        return
    phone = message.contact.phone_number
    session.phone = phone
    session.step = "payment_confirm"
    price = session.price or (get_service_by_id(session.service_id) or {}).get("price", 0)
    log.info("Phone received user=%s phone=%s", message.from_user.id, phone)
    await message.answer("Спасибо! Телефон сохранён.", reply_markup=ReplyKeyboardRemove())
    await message.answer(payment_prompt_text(price), reply_markup=payment_confirm_keyboard())
