from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def payment_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 2500₽ ✅", callback_data="pay_invoice")],
            [InlineKeyboardButton(text="⬅️ На главную", callback_data="back:home")],
        ]
    )
