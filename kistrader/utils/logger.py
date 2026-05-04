"""
logger.py — 구조화 로깅 설정 (파일 로테이션 + KST 타임스탬프)
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import config


class KSTFormatter(logging.Formatter):
    """로그 타임스탬프를 KST로 출력하는 포매터."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        from datetime import datetime
        dt = datetime.fromtimestamp(record.created, tz=config.KST)
        return dt.strftime("%Y-%m-%d %H:%M:%S KST")


def setup_logging(level: int = logging.INFO) -> None:
    """
    루트 로거 설정:
    - 파일: trading.log (RotatingFileHandler, 10MB × 5개)
    - 콘솔: stdout
    """
    log_path = Path(config.LOG_FILE)
    fmt = KSTFormatter(
        fmt="[%(asctime)s] %(levelname)-8s %(name)s — %(message)s"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logging.getLogger("websocket").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
