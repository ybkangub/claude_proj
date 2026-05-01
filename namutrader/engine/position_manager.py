"""
position_manager.py — 포지션 추적 및 미실현 손익 계산
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

import config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """단일 종목 포지션."""
    ticker: str
    qty: int
    avg_price: int          # 평균 매수단가 (원, 정수)
    current_price: int = 0  # 현재가 (실시간 갱신)

    @property
    def book_value(self) -> int:
        return self.qty * self.avg_price

    @property
    def market_value(self) -> int:
        return self.qty * (self.current_price or self.avg_price)

    @property
    def unrealized_pnl(self) -> int:
        return self.market_value - self.book_value

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.book_value == 0:
            return 0.0
        return self.unrealized_pnl / self.book_value * 100


class PositionManager:
    """전체 포지션 관리 및 포트폴리오 요약."""

    def __init__(self, initial_capital: int) -> None:
        """
        Args:
            initial_capital: 초기 자본금 (원, 정수)
        """
        self.initial_capital: int = initial_capital
        self.cash: int = initial_capital
        self._positions: Dict[str, Position] = {}
        self._realized_pnl: int = 0
        self._today_realized_pnl: int = 0
        self._today_date: Optional[datetime] = None

    # ── 포지션 업데이트 ────────────────────────────────────

    def on_buy_filled(self, ticker: str, qty: int, price: int) -> None:
        """매수 체결 처리."""
        cost = qty * price
        self.cash -= cost

        if ticker in self._positions:
            pos = self._positions[ticker]
            total_qty = pos.qty + qty
            new_avg = (pos.book_value + cost) // total_qty
            pos.qty = total_qty
            pos.avg_price = new_avg
        else:
            self._positions[ticker] = Position(ticker=ticker, qty=qty, avg_price=price)

        logger.info("매수 체결: %s qty=%d price=%d | 잔고=%d원", ticker, qty, price, self.cash)

    def on_sell_filled(self, ticker: str, qty: int, price: int) -> None:
        """매도 체결 처리."""
        if ticker not in self._positions:
            logger.error("매도 오류: 보유하지 않은 종목 %s", ticker)
            return

        pos = self._positions[ticker]
        proceeds = qty * price
        cost_basis = qty * pos.avg_price
        realized = proceeds - cost_basis

        self.cash += proceeds
        self._realized_pnl += realized
        self._refresh_today_pnl(realized)

        if qty >= pos.qty:
            del self._positions[ticker]
        else:
            pos.qty -= qty

        logger.info(
            "매도 체결: %s qty=%d price=%d | 실현손익=%d원 | 잔고=%d원",
            ticker, qty, price, realized, self.cash,
        )

    def update_price(self, ticker: str, price: int) -> None:
        """실시간 현재가 갱신 (WebSocket 콜백에서 호출)."""
        if ticker in self._positions:
            self._positions[ticker].current_price = price

    # ── 조회 ──────────────────────────────────────────────

    @property
    def total_unrealized_pnl(self) -> int:
        return sum(p.unrealized_pnl for p in self._positions.values())

    @property
    def total_market_value(self) -> int:
        return sum(p.market_value for p in self._positions.values())

    @property
    def total_equity(self) -> int:
        return self.cash + self.total_market_value

    @property
    def today_pnl(self) -> int:
        return self._today_realized_pnl + self.total_unrealized_pnl

    def get_position(self, ticker: str) -> Optional[Position]:
        return self._positions.get(ticker)

    def print_summary(self) -> None:
        """포트폴리오 현황 출력."""
        print("\n" + "=" * 60)
        print(f"{'포트폴리오 현황':^60}")
        print("=" * 60)
        print(f"  초기 자본:    {self.initial_capital:>15,}원")
        print(f"  현금 잔고:    {self.cash:>15,}원")
        print(f"  평가 자산:    {self.total_market_value:>15,}원")
        print(f"  총 자산:      {self.total_equity:>15,}원")
        print(f"  실현 손익:    {self._realized_pnl:>+15,}원")
        print(f"  미실현 손익:  {self.total_unrealized_pnl:>+15,}원")
        print(f"  당일 손익:    {self.today_pnl:>+15,}원")
        if self._positions:
            print("-" * 60)
            print(f"  {'종목':^8} {'수량':>6} {'평단가':>10} {'현재가':>10} {'손익':>12} {'수익률':>8}")
            print("-" * 60)
            for p in self._positions.values():
                print(
                    f"  {p.ticker:^8} {p.qty:>6,} {p.avg_price:>10,} "
                    f"{p.current_price:>10,} {p.unrealized_pnl:>+12,} {p.unrealized_pnl_pct:>7.2f}%"
                )
        print("=" * 60 + "\n")

    def _refresh_today_pnl(self, realized: int) -> None:
        today = datetime.now(tz=config.KST).date()
        if self._today_date != today:
            self._today_date = today
            self._today_realized_pnl = 0
        self._today_realized_pnl += realized
