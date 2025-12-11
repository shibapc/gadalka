from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def priority_keyboard(base_price: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Обычная — {base_price}₽", callback_data="priority:normal")],
            [InlineKeyboardButton(text=f"Срочно — {base_price * 2}₽ (в начало очереди)", callback_data="priority:urgent")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:home")],
        ]
    )
