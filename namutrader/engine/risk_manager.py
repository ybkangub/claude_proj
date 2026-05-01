"""
risk_manager.py — 포지션 한도 및 일일 손실 한도 관리
"""

from __future__ import annotations

import logging

import config
from engine.position_manager import PositionManager

logger = logging.getLogger(__name__)


class RiskManager:
    """리스크 검증 및 거래 정지 제어."""

    def __init__(self, position_manager: PositionManager) -> None:
        self._pm = position_manager
        self.is_trading_halted: bool = False

    def check_position_size(self, ticker: str, qty: int, price: int) -> bool:
        """
        단일 포지션이 자본 대비 MAX_POSITION_PCT 이내인지 검증.

        Returns:
            True = 허용, False = 거부
        """
        order_value = qty * price
        total_capital = self._pm.total_equity
        max_allowed = int(total_capital * config.MAX_POSITION_PCT)

        existing_pos = self._pm.get_position(ticker)
        existing_value = existing_pos.market_value if existing_pos else 0
        projected_value = existing_value + order_value

        if projected_value > max_allowed:
            logger.warning(
                "주문 거부 (포지션 한도 초과): %s 예상=%d원 한도=%d원 (자본의 %.0f%%)",
                ticker, projected_value, max_allowed, config.MAX_POSITION_PCT * 100,
            )
            self._notify("포지션 한도 초과", f"{ticker}: {projected_value:,}원 > 한도 {max_allowed:,}원")
            return False

        return True

    def check_daily_loss(self) -> bool:
        """
        당일 손익이 일일 손실 한도를 초과했는지 확인.
        초과 시 거래 정지 플래그 설정.

        Returns:
            True = 정상 (거래 가능), False = 한도 초과 (거래 정지)
        """
        if self.is_trading_halted:
            logger.warning("거래 정지 상태: 신규 주문 불가")
            return False

        today_pnl = self._pm.today_pnl
        total_capital = self._pm.initial_capital
        loss_limit = int(total_capital * config.DAILY_LOSS_LIMIT_PCT)

        if today_pnl < -loss_limit:
            self.is_trading_halted = True
            msg = (
                f"⚠️ 일일 손실 한도 초과 — 당일 거래 정지\n"
                f"당일 손익: {today_pnl:+,}원 | 한도: -{loss_limit:,}원"
            )
            logger.warning(msg)
            self._notify("일일 손실 한도 초과", msg)
            return False

        return True

    def reset_daily_halt(self) -> None:
        """다음 거래일 시작 시 정지 플래그 초기화 (스케줄러에서 호출)."""
        if self.is_trading_halted:
            logger.info("일일 거래 정지 해제 (새 거래일)")
        self.is_trading_halted = False

    def _notify(self, title: str, message: str) -> None:
        """Telegram 알림 발송 (notifier가 설정된 경우)."""
        try:
            from utils.notifier import notifier
            notifier.send(f"🚨 {title}\n{message}")
        except Exception:
            pass
