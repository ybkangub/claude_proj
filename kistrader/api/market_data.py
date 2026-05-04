"""
market_data.py — KIS OHLCV 조회 및 WebSocket 실시간 시세
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

import pandas as pd
import requests
import websocket

import config
from api.auth import token_manager

logger = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    ticker: str
    price: int
    volume: int
    timestamp: datetime


class MarketDataHandler:
    def __init__(self) -> None:
        self._ws: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None
        self._on_tick: Callable[[PriceSnapshot], None] | None = None
        self._subscribed_tickers: list[str] = []

    # ── OHLCV 조회 ───────────────────────────────────────

    def get_ohlcv(self, ticker: str, count: int = 60) -> pd.DataFrame:
        end_dt = datetime.now(config.KST)
        start_dt = end_dt - timedelta(days=count * 2)  # 영업일 여유분 포함

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start_dt.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_dt.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        resp = requests.get(
            url,
            headers=token_manager.get_headers("FHKST03010100"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("rt_cd") != "0":
            raise RuntimeError(f"OHLCV 조회 실패: {data.get('msg1', '')}")

        rows = data.get("output2", [])
        if not rows:
            raise RuntimeError(f"[{ticker}] OHLCV 데이터 없음")

        df = pd.DataFrame(rows)
        df = df.rename(columns={
            "stck_bsop_date": "date",
            "stck_oprc": "open",
            "stck_hgpr": "high",
            "stck_lwpr": "low",
            "stck_clpr": "close",
            "acml_vol": "volume",
        })[["date", "open", "high", "low", "close", "volume"]]

        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df = df.set_index("date").sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(int)

        return df.tail(count)

    # ── WebSocket 실시간 시세 ────────────────────────────

    def subscribe_realtime(
        self, tickers: list[str], on_tick: Callable[[PriceSnapshot], None]
    ) -> None:
        self._on_tick = on_tick
        self._subscribed_tickers = tickers

        try:
            approval_key = token_manager.issue_ws_approval_key()
        except Exception as exc:
            logger.warning("WebSocket 승인키 발급 실패 — 실시간 시세 비활성화: %s", exc)
            return

        def on_open(ws: websocket.WebSocketApp) -> None:
            for ticker in tickers:
                sub_msg = {
                    "header": {
                        "approval_key": approval_key,
                        "custtype": "P",
                        "tr_type": "1",
                        "content-type": "utf-8",
                    },
                    "body": {
                        "input": {
                            "tr_id": "H0STCNT0",
                            "tr_key": ticker,
                        }
                    },
                }
                ws.send(json.dumps(sub_msg))
                logger.info("[WebSocket] %s 실시간 시세 구독", ticker)

        def on_message(ws: websocket.WebSocketApp, message: str) -> None:
            try:
                if message.startswith("{"):
                    # PINGPONG or 시스템 메시지
                    return
                parts = message.split("|")
                if len(parts) < 4:
                    return
                tr_id, _, _, body = parts[0], parts[1], parts[2], parts[3]
                if tr_id != "H0STCNT0":
                    return
                fields = body.split("^")
                # KIS H0STCNT0 필드 순서: 0=MKSC_SHRN_ISCD, 2=STCK_PRPR, 12=CNTG_VOL
                snap = PriceSnapshot(
                    ticker=fields[0],
                    price=int(fields[2]),
                    volume=int(fields[12]),
                    timestamp=datetime.now(config.KST),
                )
                if self._on_tick:
                    self._on_tick(snap)
            except Exception as exc:
                logger.debug("WebSocket 메시지 파싱 오류: %s", exc)

        def on_error(ws: websocket.WebSocketApp, error: Exception) -> None:
            logger.error("WebSocket 오류: %s", error)

        def on_close(ws: websocket.WebSocketApp, code: int, msg: str) -> None:
            logger.info("WebSocket 연결 종료 (code=%s)", code)

        self._ws = websocket.WebSocketApp(
            config.WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever, daemon=True
        )
        self._ws_thread.start()
        logger.info("WebSocket 연결 시작: %s", config.WS_URL)

    def stop(self) -> None:
        if self._ws:
            self._ws.close()
