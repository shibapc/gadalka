from aiogram import F, Router
from aiogram.types import LabeledPrice, Message, ReplyKeyboardRemove, PreCheckoutQuery

from app.config import settings
from app.handlers.booking import get_session
from app.logger import get_logger
from app.services.booking import get_service_by_id, get_service_price


contact_router = Router()
log = get_logger(__name__)


@contact_router.message(F.contact)
async def handle_contact(message: Message) -> None:
    session = get_session(message.from_user.id)
    if session.step != "phone":
        return
    phone = message.contact.phone_number
    session.phone = phone
    session.step = "waiting_payment"
    log.info("Phone received user=%s phone=%s", message.from_user.id, phone)
    await message.answer("Спасибо! Телефон сохранён.", reply_markup=ReplyKeyboardRemove())
    if not settings.PAYMENT_PROVIDER_TOKEN:
        await message.answer("Платёжный токен не задан, обратитесь к администратору.")
        return
    price = session.price or get_service_price(session.service_id or "")
    service = get_service_by_id(session.service_id or "") or {"title": "Запись"}
    prices = [LabeledPrice(label=service["title"], amount=price * 100)]
    await message.answer_invoice(
        title=f"Оплата: {service['title']}",
        description=f"Оплата {price}₽ за запись.",
        provider_token=settings.PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        payload="prepay",
    )


@contact_router.pre_checkout_query()
async def handle_pre_checkout(query: PreCheckoutQuery) -> None:
    # Обязательный ответ, иначе Telegram показывает ошибку оплаты
    await query.answer(ok=True)
