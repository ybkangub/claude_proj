"""
rsi_strategy.py — RSI 과매수/과매도 전략 (RSI 14)
"""

from __future__ import annotations

import logging

import pandas as pd

from strategy.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


def _calc_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI 계산 (pandas_ta 없이 순수 pandas 구현)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing (EWM with alpha=1/period)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    # avg_loss=0 이면 손실 없음 → RSI=100
    rsi = 100 - (100 / (1 + avg_gain / avg_loss))
    return rsi.where(avg_loss != 0, 100.0)


class RSIStrategy(BaseStrategy):
    """
    RSI < oversold  → BUY  (과매도 구간 진입)
    RSI > overbought → SELL (과매수 구간 진입)
    그 외           → HOLD
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> None:
        super().__init__(name=f"RSI{period} ({oversold}/{overbought})")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """
        RSI 기반 신호 생성.

        Args:
            df: OHLCV DataFrame (최신 데이터가 마지막 행)

        Returns:
            Signal.BUY | Signal.SELL | Signal.HOLD
        """
        self.validate_data(df, min_rows=self.period + 1)

        close = df["close"].astype(float)

        # pandas_ta 사용 시도, 없으면 내장 구현
        try:
            import pandas_ta as ta  # type: ignore[import]
            rsi_series = ta.rsi(close, length=self.period)
        except ImportError:
            rsi_series = _calc_rsi(close, self.period)

        current_rsi = rsi_series.iloc[-1]

        if pd.isna(current_rsi):
            return Signal.HOLD

        if current_rsi < self.oversold:
            logger.info("[%s] 과매도 구간 → BUY (RSI=%.2f)", self.name, current_rsi)
            return Signal.BUY

        if current_rsi > self.overbought:
            logger.info("[%s] 과매수 구간 → SELL (RSI=%.2f)", self.name, current_rsi)
            return Signal.SELL

        logger.debug("[%s] HOLD (RSI=%.2f)", self.name, current_rsi)
        return Signal.HOLD
