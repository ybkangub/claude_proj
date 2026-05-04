"""
auth.py — KIS OAuth2 토큰 및 WebSocket 승인키 관리
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import requests

import config

logger = logging.getLogger(__name__)


class KISTokenManager:
    def __init__(self) -> None:
        self._access_token: str = ""
        self._approval_key: str = ""
        self._expires_at: datetime = datetime.min

    # ── REST 토큰 ────────────────────────────────────────

    def issue_token(self) -> None:
        url = f"{config.BASE_URL}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self._expires_at = datetime.now() + timedelta(seconds=expires_in)
        mode = "모의투자" if config.PAPER_TRADING else "실거래"
        expire_kst = self._expires_at.astimezone(config.KST).strftime("%Y-%m-%d %H:%M KST")
        logger.info("✅ KIS API 연결 성공 [%s] | 토큰 만료: %s", mode, expire_kst)
        print(f"✅ Connected to KIS API [{mode}] | Token expires at {expire_kst}")

    def is_expired(self) -> bool:
        return datetime.now() >= self._expires_at - timedelta(minutes=5)

    def get_valid_token(self) -> str:
        if not self._access_token or self.is_expired():
            self.issue_token()
        return self._access_token

    # ── WebSocket 승인키 ─────────────────────────────────

    def issue_ws_approval_key(self) -> str:
        url = f"{config.BASE_URL}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": config.APP_KEY,
            "secretkey": config.APP_SECRET,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        self._approval_key = resp.json()["approval_key"]
        logger.debug("WebSocket 승인키 발급 완료")
        return self._approval_key

    # ── 헤더 생성 ────────────────────────────────────────

    def get_headers(self, tr_id: str = "") -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.get_valid_token()}",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
        }


token_manager = KISTokenManager()
