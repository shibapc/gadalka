import json
from pathlib import Path
from typing import Dict, List, Optional

from app.services.booking import get_service_by_id, now_ekb


class QueueStorage:
    def __init__(self, path: Path, history_path: Path) -> None:
        self.path = path
        self.history_path = history_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])
        if not self.history_path.exists():
            self._write_history([])

    def _read(self) -> List[Dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        dirty = False
        for idx, item in enumerate(data, start=1):
            if "position" not in item:
                item["position"] = idx
                dirty = True
            if "payment_status" not in item:
                item["payment_status"] = "pending"
                dirty = True
            if "session_status" not in item:
                item["session_status"] = "pending"
                dirty = True
            proof = item.get("payment_proof")
            if proof is None:
                item["payment_proof"] = None
            elif isinstance(proof, str):
                item["payment_proof"] = {"type": "unknown", "file_id": proof}
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
        for idx, item in enumerate(data, start=1):
            if "archive_id" not in item:
                item["archive_id"] = idx
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
        new_item = {
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
            "payment_proof": None,
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

    def set_payment_proof(self, position: int, file_id: str, file_type: str = "unknown") -> bool:
        data = self._read()
        for item in data:
            if item.get("position") == position:
                item["payment_proof"] = {"type": file_type, "file_id": file_id}
                item["payment_status"] = "awaiting_review"
                self._write(data)
                return True
        return False

    def get_by_position(self, position: int) -> Optional[Dict]:
        for item in self._read():
            if item.get("position") == position:
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

    def clear_history(self) -> None:
        self._write_history([])


storage = QueueStorage(Path("data/queue.json"), Path("data/history.json"))
