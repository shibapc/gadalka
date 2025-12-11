from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.handlers.booking import reset_session
from app.keyboards.main import main_menu_keyboard
from app.storage import storage
from app.texts import build_start_text


start_router = Router()


@start_router.message(CommandStart())
async def handle_start(message: Message) -> None:
    reset_session(message.from_user.id)
    await message.answer(build_start_text(), reply_markup=main_menu_keyboard())


@start_router.callback_query(F.data == "my_bookings")
async def handle_my_bookings(callback: CallbackQuery) -> None:
    await callback.answer()
    bookings = storage.list_user_requests(callback.from_user.id)
    if not bookings:
        text = "У вас пока нет заявок. Оформите новую через «Записаться»."
    else:
        text = "Ваши заявки:\n" + "\n".join(f"• {item}" for item in bookings)
    await callback.message.answer(text, parse_mode=None)
