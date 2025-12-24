import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from app.services.booking import get_service_by_id, now_ekb


class QueueStorage:
    def __init__(self, path: Path, history_path: Path, reviews_path: Path) -> None:
        self.path = path
        self.history_path = history_path
        self.reviews_path = reviews_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])
        if not self.history_path.exists():
            self._write_history([])
        if not self.reviews_path.exists():
            self._write_reviews([])

    def _max_order_id_from_path(self, path: Path) -> int:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0
        max_id = 0
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("order_id"), int):
                max_id = max(max_id, item["order_id"])
        return max_id

    def _read(self) -> List[Dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        dirty = False
        max_order_id = max(
            self._max_order_id_from_path(self.history_path),
            0,
        )
        for item in data:
            if isinstance(item.get("order_id"), int):
                max_order_id = max(max_order_id, item["order_id"])
        for idx, item in enumerate(data, start=1):
            if "position" not in item:
                item["position"] = idx
                dirty = True
            if "order_id" not in item:
                max_order_id += 1
                item["order_id"] = max_order_id
                dirty = True
            if "result_sent" not in item:
                item["result_sent"] = False
                dirty = True
            if "result_payload" not in item:
                item["result_payload"] = None
                dirty = True
            if "review_skipped_at" not in item:
                item["review_skipped_at"] = None
                dirty = True
            if "payment_status" not in item:
                item["payment_status"] = "pending"
                dirty = True
            if "session_status" not in item:
                item["session_status"] = "pending"
                dirty = True
            if "user_username" not in item:
                item["user_username"] = None
                dirty = True
            if "user_fullname" not in item:
                item["user_fullname"] = None
                dirty = True
            if "is_urgent" not in item:
                item["is_urgent"] = False
                dirty = True
            if "price" not in item:
                item["price"] = None
                dirty = True
            if "phone" not in item:
                item["phone"] = None
                dirty = True
        # срочные вверх, сортируем по дате создания
        data.sort(key=lambda x: (not x.get("is_urgent", False), x.get("created_at", "")))
        for idx, item in enumerate(data, start=1):
            item["position"] = idx
        dirty = True  # всегда сохраняем после нормализации
        if dirty:
            self._write(data)
        return data

    def _write(self, data: List[Dict]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_history(self) -> List[Dict]:
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []
        dirty = False
        max_order_id = max(
            self._max_order_id_from_path(self.path),
            0,
        )
        for item in data:
            if isinstance(item.get("order_id"), int):
                max_order_id = max(max_order_id, item["order_id"])
        for idx, item in enumerate(data, start=1):
            if "archive_id" not in item:
                item["archive_id"] = idx
                dirty = True
            if "order_id" not in item:
                max_order_id += 1
                item["order_id"] = max_order_id
                dirty = True
            if "result_sent" not in item:
                item["result_sent"] = False
                dirty = True
            if "result_payload" not in item:
                item["result_payload"] = None
                dirty = True
            if "review_skipped_at" not in item:
                item["review_skipped_at"] = None
                dirty = True
            if "user_username" not in item:
                item["user_username"] = None
                dirty = True
            if "user_fullname" not in item:
                item["user_fullname"] = None
                dirty = True
            if "is_urgent" not in item:
                item["is_urgent"] = False
                dirty = True
            if "price" not in item:
                item["price"] = None
                dirty = True
            if "phone" not in item:
                item["phone"] = None
                dirty = True
        if dirty:
            self._write_history(data)
        return data

    def _write_history(self, data: List[Dict]) -> None:
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_reviews(self) -> List[Dict]:
        try:
            with open(self.reviews_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []
        dirty = False
        for idx, item in enumerate(data, start=1):
            if "review_id" not in item:
                item["review_id"] = idx
                dirty = True
            if "user_username" not in item:
                item["user_username"] = None
                dirty = True
            if "user_fullname" not in item:
                item["user_fullname"] = None
                dirty = True
            if "name" not in item:
                item["name"] = None
                dirty = True
            if "birth_date" not in item:
                item["birth_date"] = None
                dirty = True
            if "order_created_at" not in item:
                item["order_created_at"] = None
                dirty = True
            if "order_id" not in item:
                item["order_id"] = None
                dirty = True
        if dirty:
            self._write_reviews(data)
        return data

    def _write_reviews(self, data: List[Dict]) -> None:
        with open(self.reviews_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_request(
        self,
        user_id: int,
        service_id: str,
        birth_date: str,
        name: str,
        problem: str,
        user_username: Optional[str],
        user_fullname: Optional[str],
        is_urgent: bool,
        price: Optional[int],
        phone: Optional[str],
        payment_status: str = "pending",
    ) -> int:
        data = self._read()
        max_order_id = max(
            max((item.get("order_id", 0) or 0) for item in data) if data else 0,
            self._max_order_id_from_path(self.history_path),
        )
        new_item = {
            "order_id": max_order_id + 1,
            "user_id": user_id,
            "service_id": service_id,
            "birth_date": birth_date,
            "name": name,
            "problem": problem,
            "user_username": user_username,
            "user_fullname": user_fullname,
            "is_urgent": is_urgent,
            "price": price,
            "phone": phone,
            "payment_status": payment_status,
            "session_status": "pending",
            "result_sent": False,
            "result_payload": None,
            "review_skipped_at": None,
            "created_at": now_ekb().isoformat(),
        }
        data.append(new_item)
        data.sort(key=lambda x: (not x.get("is_urgent", False), x.get("created_at", "")))
        for idx, item in enumerate(data, start=1):
            item["position"] = idx
        self._write(data)
        for item in data:
            if item is new_item:
                return item["position"]
        return len(data)

    def list_user_requests(self, user_id: int) -> List[str]:
        entries = self._read()
        lines: List[str] = []
        for item in entries:
            if item.get("user_id") != user_id:
                continue
            service = get_service_by_id(item.get("service_id", "")) or {"title": item.get("service_id", "")}
            pay_status = item.get("payment_status")
            pay_text = "оплачено" if pay_status == "paid" else "на проверке"
            created = item.get("created_at", "")
            created_date = created.split("T")[0] if "T" in created else created
            lines.append(f"{service['title']}, {created_date}, {pay_text}")
        return lines

    def list_all(self) -> List[Dict]:
        return self._read()

    def list_by_payment_status(self, statuses: List[str]) -> List[Dict]:
        return [item for item in self._read() if item.get("payment_status") in statuses]

    def update_payment_status(self, position: int, status: str) -> bool:
        data = self._read()
        for item in data:
            if item.get("position") == position:
                item["payment_status"] = status
                self._write(data)
                return True
        return False

    def update_session_status(self, position: int, status: str) -> bool:
        data = self._read()
        for item in data:
            if item.get("position") == position:
                item["session_status"] = status
                self._write(data)
                return True
        return False

    def get_by_position(self, position: int) -> Optional[Dict]:
        for item in self._read():
            if item.get("position") == position:
                return item
        return None

    def get_by_order_id(self, order_id: int) -> Optional[Dict]:
        for item in self._read():
            if item.get("order_id") == order_id:
                return item
        return None

    def delete_and_archive(self, position: int) -> bool:
        data = self._read()
        target = None
        rest: List[Dict] = []
        for item in data:
            if item.get("position") == position:
                target = item
            else:
                rest.append(item)
        if not target:
            return False
        history = self._read_history()
        target["archived_at"] = now_ekb().isoformat()
        target["archive_id"] = len(history) + 1
        history.append(target)
        self._write_history(history)
        for idx, item in enumerate(rest, start=1):
            item["position"] = idx
        self._write(rest)
        return True

    def list_history(self, limit: int = 20) -> List[Dict]:
        history = self._read_history()
        return history[-limit:][::-1]

    def get_history_by_id(self, archive_id: int) -> Optional[Dict]:
        for item in self._read_history():
            if item.get("archive_id") == archive_id:
                return item
        return None

    def get_history_by_order_id(self, order_id: int) -> Optional[Dict]:
        for item in self._read_history():
            if item.get("order_id") == order_id:
                return item
        return None

    def set_result_sent(self, order_id: int, payload: Dict) -> bool:
        data = self._read()
        for item in data:
            if item.get("order_id") == order_id:
                item["result_sent"] = True
                item["result_payload"] = payload
                self._write(data)
                return True
        history = self._read_history()
        for item in history:
            if item.get("order_id") == order_id:
                item["result_sent"] = True
                item["result_payload"] = payload
                self._write_history(history)
                return True
        return False

    def set_review_skipped(self, order_id: int) -> bool:
        stamp = now_ekb().isoformat()
        data = self._read()
        for item in data:
            if item.get("order_id") == order_id:
                item["review_skipped_at"] = stamp
                self._write(data)
                return True
        history = self._read_history()
        for item in history:
            if item.get("order_id") == order_id:
                item["review_skipped_at"] = stamp
                self._write_history(history)
                return True
        return False

    def history_stats(self, default_price: int = 2500, service_id: str | None = None) -> tuple[int, int]:
        history = self._read_history()
        if service_id:
            history = [item for item in history if item.get("service_id") == service_id]
        total = len(history)
        total_sum = sum(
            item.get("price") if isinstance(item.get("price"), int) else default_price for item in history
        )
        return total, total_sum

    def add_review(
        self,
        user_id: int,
        service_id: str,
        text: str,
        user_username: Optional[str],
        user_fullname: Optional[str],
        name: Optional[str],
        birth_date: Optional[str],
        order_created_at: Optional[str],
        order_id: Optional[int],
    ) -> int:
        reviews = self._read_reviews()
        new_item = {
            "user_id": user_id,
            "service_id": service_id,
            "text": text,
            "user_username": user_username,
            "user_fullname": user_fullname,
            "name": name,
            "birth_date": birth_date,
            "order_created_at": order_created_at,
            "order_id": order_id,
            "created_at": now_ekb().isoformat(),
        }
        reviews.append(new_item)
        for idx, item in enumerate(reviews, start=1):
            item["review_id"] = idx
        self._write_reviews(reviews)
        return reviews[-1]["review_id"]

    def list_reviews(self, service_id: str | None = None) -> List[Dict]:
        reviews = self._read_reviews()
        if service_id:
            reviews = [item for item in reviews if item.get("service_id") == service_id]
        return reviews[::-1]

    def get_review_by_id(self, review_id: int) -> Optional[Dict]:
        for item in self._read_reviews():
            if item.get("review_id") == review_id:
                return item
        return None

    def get_review_for_order(self, order_id: Optional[int]) -> Optional[Dict]:
        if not order_id:
            return None
        for item in self._read_reviews():
            if item.get("order_id") == order_id:
                return item
        return None

    def clear_history(self) -> None:
        self._write_history([])


QUEUE_PATH = Path(os.getenv("STORAGE_PATH", "data/queue.json"))
HISTORY_PATH = Path(os.getenv("HISTORY_PATH", "data/history.json"))
REVIEWS_PATH = Path(os.getenv("REVIEWS_PATH", "data/reviews.json"))
storage = QueueStorage(QUEUE_PATH, HISTORY_PATH, REVIEWS_PATH)
