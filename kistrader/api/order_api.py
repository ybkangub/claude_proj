"""
order_api.py — KIS 주식 주문/취소/조회 REST API
"""
from __future__ import annotations

import logging

import requests

import config
from api.auth import token_manager

logger = logging.getLogger(__name__)

# tr_id 매핑: (side, paper) → tr_id
_ORDER_TR = {
    ("BUY",  True):  "VTTC0802U",
    ("BUY",  False): "TTTC0802U",
    ("SELL", True):  "VTTC0801U",
    ("SELL", False): "TTTC0801U",
}
_CANCEL_TR = {True: "VTTC0803U", False: "TTTC0803U"}


class KISOrderAPI:
    def place_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        price: int,
        order_type: str = "LIMIT",
    ) -> str:
        tr_id = _ORDER_TR[(side.upper(), config.PAPER_TRADING)]
        ord_dvsn = "01" if order_type.upper() == "MARKET" else "00"
        ord_unpr = 0 if ord_dvsn == "01" else price

        body = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(ord_unpr),
        }
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"
        resp = requests.post(
            url,
            headers=token_manager.get_headers(tr_id),
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("rt_cd") != "0":
            raise RuntimeError(f"주문 실패: {data.get('msg1', '')}")

        order_id: str = data["output"]["ODNO"]
        logger.info("[%s] %s %d주 @ %d원 → 주문번호 %s", ticker, side, qty, price, order_id)
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        tr_id = _CANCEL_TR[config.PAPER_TRADING]
        body = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_id,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
        }
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        resp = requests.post(
            url,
            headers=token_manager.get_headers(tr_id),
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        success = data.get("rt_cd") == "0"
        if success:
            logger.info("주문 취소 성공: %s", order_id)
        else:
            logger.warning("주문 취소 실패: %s — %s", order_id, data.get("msg1", ""))
        return success

    def get_order_status(self, order_id: str) -> dict:
        params = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0",
        }
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        tr_id = "TTTC8036R" if not config.PAPER_TRADING else "VTTC8036R"
        resp = requests.get(
            url,
            headers=token_manager.get_headers(tr_id),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        orders = data.get("output", [])
        for o in orders:
            if o.get("odno") == order_id:
                return o
        return {"odno": order_id, "ord_qty": "0", "tot_ccld_qty": "0"}


order_api = KISOrderAPI()
