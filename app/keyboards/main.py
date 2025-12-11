from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Записаться 🙋‍♀️", callback_data="start_booking")],
        [InlineKeyboardButton(text="Мои заявки 📒", callback_data="my_bookings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
