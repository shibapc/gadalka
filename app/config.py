import os
from dataclasses import dataclass
from typing import Tuple

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str
    MASTER_NAME: str = "Ксения Малиновская"
    PLACE_TITLE: str = "гадание"
    SERVICES: tuple = (
        {"id": "consult", "title": "Консультация", "price": 5000},
    )
    ADMIN_IDS: Tuple[int, ...] = ()
    MODERATOR_IDS: Tuple[int, ...] = ()


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Создайте .env на основе .env.example и задайте токен.")
    admins = tuple(int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit())
    moderators = tuple(int(x) for x in os.getenv("MODERATOR_IDS", "").split(",") if x.strip().isdigit())
    return Settings(BOT_TOKEN=token, ADMIN_IDS=admins, MODERATOR_IDS=moderators)


settings = load_settings()
