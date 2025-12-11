from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings


def services_keyboard(selected_service_id: str | None) -> InlineKeyboardMarkup:
    rows = []
    for service in settings.SERVICES:
        prefix = "✅ " if selected_service_id == service["id"] else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{service['title']} — {service['price']}₽",
                    callback_data=f"service:{service['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ На главную", callback_data="back:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
