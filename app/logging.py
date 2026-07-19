"""Логирование с ротацией без записи секретов в файлы."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(level: str = "INFO") -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    app_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    app_handler.setFormatter(formatter)
    error_handler = RotatingFileHandler(
        log_dir / "error.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    logging.basicConfig(level=level.upper(), handlers=[app_handler, error_handler])
