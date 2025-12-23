from dataclasses import dataclass
from typing import Optional


@dataclass
class BookingSession:
    service_id: Optional[str] = None
    is_urgent: bool = False
    price: Optional[int] = None
    birth_date: Optional[str] = None
    name: Optional[str] = None
    intuitive_number: Optional[int] = None
    problem: Optional[str] = None
    phone: Optional[str] = None
    last_position: Optional[int] = None
    step: Optional[str] = None  # priority -> birth_date -> name -> problem -> phone -> payment_confirm -> payment_proof
