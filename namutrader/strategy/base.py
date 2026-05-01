"""
base.py — 전략 베이스 클래스 및 Signal 열거형
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class BaseStrategy(ABC):
    """모든 매매 전략의 추상 베이스 클래스."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> Signal:
        """
        OHLCV DataFrame을 받아 매매 신호 반환.

        Args:
            df: OHLCV DataFrame (index=KST datetime, columns=open/high/low/close/volume)
                최신 데이터가 마지막 행.

        Returns:
            Signal.BUY | Signal.SELL | Signal.HOLD
        """

    def validate_data(self, df: pd.DataFrame, min_rows: int) -> None:
        """
        데이터 유효성 검증.

        Raises:
            ValueError: 데이터 부족 또는 필수 컬럼 없음
        """
        if df.empty or len(df) < min_rows:
            raise ValueError(
                f"[{self.name}] 데이터 부족: {len(df)}행 (최소 {min_rows}행 필요)"
            )
        missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
        if missing:
            raise ValueError(f"[{self.name}] 누락된 컬럼: {missing}")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
