from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def priority_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Обычная очередь", callback_data="priority:normal")],
            [InlineKeyboardButton(text="Срочно (в начало очереди)", callback_data="priority:urgent")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:home")],
        ]
    )
