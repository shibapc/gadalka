from dataclasses import dataclass
from typing import Optional


@dataclass
class BookingSession:
    service_id: Optional[str] = None
    birth_date: Optional[str] = None
    name: Optional[str] = None
    problem: Optional[str] = None
    last_position: Optional[int] = None
    step: Optional[str] = None  # birth_date -> name -> problem -> payment_confirm -> payment_proof
