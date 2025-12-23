import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher

from app.config import settings
from app.handlers.admin import admin_router
from app.handlers.booking import booking_router
from app.handlers.contact import contact_router
from app.handlers.start import start_router
from app.logger import setup_logging


async def main() -> None:
    setup_logging(Path(settings.LOG_DIR))
    logging.getLogger(__name__).info("Starting bot")
    bot = Bot(token=settings.BOT_TOKEN, parse_mode="Markdown")
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(contact_router)
    dp.include_router(start_router)
    dp.include_router(booking_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
