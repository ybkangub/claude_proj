"""
scheduler.py — 장 시간 인식 스케줄러 (한국 공휴일 포함)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Callable, Set

import schedule

import config

logger = logging.getLogger(__name__)

# 2025–2026년 한국 공휴일 (YYYY-MM-DD)
_KR_HOLIDAYS: Set[date] = {
    date(2025, 1, 1),   # 신정
    date(2025, 1, 28),  # 설날 연휴
    date(2025, 1, 29),  # 설날
    date(2025, 1, 30),  # 설날 연휴
    date(2025, 3, 1),   # 삼일절
    date(2025, 5, 5),   # 어린이날
    date(2025, 5, 6),   # 어린이날 대체
    date(2025, 6, 6),   # 현충일
    date(2025, 8, 15),  # 광복절
    date(2025, 10, 3),  # 개천절
    date(2025, 10, 5),  # 추석 연휴
    date(2025, 10, 6),  # 추석
    date(2025, 10, 7),  # 추석 연휴
    date(2025, 10, 9),  # 한글날
    date(2025, 12, 25), # 크리스마스
    date(2026, 1, 1),   # 신정
    date(2026, 2, 16),  # 설날 연휴
    date(2026, 2, 17),  # 설날
    date(2026, 2, 18),  # 설날 연휴
    date(2026, 3, 1),   # 삼일절
    date(2026, 5, 5),   # 어린이날
    date(2026, 6, 6),   # 현충일
    date(2026, 8, 15),  # 광복절
    date(2026, 9, 24),  # 추석 연휴
    date(2026, 9, 25),  # 추석
    date(2026, 9, 26),  # 추석 연휴
    date(2026, 10, 9),  # 한글날
    date(2026, 12, 25), # 크리스마스
}


class KoreanMarketScheduler:
    """한국 주식 시장 시간 인식 스케줄러."""

    @staticmethod
    def is_holiday(d: date) -> bool:
        return d in _KR_HOLIDAYS

    @staticmethod
    def is_market_open() -> bool:
        """현재 시각이 장 중인지 확인 (KST 09:00–15:30, 평일, 공휴일 제외)."""
        now = datetime.now(tz=config.KST)
        today = now.date()

        if now.weekday() >= 5:
            return False
        if KoreanMarketScheduler.is_holiday(today):
            return False

        open_t = now.replace(hour=config.MARKET_OPEN_HOUR, minute=config.MARKET_OPEN_MINUTE, second=0, microsecond=0)
        close_t = now.replace(hour=config.MARKET_CLOSE_HOUR, minute=config.MARKET_CLOSE_MINUTE, second=0, microsecond=0)
        return open_t <= now <= close_t

    def run_every(
        self,
        seconds: int,
        job: Callable[[], None],
        market_only: bool = True,
    ) -> None:
        """
        주기적으로 job 실행.

        Args:
            seconds: 실행 간격 (초)
            job: 실행할 함수
            market_only: True이면 장 중에만 실행
        """
        def _wrapped() -> None:
            if market_only and not self.is_market_open():
                logger.debug("장 외 시간 — 전략 실행 건너뜀")
                return
            try:
                job()
            except Exception as exc:
                logger.error("전략 실행 오류: %s", exc, exc_info=True)

        schedule.every(seconds).seconds.do(_wrapped)
        logger.info("스케줄러 등록: 매 %d초 실행 (장중만=%s)", seconds, market_only)

    @staticmethod
    def run_at_open(job: Callable[[], None]) -> None:
        """장 시작 시 1회 실행 (09:00 KST)."""
        open_time = f"{config.MARKET_OPEN_HOUR:02d}:{config.MARKET_OPEN_MINUTE:02d}"
        schedule.every().day.at(open_time).do(job)
        logger.info("장 시작 작업 등록: %s KST", open_time)

    @staticmethod
    def run_at_close(job: Callable[[], None]) -> None:
        """장 마감 시 1회 실행 (15:30 KST)."""
        close_time = f"{config.MARKET_CLOSE_HOUR:02d}:{config.MARKET_CLOSE_MINUTE:02d}"
        schedule.every().day.at(close_time).do(job)
        logger.info("장 마감 작업 등록: %s KST", close_time)
