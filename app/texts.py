from app.config import settings
from app.models import BookingSession
from app.services.booking import get_service_by_id, get_service_price

PREPAY_AMOUNT = 2500


def build_start_text() -> str:
    return (
        f"Запись к Ксении на гадание.\n\n"
        "Работаем в порядке очереди: выбирайте услугу, отвечайте на вопросы – и мы свяжемся.\n"
        "Запись подтверждается только после предоплаты\n"
        "Подсказка: отправьте /start чтобы начать заново."
    )


def booking_prompt_text() -> str:
    return "Выберите услугу 👇"


def service_selected_text(service_id: str) -> str:
    service = get_service_by_id(service_id) or {"title": service_id, "price": "—"}
    return f"Вы выбрали: *{service['title']}*."


def ask_birth_date_text() -> str:
    return "Введите дату рождения в формате ДД.ММ.ГГГГ (например, 19.09.2005)"


def ask_name_text() -> str:
    return "Введите ваше имя"


def ask_full_name_text() -> str:
    return "Введите ФИО"


def ask_intuitive_number_text() -> str:
    return "Введите вашу интуитивную цифру от 0 до 78."


def ask_problem_text() -> str:
    return "Опишите вашу проблему максимально подробно."


def ask_problem_brief_text() -> str:
    return "Кратко опишите сердце вашего запроса (1-2 предложения)."


def ask_phone_text() -> str:
    return "Поделитесь номером телефона, чтобы мы могли связаться. Нажмите кнопку ниже."


def payment_prompt_text(total_price: int) -> str:
    rest = max(total_price - PREPAY_AMOUNT, 0)
    rest_text = f"Остаток {rest}₽ будет оплачен отдельно." if rest else ""
    return (
        f"Для подтверждения записи нужна предоплата {PREPAY_AMOUNT}₽.\n"
        f"{rest_text}\n"
        "Реквизиты (пример):\n"
        "СБП: 4100 0000 0000 0000\n"
        "Комментарий к платежу: Ваше имя + дата рождения\n"
        "После оплаты нажмите «Подтвердить оплату» и отправьте чек сюда."
    )


def ask_payment_proof_text() -> str:
    return "Отправьте фото/скан чека. Это нужно для подтверждения оплаты администратором."


def payment_proof_received_text() -> str:
    return "Чек получен. Администратор проверит оплату и подтвердит запись. С вами свяжутся."


def queue_confirmation_text(session: BookingSession) -> str:
    service = get_service_by_id(session.service_id) or {"title": session.service_id, "price": "—"}
    price = session.price or get_service_price(session.service_id or "", PREPAY_AMOUNT)
    price_text = f"{price}₽"
    urgency = "Срочная (в начале очереди)" if session.is_urgent else "Обычная"
    return (
        "Заявка принята ✅\n\n"
        f"*Услуга:* {service['title']}\n"
        f"*Тип записи:* {urgency}\n"
        f"*Стоимость:* {price_text}\n"
        f"*Дата рождения:* {session.birth_date}\n"
        f"*Имя:* {session.name}\n"
        "*Описание:*\n"
        f"{session.problem}\n\n"
        "С вами свяжутся. Оплата получена автоматически."
    )
