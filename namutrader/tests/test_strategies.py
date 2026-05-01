"""
test_strategies.py — 전략 신호 생성 단위 테스트
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# .env 없어도 테스트 가능하도록 더미 환경변수 설정
os.environ.setdefault("APP_KEY", "test_key")
os.environ.setdefault("APP_SECRET", "test_secret")
os.environ.setdefault("ACCOUNT_NO", "12345678901")
os.environ.setdefault("PAPER_TRADING", "true")

import numpy as np
import pandas as pd
import pytest
import pytz

from strategy.base import Signal
from strategy.ma_crossover import MovingAverageCrossover
from strategy.rsi_strategy import RSIStrategy

KST = pytz.timezone("Asia/Seoul")


def make_ohlcv(close_prices: list[float]) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성."""
    n = len(close_prices)
    close = np.array(close_prices, dtype=int)
    index = pd.date_range(end=pd.Timestamp.now(tz=KST), periods=n, freq="B")
    return pd.DataFrame({
        "open":   (close * 0.99).astype(int),
        "high":   (close * 1.01).astype(int),
        "low":    (close * 0.98).astype(int),
        "close":  close,
        "volume": np.full(n, 500_000),
    }, index=index)


# ── MovingAverageCrossover 테스트 ──────────────────────

class TestMovingAverageCrossover:
    def setup_method(self):
        self.strategy = MovingAverageCrossover(short_window=5, long_window=20)

    def test_golden_cross_returns_buy(self):
        """MA5가 MA20을 상향 돌파 → BUY."""
        # 처음 20개는 하락 추세 (MA5 < MA20), 이후 급등으로 골든크로스 유발
        prices = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91,
                  90, 89, 88, 87, 86, 85, 84, 83, 82, 81,
                  # 마지막 2개 급등 → MA5 상승
                  120, 130]
        df = make_ohlcv(prices)
        signal = self.strategy.generate_signal(df)
        assert signal == Signal.BUY

    def test_dead_cross_returns_sell(self):
        """MA5가 MA20을 하향 돌파 → SELL."""
        # 처음 20개는 상승 추세, 이후 급락
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                  110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                  80, 70]
        df = make_ohlcv(prices)
        signal = self.strategy.generate_signal(df)
        assert signal == Signal.SELL

    def test_no_cross_returns_hold(self):
        """크로스 없음 → HOLD."""
        prices = list(range(100, 125))  # 꾸준한 상승 (크로스 없음)
        df = make_ohlcv(prices)
        signal = self.strategy.generate_signal(df)
        assert signal == Signal.HOLD

    def test_insufficient_data_raises(self):
        """데이터 부족 시 ValueError."""
        df = make_ohlcv([100, 101, 102])
        with pytest.raises(ValueError, match="데이터 부족"):
            self.strategy.generate_signal(df)

    def test_signal_is_enum(self):
        prices = list(range(80, 105))
        df = make_ohlcv(prices)
        signal = self.strategy.generate_signal(df)
        assert isinstance(signal, Signal)


# ── RSIStrategy 테스트 ─────────────────────────────────

class TestRSIStrategy:
    def setup_method(self):
        self.strategy = RSIStrategy(period=14, oversold=30, overbought=70)

    def test_oversold_returns_buy(self):
        """RSI < 30 → BUY."""
        # 급격한 하락 시퀀스 → RSI 낮음
        prices = [100] * 5 + [95, 88, 80, 70, 60, 50, 42, 38, 35, 30, 25, 22, 20, 19, 18]
        df = make_ohlcv(prices)
        signal = self.strategy.generate_signal(df)
        assert signal == Signal.BUY

    def test_overbought_returns_sell(self):
        """RSI > 70 → SELL."""
        # 급격한 상승 시퀀스 → RSI 높음
        prices = [100] * 5 + [105, 112, 120, 130, 142, 155, 165, 172, 178, 183, 187, 190, 192, 194, 195]
        df = make_ohlcv(prices)
        signal = self.strategy.generate_signal(df)
        assert signal == Signal.SELL

    def test_neutral_returns_hold(self):
        """중립 구간 → HOLD."""
        prices = [100 + i % 3 for i in range(30)]  # 소폭 등락
        df = make_ohlcv(prices)
        signal = self.strategy.generate_signal(df)
        assert signal == Signal.HOLD

    def test_insufficient_data_raises(self):
        df = make_ohlcv([100, 101])
        with pytest.raises(ValueError):
            self.strategy.generate_signal(df)

    def test_custom_thresholds(self):
        """커스텀 임계값 적용 확인."""
        strategy = RSIStrategy(period=14, oversold=40, overbought=60)
        assert strategy.oversold == 40
        assert strategy.overbought == 60


# ── Signal 열거형 테스트 ───────────────────────────────

class TestSignal:
    def test_signal_values(self):
        assert Signal.BUY.value == "BUY"
        assert Signal.SELL.value == "SELL"
        assert Signal.HOLD.value == "HOLD"

    def test_signal_comparison(self):
        assert Signal.BUY != Signal.SELL
        assert Signal.HOLD == Signal.HOLD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
