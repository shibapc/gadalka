from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def payment_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить оплату ✅", callback_data="confirm_payment")],
            [InlineKeyboardButton(text="⬅️ На главную", callback_data="back:home")],
        ]
    )
