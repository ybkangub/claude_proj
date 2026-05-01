"""
ma_crossover.py — 이동평균 골든/데드크로스 전략 (MA5 / MA20)
"""

from __future__ import annotations

import logging

import pandas as pd

from strategy.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class MovingAverageCrossover(BaseStrategy):
    """
    단기 MA가 장기 MA를 상향 돌파 → BUY (골든크로스)
    단기 MA가 장기 MA를 하향 돌파 → SELL (데드크로스)
    그 외 → HOLD
    """

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        super().__init__(name=f"MA{short_window}/{long_window} Crossover")
        self.short_window = short_window
        self.long_window = long_window

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """
        이동평균 크로스오버 신호 생성.

        Args:
            df: OHLCV DataFrame (최신 데이터가 마지막 행)

        Returns:
            Signal.BUY | Signal.SELL | Signal.HOLD
        """
        self.validate_data(df, min_rows=self.long_window + 1)

        close = df["close"].astype(float)
        ma_short = close.rolling(self.short_window).mean()
        ma_long = close.rolling(self.long_window).mean()

        # 현재 봉과 직전 봉의 MA 위치 비교
        prev_short = ma_short.iloc[-2]
        prev_long = ma_long.iloc[-2]
        curr_short = ma_short.iloc[-1]
        curr_long = ma_long.iloc[-1]

        if pd.isna(prev_short) or pd.isna(prev_long) or pd.isna(curr_short) or pd.isna(curr_long):
            return Signal.HOLD

        golden_cross = (prev_short <= prev_long) and (curr_short > curr_long)
        dead_cross = (prev_short >= prev_long) and (curr_short < curr_long)

        if golden_cross:
            logger.info("[%s] 골든크로스 감지 → BUY (MA%d=%.1f, MA%d=%.1f)",
                        self.name, self.short_window, curr_short, self.long_window, curr_long)
            return Signal.BUY

        if dead_cross:
            logger.info("[%s] 데드크로스 감지 → SELL (MA%d=%.1f, MA%d=%.1f)",
                        self.name, self.short_window, curr_short, self.long_window, curr_long)
            return Signal.SELL

        return Signal.HOLD
