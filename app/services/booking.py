from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from app.config import settings


def get_service_by_id(service_id: str) -> Optional[Dict]:
    return next((item for item in settings.SERVICES if item["id"] == service_id), None)


def now_ekb() -> datetime:
    return datetime.now(ZoneInfo("Asia/Yekaterinburg"))


def validate_birth_date(text: str) -> tuple[bool, str]:
    """
    Формат ДД.MM.ГГГГ, диапазоны: день 1-31, месяц 1-12, год 1929..текущий.
    Возвращает (ok, message), где message при ошибке уточняет поле.
    """
    text = text.strip()
    if len(text) != 10 or text[2] != "." or text[5] != ".":
        return False, "Формат даты должен быть ДД.MM.ГГГГ (например, 12.03.1990)"
    try:
        day = int(text[0:2])
        month = int(text[3:5])
        year = int(text[6:10])
    except ValueError:
        return False, "Используйте только цифры в формате ДД.MM.ГГГГ"

    if not (1 <= day <= 31):
        return False, "Некорректный день: допустимо 01-31. Введите дату ещё раз."
    if not (1 <= month <= 12):
        return False, "Некорректный месяц: допустимо 01-12. Введите дату ещё раз."
    current_year = now_ekb().year
    if not (1929 <= year <= current_year):
        return False, f"Некорректный год, введите дату ещё раз."
    return True, text
