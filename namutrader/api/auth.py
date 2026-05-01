"""
auth.py — 나무증권 OAuth2 토큰 발급 및 자동 갱신
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

# ⚠️ API SPEC NEEDED: 나무증권 토큰 발급 엔드포인트 확인 필요
_TOKEN_PATH = "/oauth2/token"


class TokenManager:
    """OAuth2 액세스 토큰 발급 및 자동 갱신."""

    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        # 만료 N초 전에 미리 갱신
        self._refresh_buffer_seconds: int = 300

    def issue_token(self) -> None:
        """나무증권 API에서 새 액세스 토큰 발급."""
        if config.PAPER_TRADING:
            self._mock_issue_token()
            return

        url = config.BASE_URL + _TOKEN_PATH
        payload = {
            # ⚠️ API SPEC NEEDED: 실제 요청 body 필드명 확인 필요
            "grant_type": "client_credentials",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
        }
        headers = {"Content-Type": "application/json"}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("토큰 발급 실패: %s", exc)
            raise

        # ⚠️ API SPEC NEEDED: 응답 필드명 확인 필요 (access_token, expires_in 등)
        self._access_token = data.get("access_token") or data.get("token")
        expires_in: int = int(data.get("expires_in", 86400))
        self._expires_at = datetime.now(tz=config.KST) + timedelta(seconds=expires_in)

        self._log_connection_success()

    def _mock_issue_token(self) -> None:
        """페이퍼 트레이딩 모드: 실제 API 호출 없이 mock 토큰 생성."""
        self._access_token = "PAPER_TRADING_MOCK_TOKEN"
        self._expires_at = datetime.now(tz=config.KST) + timedelta(hours=24)
        self._log_connection_success()

    def _log_connection_success(self) -> None:
        expires_str = self._expires_at.strftime("%Y-%m-%d %H:%M:%S %Z")
        mode = "[PAPER]" if config.PAPER_TRADING else "[LIVE]"
        msg = f"✅ Connected to 나무증권 API {mode} | Token expires at {expires_str}"
        print(msg)
        logger.info(msg)

    def is_expired(self) -> bool:
        """토큰이 만료됐거나 갱신 버퍼 시간 이내인지 확인."""
        if self._access_token is None or self._expires_at is None:
            return True
        now = datetime.now(tz=config.KST)
        return now >= self._expires_at - timedelta(seconds=self._refresh_buffer_seconds)

    def get_valid_token(self) -> str:
        """유효한 토큰 반환. 만료 임박 시 자동 재발급."""
        if self.is_expired():
            logger.info("토큰 만료 임박 — 재발급 중...")
            self.issue_token()
        return self._access_token  # type: ignore[return-value]

    def get_headers(self) -> dict[str, str]:
        """API 요청에 필요한 인증 헤더 반환."""
        token = self.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # ⚠️ API SPEC NEEDED: 추가 헤더 필드 확인 필요 (appkey, appsecret 등)
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
        }

    @property
    def expires_at(self) -> Optional[datetime]:
        return self._expires_at


# 싱글턴 인스턴스
token_manager = TokenManager()
