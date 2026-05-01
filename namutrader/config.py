"""
config.py — 환경변수 로딩 및 전역 상수 정의
모든 설정값은 .env 파일에서 로드. 소스코드에 credentials 절대 하드코딩 금지.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import pytz

# 프로젝트 루트에서 .env 로드
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)


def _require(key: str) -> str:
    """필수 환경변수 로드. 미설정 시 RuntimeError."""
    val = os.getenv(key)
    if not val:
        raise RuntimeError(
            f"필수 환경변수 '{key}'가 설정되지 않았습니다. .env 파일을 확인하세요."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── 인증 ──────────────────────────────────────────────
APP_KEY: str = _require("APP_KEY")
APP_SECRET: str = _require("APP_SECRET")
ACCOUNT_NO: str = _require("ACCOUNT_NO")

# ── API 엔드포인트 ──────────────────────────────────────
# ⚠️ API SPEC NEEDED: 나무증권 실제 BASE_URL 확인 필요
BASE_URL: str = _optional("BASE_URL", "https://openapi.namusecurities.com")
# ⚠️ API SPEC NEEDED: 나무증권 실제 WebSocket URL 확인 필요
WS_URL: str = _optional("WS_URL", "wss://openapi.namusecurities.com/ws")

# ── 거래 모드 ───────────────────────────────────────────
# PAPER_TRADING=true 이면 실제 주문 발송 없이 모의 실행
_paper_raw = _optional("PAPER_TRADING", "true").lower()
PAPER_TRADING: bool = _paper_raw not in ("false", "0", "no")

# ── 시간 설정 ───────────────────────────────────────────
KST = pytz.timezone("Asia/Seoul")

MARKET_OPEN_HOUR: int = 9
MARKET_OPEN_MINUTE: int = 0
MARKET_CLOSE_HOUR: int = 15
MARKET_CLOSE_MINUTE: int = 30

# 시장가 주문 마감 (동시호가 제외)
MARKET_ORDER_CUTOFF_HOUR: int = 15
MARKET_ORDER_CUTOFF_MINUTE: int = 20

# ── 리스크 파라미터 ─────────────────────────────────────
# 단일 포지션 최대 비중 (전체 자본 대비)
MAX_POSITION_PCT: float = float(_optional("MAX_POSITION_PCT", "0.1"))
# 일일 손실 한도 (이 비율 초과 시 당일 신규 주문 정지)
DAILY_LOSS_LIMIT_PCT: float = float(_optional("DAILY_LOSS_LIMIT_PCT", "0.02"))

# ── 스케줄러 ────────────────────────────────────────────
# 전략 실행 주기 (초 단위)
RUN_INTERVAL_SECONDS: int = int(_optional("RUN_INTERVAL_SECONDS", "60"))

# ── Telegram 알림 ────────────────────────────────────────
TELEGRAM_TOKEN: str = _optional("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID: str = _optional("TELEGRAM_CHAT_ID", "")

# ── 로그 파일 ────────────────────────────────────────────
LOG_FILE: str = _optional("LOG_FILE", "trading.log")
ORDERS_CSV: str = _optional("ORDERS_CSV", "orders.csv")
