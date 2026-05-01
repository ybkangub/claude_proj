"""
notifier.py — Telegram 봇 알림 (선택 사항)
TELEGRAM_TOKEN 미설정 시 silently skip.
"""

from __future__ import annotations

import logging

import requests

import config

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Telegram 봇으로 알림 메시지 전송."""

    def __init__(self) -> None:
        self._token = config.TELEGRAM_TOKEN
        self._chat_id = config.TELEGRAM_CHAT_ID
        self._enabled = bool(self._token and self._chat_id)

        if self._enabled:
            logger.info("Telegram 알림 활성화: chat_id=%s", self._chat_id)
        else:
            logger.info("Telegram 알림 비활성화 (TELEGRAM_TOKEN 미설정)")

    def send(self, message: str) -> bool:
        """
        Telegram 메시지 전송.

        Returns:
            True = 성공, False = 실패 또는 비활성화
        """
        if not self._enabled:
            return False

        url = _TELEGRAM_API.format(token=self._token)
        payload = {"chat_id": self._chat_id, "text": message, "parse_mode": "HTML"}

        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.warning("Telegram 전송 실패: %s", exc)
            return False

    def notify_fill(self, ticker: str, side: str, qty: int, price: int) -> None:
        msg = f"✅ 체결\n{side} {ticker}\n수량: {qty:,}주\n가격: {price:,}원"
        self.send(msg)

    def notify_risk(self, event: str, detail: str) -> None:
        self.send(f"🚨 리스크 이벤트: {event}\n{detail}")


# 싱글턴
notifier = TelegramNotifier()
