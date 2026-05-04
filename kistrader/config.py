"""
config.py — 환경변수 로드 및 KIS API 상수 정의
"""
from __future__ import annotations

import os

import pytz
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        raise RuntimeError(f"환경변수 {key} 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return val

def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)

# ── 인증 정보 ────────────────────────────────────────────
APP_KEY: str = _require("APP_KEY")
APP_SECRET: str = _require("APP_SECRET")
ACCOUNT_NO: str = _require("ACCOUNT_NO")          # 8자리 계좌번호
ACCOUNT_PRODUCT_CODE: str = _optional("ACCOUNT_PRODUCT_CODE", "01")  # 계좌상품코드

# ── 거래 모드 ────────────────────────────────────────────
_paper_raw = _optional("PAPER_TRADING", "true").strip().lower()
PAPER_TRADING: bool = _paper_raw not in ("false", "0", "no")

# ── KIS API 엔드포인트 (모의투자 / 실거래 자동 분기) ────
if PAPER_TRADING:
    BASE_URL: str = "https://openapivts.koreainvestment.com:29443"
    WS_URL: str = "ws://ops.koreainvestment.com:31000"
else:
    BASE_URL = "https://openapi.koreainvestment.com:9443"
    WS_URL = "ws://ops.koreainvestment.com:21000"

# ── 타임존 및 장 시간 ────────────────────────────────────
KST = pytz.timezone("Asia/Seoul")
MARKET_OPEN_H, MARKET_OPEN_M = 9, 0
MARKET_CLOSE_H, MARKET_CLOSE_M = 15, 30

# ── 리스크 파라미터 ──────────────────────────────────────
MAX_POSITION_PCT: float = float(_optional("MAX_POSITION_PCT", "0.1"))
DAILY_LOSS_LIMIT_PCT: float = float(_optional("DAILY_LOSS_LIMIT_PCT", "0.02"))
RUN_INTERVAL_SECONDS: int = int(_optional("RUN_INTERVAL_SECONDS", "60"))

# ── 파일 경로 ────────────────────────────────────────────
LOG_FILE: str = _optional("LOG_FILE", "trading.log")
ORDERS_CSV: str = _optional("ORDERS_CSV", "orders.csv")
