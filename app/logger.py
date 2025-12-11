import logging
from pathlib import Path
from typing import Optional


class LineLimitedFileHandler(logging.FileHandler):
    """Перезапускает файл, если строк > max_lines."""

    def __init__(self, filename: Path, mode: str = "a", max_lines: int = 1000) -> None:
        self.max_lines = max_lines
        filename.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, mode, encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_limit()
        except Exception:
            # Не блокируем логирование при ошибках контроля размера
            pass
        super().emit(record)

    def _ensure_limit(self) -> None:
        try:
            self.flush()
            with open(self.baseFilename, "r", encoding="utf-8") as f:
                line_count = sum(1 for _ in f)
            if line_count >= self.max_lines:
                with open(self.baseFilename, "w", encoding="utf-8") as f:
                    f.truncate(0)
        except FileNotFoundError:
            Path(self.baseFilename).touch()


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    info_handler = LineLimitedFileHandler(log_dir / "info.log", max_lines=1000)
    error_handler = LineLimitedFileHandler(log_dir / "errors.log", max_lines=1000)
    info_handler.setLevel(logging.INFO)
    error_handler.setLevel(logging.ERROR)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    info_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    # Минимум в info, так что всё, что выше INFO, пойдёт и в error_handler.
    root_logger.addHandler(info_handler)
    root_logger.addHandler(error_handler)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(name)
