from aiogram import F, Router
from aiogram.types import Message

from app.keyboards.main import main_menu_keyboard
from app.logger import get_logger
from app.models import BookingSession
from app.storage import storage
from app.texts import payment_proof_received_text
from app.handlers.booking import get_session, reset_session


proofs_router = Router()
log = get_logger(__name__)


@proofs_router.message(F.photo | F.document)
async def handle_payment_proof(message: Message) -> None:
    session: BookingSession = get_session(message.from_user.id)
    if session.step != "payment_proof" or not session.last_position:
        return

    file_id = None
    file_type = "unknown"
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"

    if not file_id:
        await message.answer("Отправьте фото или документ с чеком.")
        return

    if storage.set_payment_proof(session.last_position, file_id, file_type=file_type):
        log.info("Payment proof saved for position %s by user %s", session.last_position, message.from_user.id)
        await message.answer(payment_proof_received_text(), reply_markup=main_menu_keyboard())
    else:
        await message.answer("Не удалось сохранить чек. Попробуйте /start и отправить снова.")
    reset_session(message.from_user.id)
