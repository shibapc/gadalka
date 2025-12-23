import os
from dataclasses import dataclass
from typing import Tuple

from dotenv import load_dotenv


ENV_FILE = os.getenv("ENV_FILE", ".env")
load_dotenv(dotenv_path=ENV_FILE)
ENV_MODE = os.getenv("ENV", "prod").strip().lower()
if os.getenv("STORAGE_PATH") is None:
    os.environ["STORAGE_PATH"] = "data/queue_test.json" if ENV_MODE == "test" else "data/queue.json"
if os.getenv("HISTORY_PATH") is None:
    os.environ["HISTORY_PATH"] = "data/history_test.json" if ENV_MODE == "test" else "data/history.json"
if os.getenv("REVIEWS_PATH") is None:
    os.environ["REVIEWS_PATH"] = "data/reviews_test.json" if ENV_MODE == "test" else "data/reviews.json"


@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str
    PAYMENT_PROVIDER_TOKEN: str = ""
    MASTER_NAME: str = "Ксения Малиновская"
    PLACE_TITLE: str = "гадание"
    SERVICES: tuple = (
        {"id": "consult", "title": "Сеанс гадания", "price": 2500},
        {"id": "express", "title": "Личный экспресс-прогноз", "price": 1393},
    )
    ADMIN_IDS: Tuple[int, ...] = ()
    MODERATOR_IDS: Tuple[int, ...] = ()
    LOG_DIR: str = "logs"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            f"BOT_TOKEN is missing. Проверьте файл {ENV_FILE} и задайте токен."
        )
    admins = tuple(int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit())
    moderators = tuple(int(x) for x in os.getenv("MODERATOR_IDS", "").split(",") if x.strip().isdigit())
    provider = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
    log_dir = os.getenv("LOG_DIR", "logs")
    return Settings(
        BOT_TOKEN=token,
        ADMIN_IDS=admins,
        MODERATOR_IDS=moderators,
        PAYMENT_PROVIDER_TOKEN=provider,
        LOG_DIR=log_dir,
    )


settings = load_settings()
