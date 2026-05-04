"""
order_manager.py — 주문 실행, pre-trade 검증, CSV 로깅
"""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import config
from api.order_api import OrderAPI, OrderSide, OrderType, order_api

logger = logging.getLogger(__name__)


class OrderManager:
    """pre-trade 검증 후 주문 발송 및 체결 모니터링."""

    def __init__(
        self,
        api: OrderAPI = order_api,
        orders_csv: str = config.ORDERS_CSV,
    ) -> None:
        self._api = api
        self._csv_path = Path(orders_csv)
        self._ensure_csv_header()
        self._risk_manager: Optional[object] = None  # RiskManager 주입 (순환 방지)

    def set_risk_manager(self, risk_manager: object) -> None:
        self._risk_manager = risk_manager

    # ── 주문 제출 ──────────────────────────────────────────

    def submit_order(
        self,
        ticker: str,
        side: OrderSide,
        qty: int,
        price: int,
        order_type: OrderType = "LIMIT",
    ) -> Optional[str]:
        """
        pre-trade 검증 통과 시 주문 발송.

        Returns:
            order_id (성공) 또는 None (거부)
        """
        if not self._check_market_hours(order_type):
            return None

        if self._risk_manager is not None:
            if not self._risk_manager.check_position_size(ticker, qty, price):  # type: ignore[union-attr]
                return None
            if not self._risk_manager.check_daily_loss():
                return None

        try:
            order_id = self._api.place_order(ticker, side, qty, price, order_type)
        except Exception as exc:
            logger.error("주문 발송 오류: %s", exc)
            self._log_order(ticker, side, qty, price, order_type, "ERROR")
            return None

        self._log_order(ticker, side, qty, price, order_type, "SUBMITTED", order_id)
        return order_id

    # ── 체결 확인 ──────────────────────────────────────────

    def poll_order_status(
        self,
        order_id: str,
        max_retries: int = 10,
        interval_seconds: float = 3.0,
    ) -> dict:
        """
        주문 체결 상태를 주기적으로 확인.

        Returns:
            최종 상태 dict (status, filled_qty, avg_price)
        """
        for attempt in range(max_retries):
            status = self._api.get_order_status(order_id)
            logger.debug("주문 상태 [%s] %d/%d: %s", order_id, attempt + 1, max_retries, status)

            if status["status"] in ("FILLED", "CANCELLED"):
                self._update_order_csv(order_id, status["status"])
                return status

            time.sleep(interval_seconds)

        logger.warning("주문 체결 확인 타임아웃: order_id=%s", order_id)
        return self._api.get_order_status(order_id)

    def cancel_all_open_orders(self, open_orders: list[dict]) -> None:
        """열린 주문 전량 취소 (graceful shutdown 시 호출)."""
        for order in open_orders:
            success = self._api.cancel_order(
                order["order_id"], order["ticker"], order["qty"]
            )
            if success:
                self._update_order_csv(order["order_id"], "CANCELLED")
                logger.info("주문 취소: %s", order["order_id"])

    # ── 장 시간 검증 ───────────────────────────────────────

    def _check_market_hours(self, order_type: OrderType) -> bool:
        """09:00~15:30 KST 내 주문만 허용. 시장가는 15:20까지."""
        now = datetime.now(tz=config.KST)
        weekday = now.weekday()
        if weekday >= 5:
            logger.warning("주문 거부: 주말 (%s)", now.strftime("%A"))
            return False

        open_t = now.replace(hour=config.MARKET_OPEN_HOUR, minute=config.MARKET_OPEN_MINUTE, second=0, microsecond=0)
        close_t = now.replace(hour=config.MARKET_CLOSE_HOUR, minute=config.MARKET_CLOSE_MINUTE, second=0, microsecond=0)

        if order_type == "MARKET":
            close_t = now.replace(
                hour=config.MARKET_ORDER_CUTOFF_HOUR,
                minute=config.MARKET_ORDER_CUTOFF_MINUTE,
                second=0, microsecond=0,
            )

        if now < open_t or now > close_t:
            logger.warning(
                "주문 거부: 장 시간 외 (%s) [허용: %s~%s KST]",
                now.strftime("%H:%M:%S"), open_t.strftime("%H:%M"), close_t.strftime("%H:%M"),
            )
            return False

        return True

    # ── CSV 로깅 ───────────────────────────────────────────

    def _ensure_csv_header(self) -> None:
        if not self._csv_path.exists():
            with self._csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "order_id", "ticker", "side",
                    "qty", "price", "order_type", "status",
                ])

    def _log_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        price: int,
        order_type: str,
        status: str,
        order_id: str = "",
    ) -> None:
        timestamp = datetime.now(tz=config.KST).isoformat()
        with self._csv_path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                timestamp, order_id, ticker, side, qty, price, order_type, status,
            ])

    def _update_order_csv(self, order_id: str, new_status: str) -> None:
        """CSV에서 order_id 행의 status 업데이트."""
        if not self._csv_path.exists():
            return
        rows = self._csv_path.read_text(encoding="utf-8").splitlines()
        updated = []
        for row in rows:
            if order_id in row and "SUBMITTED" in row:
                row = row.replace("SUBMITTED", new_status)
            updated.append(row)
        self._csv_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
