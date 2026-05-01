"""
market_data.py — 시세 조회 (REST OHLCV + WebSocket 실시간)
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import pandas as pd
import requests
import websocket

import config
from api.auth import token_manager

logger = logging.getLogger(__name__)

# ⚠️ API SPEC NEEDED: OHLCV 조회 엔드포인트 확인 필요
_OHLCV_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
# ⚠️ API SPEC NEEDED: 분봉 조회 엔드포인트 확인 필요
_MINUTE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"


@dataclass
class PriceSnapshot:
    """실시간 체결 데이터 스냅샷."""
    ticker: str
    price: int          # 현재가 (원, 정수)
    volume: int         # 누적 체결량
    bid: int            # 매수 1호가
    ask: int            # 매도 1호가
    timestamp: datetime # KST


class MarketDataHandler:
    """REST OHLCV 조회 및 WebSocket 실시간 시세 수신."""

    def __init__(self) -> None:
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._subscribed_tickers: list[str] = []
        self._on_tick_callback: Optional[Callable[[PriceSnapshot], None]] = None

    # ── REST: 과거 데이터 ──────────────────────────────────

    def get_ohlcv(
        self,
        ticker: str,
        period: str = "D",
        count: int = 100,
    ) -> pd.DataFrame:
        """
        OHLCV 데이터 조회.

        Args:
            ticker: 종목코드 (예: "005930" 삼성전자)
            period: "D"=일봉, "W"=주봉, "M"=월봉, "1"=1분봉, "5"=5분봉
            count: 조회 개수

        Returns:
            DataFrame (index=KST datetime, columns=open/high/low/close/volume, dtype=int)
        """
        if config.PAPER_TRADING:
            return self._mock_ohlcv(ticker, count)

        # ⚠️ API SPEC NEEDED: 실제 파라미터명/응답 구조 확인 필요
        path = _MINUTE_PATH if period.isdigit() else _OHLCV_PATH
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": ticker,
            "fid_org_adj_prc": "1",
            "fid_period_div_code": period,
        }

        try:
            resp = requests.get(
                config.BASE_URL + path,
                headers=token_manager.get_headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("OHLCV 조회 실패 [%s]: %s", ticker, exc)
            raise

        return self._parse_ohlcv(data, count)

    def _parse_ohlcv(self, data: dict, count: int) -> pd.DataFrame:
        """API 응답을 DataFrame으로 변환."""
        # ⚠️ API SPEC NEEDED: 실제 응답 키 이름 확인 필요
        rows = data.get("output2", data.get("output", []))[:count]
        records = []
        for row in rows:
            try:
                records.append({
                    "datetime": pd.to_datetime(
                        row.get("stck_bsop_date", row.get("date", "")),
                        format="%Y%m%d",
                    ).tz_localize(config.KST),
                    "open":   int(row.get("stck_oprc", row.get("open", 0))),
                    "high":   int(row.get("stck_hgpr", row.get("high", 0))),
                    "low":    int(row.get("stck_lwpr", row.get("low", 0))),
                    "close":  int(row.get("stck_clpr", row.get("close", 0))),
                    "volume": int(row.get("acml_vol",  row.get("volume", 0))),
                })
            except (ValueError, KeyError) as exc:
                logger.warning("OHLCV 행 파싱 오류: %s", exc)

        if not records:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(records).set_index("datetime").sort_index()
        return df

    def _mock_ohlcv(self, ticker: str, count: int) -> pd.DataFrame:
        """페이퍼 트레이딩용 mock OHLCV 데이터 생성."""
        import numpy as np

        rng = pd.date_range(end=pd.Timestamp.now(tz=config.KST), periods=count, freq="B")
        close = (np.random.randn(count).cumsum() * 1000 + 70000).astype(int).clip(1000)
        df = pd.DataFrame({
            "open":   (close * 0.99).astype(int),
            "high":   (close * 1.02).astype(int),
            "low":    (close * 0.98).astype(int),
            "close":  close,
            "volume": np.random.randint(100_000, 1_000_000, count),
        }, index=rng)
        logger.debug("Mock OHLCV 생성: ticker=%s count=%d", ticker, count)
        return df

    # ── WebSocket: 실시간 시세 ─────────────────────────────

    def subscribe_realtime(
        self,
        tickers: list[str],
        on_tick: Callable[[PriceSnapshot], None],
    ) -> None:
        """
        실시간 현재가 WebSocket 구독 시작 (별도 스레드).

        Args:
            tickers: 구독할 종목코드 리스트
            on_tick: 체결 데이터 수신 시 호출되는 콜백
        """
        self._subscribed_tickers = tickers
        self._on_tick_callback = on_tick

        if config.PAPER_TRADING:
            logger.info("[PAPER] WebSocket 구독 생략 (페이퍼 트레이딩 모드)")
            return

        self._ws = websocket.WebSocketApp(
            config.WS_URL,
            header=self._ws_headers(),
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 30, "ping_timeout": 10},
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("WebSocket 연결 시작: %s", tickers)

    def _ws_headers(self) -> list[str]:
        headers = token_manager.get_headers()
        return [f"{k}: {v}" for k, v in headers.items()]

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        """WebSocket 연결 후 종목 구독 메시지 전송."""
        for ticker in self._subscribed_tickers:
            # ⚠️ API SPEC NEEDED: 구독 요청 메시지 형식 확인 필요
            msg = json.dumps({
                "header": {"approval_key": token_manager.get_valid_token(), "custtype": "P"},
                "body": {
                    "input": {"tr_id": "H0STCNT0", "tr_key": ticker},
                },
            })
            ws.send(msg)
            logger.info("실시간 구독 요청: %s", ticker)

    def _on_message(self, ws: websocket.WebSocketApp, raw: str) -> None:
        """수신 메시지 파싱 후 콜백 호출."""
        try:
            # ⚠️ API SPEC NEEDED: WebSocket 응답 포맷 확인 필요
            data = json.loads(raw)
            body = data.get("body", {})
            output = body.get("output", {})

            snapshot = PriceSnapshot(
                ticker=output.get("mksc_shrn_iscd", ""),
                price=int(output.get("stck_prpr", 0)),
                volume=int(output.get("acml_vol", 0)),
                bid=int(output.get("askp1", 0)),
                ask=int(output.get("bidp1", 0)),
                timestamp=datetime.now(tz=config.KST),
            )
            if self._on_tick_callback and snapshot.ticker:
                self._on_tick_callback(snapshot)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("WebSocket 메시지 파싱 오류: %s", exc)

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        logger.error("WebSocket 오류: %s", error)

    def _on_close(
        self,
        ws: websocket.WebSocketApp,
        close_status_code: Optional[int],
        close_msg: Optional[str],
    ) -> None:
        logger.warning("WebSocket 연결 종료: %s %s", close_status_code, close_msg)

    def stop(self) -> None:
        """WebSocket 연결 종료."""
        if self._ws:
            self._ws.close()
            logger.info("WebSocket 연결 종료")
