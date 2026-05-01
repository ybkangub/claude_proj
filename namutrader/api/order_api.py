"""
order_api.py — 주문 REST API 래퍼 (시장가 / 지정가)
PAPER_TRADING=true 시 실제 API 호출 없이 mock 응답 반환.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

import requests

import config
from api.auth import token_manager

logger = logging.getLogger(__name__)

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]

# ⚠️ API SPEC NEEDED: 주문 엔드포인트 확인 필요
_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
# ⚠️ API SPEC NEEDED: 주문 취소 엔드포인트 확인 필요
_CANCEL_PATH = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
# ⚠️ API SPEC NEEDED: 주문 조회 엔드포인트 확인 필요
_STATUS_PATH = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"


class OrderAPI:
    """나무증권 주문 API."""

    def place_order(
        self,
        ticker: str,
        side: OrderSide,
        qty: int,
        price: int,
        order_type: OrderType = "LIMIT",
    ) -> str:
        """
        주문 발송.

        Args:
            ticker: 종목코드
            side: "BUY" | "SELL"
            qty: 주문 수량
            price: 주문 가격 (시장가 시 0)
            order_type: "MARKET" | "LIMIT"

        Returns:
            order_id (주문번호)
        """
        if config.PAPER_TRADING:
            return self._mock_place_order(ticker, side, qty, price, order_type)

        # ⚠️ API SPEC NEEDED: tr_id, 요청 body 필드명 확인 필요
        tr_id = "TTTC0802U" if side == "BUY" else "TTTC0801U"
        ord_dvsn = "01" if order_type == "MARKET" else "00"  # 01=시장가, 00=지정가

        payload = {
            "CANO": config.ACCOUNT_NO[:8],
            "ACNT_PRDT_CD": config.ACCOUNT_NO[8:],
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price if order_type == "LIMIT" else 0),
        }
        headers = {**token_manager.get_headers(), "tr_id": tr_id}

        try:
            resp = requests.post(
                config.BASE_URL + _ORDER_PATH,
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("주문 실패 [%s %s %s]: %s", side, ticker, qty, exc)
            raise

        # ⚠️ API SPEC NEEDED: 응답에서 주문번호 필드 확인 필요
        order_id: str = data.get("output", {}).get("ODNO", str(uuid.uuid4()))
        logger.info("주문 접수: order_id=%s %s %s qty=%d price=%d", order_id, side, ticker, qty, price)
        return order_id

    def cancel_order(self, order_id: str, ticker: str, qty: int) -> bool:
        """
        미체결 주문 취소.

        Args:
            order_id: 주문번호
            ticker: 종목코드
            qty: 취소 수량

        Returns:
            취소 성공 여부
        """
        if config.PAPER_TRADING:
            logger.info("[PAPER] 주문 취소: order_id=%s", order_id)
            return True

        # ⚠️ API SPEC NEEDED: 취소 요청 body 필드명 확인 필요
        payload = {
            "CANO": config.ACCOUNT_NO[:8],
            "ACNT_PRDT_CD": config.ACCOUNT_NO[8:],
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_id,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 02=취소
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
        }
        headers = {**token_manager.get_headers(), "tr_id": "TTTC0803U"}

        try:
            resp = requests.post(
                config.BASE_URL + _CANCEL_PATH,
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("주문 취소 완료: order_id=%s", order_id)
            return True
        except requests.RequestException as exc:
            logger.error("주문 취소 실패 [%s]: %s", order_id, exc)
            return False

    def get_order_status(self, order_id: str) -> dict:
        """
        주문 상태 조회.

        Returns:
            dict with keys: order_id, status ("FILLED"|"PARTIAL"|"PENDING"|"CANCELLED"), filled_qty, avg_price
        """
        if config.PAPER_TRADING:
            return {
                "order_id": order_id,
                "status": "FILLED",
                "filled_qty": 0,
                "avg_price": 0,
            }

        # ⚠️ API SPEC NEEDED: 조회 파라미터/응답 구조 확인 필요
        params = {
            "CANO": config.ACCOUNT_NO[:8],
            "ACNT_PRDT_CD": config.ACCOUNT_NO[8:],
            "ODNO": order_id,
        }
        headers = {**token_manager.get_headers(), "tr_id": "TTTC8036R"}

        try:
            resp = requests.get(
                config.BASE_URL + _STATUS_PATH,
                headers=headers,
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("output", {})
        except requests.RequestException as exc:
            logger.error("주문 상태 조회 실패 [%s]: %s", order_id, exc)
            return {"order_id": order_id, "status": "UNKNOWN", "filled_qty": 0, "avg_price": 0}

        return {
            "order_id": order_id,
            # ⚠️ API SPEC NEEDED: 상태 코드 매핑 확인 필요
            "status": data.get("ord_stts", "UNKNOWN"),
            "filled_qty": int(data.get("tot_ccld_qty", 0)),
            "avg_price": int(data.get("avg_prvs", 0)),
        }

    def _mock_place_order(
        self,
        ticker: str,
        side: OrderSide,
        qty: int,
        price: int,
        order_type: OrderType,
    ) -> str:
        """페이퍼 트레이딩 mock 주문."""
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        logger.info(
            "[PAPER] 주문 접수: order_id=%s %s %s qty=%d price=%d type=%s",
            order_id, side, ticker, qty, price, order_type,
        )
        return order_id


order_api = OrderAPI()
