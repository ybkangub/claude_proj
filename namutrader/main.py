"""
main.py — 자동매매 시스템 진입점
사용법: python main.py --mode paper | python main.py --mode live
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from typing import Optional

import schedule

# 로거 먼저 설정
from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="나무증권 자동매매 시스템")
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="실행 모드 (기본값: paper)",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=["005930"],  # 삼성전자
        help="거래 종목 코드 리스트",
    )
    parser.add_argument(
        "--capital",
        type=int,
        default=10_000_000,
        help="초기 자본금 (원, 기본값: 1000만원)",
    )
    parser.add_argument(
        "--strategy",
        choices=["ma", "rsi"],
        default="ma",
        help="사용할 전략 (기본값: ma)",
    )
    return parser.parse_args()


def confirm_live_mode() -> bool:
    """라이브 모드 전환 전 사용자 재확인."""
    print("\n" + "!" * 60)
    print("  ⚠️  경고: 라이브 트레이딩 모드")
    print("  실제 주문이 발송됩니다. 계속하시겠습니까?")
    print("!" * 60)
    answer = input("  'LIVE' 를 입력하면 계속합니다: ").strip()
    return answer == "LIVE"


def build_strategy(name: str):
    if name == "ma":
        from strategy.ma_crossover import MovingAverageCrossover
        return MovingAverageCrossover(short_window=5, long_window=20)
    from strategy.rsi_strategy import RSIStrategy
    return RSIStrategy(period=14, oversold=30, overbought=70)


def main() -> None:
    args = parse_args()

    # .env PAPER_TRADING 값과 인수 교차 검증
    import config
    if args.mode == "live":
        if config.PAPER_TRADING:
            print("오류: .env의 PAPER_TRADING=true 상태에서 --mode live 실행 불가.")
            print("       .env에서 PAPER_TRADING=false 로 변경 후 재실행하세요.")
            sys.exit(1)
        if not confirm_live_mode():
            print("라이브 모드 취소.")
            sys.exit(0)
    else:
        # paper 모드 강제 보장
        if not config.PAPER_TRADING:
            logger.warning("--mode paper 지정됐으나 .env PAPER_TRADING=false — 페이퍼 모드로 강제 설정")
            config.PAPER_TRADING = True

    logger.info("=" * 50)
    logger.info("나무증권 자동매매 시스템 시작 [%s 모드]", args.mode.upper())
    logger.info("종목: %s | 전략: %s | 자본: %s원", args.tickers, args.strategy, f"{args.capital:,}")
    logger.info("=" * 50)

    # ── 컴포넌트 초기화 ─────────────────────────────────
    from api.auth import token_manager
    from api.market_data import MarketDataHandler
    from engine.order_manager import OrderManager
    from engine.position_manager import PositionManager
    from engine.risk_manager import RiskManager
    from utils.scheduler import KoreanMarketScheduler

    token_manager.issue_token()

    market = MarketDataHandler()
    position_mgr = PositionManager(initial_capital=args.capital)
    risk_mgr = RiskManager(position_manager=position_mgr)
    order_mgr = OrderManager()
    order_mgr.set_risk_manager(risk_mgr)
    strategy = build_strategy(args.strategy)
    scheduler = KoreanMarketScheduler()

    # ── 실시간 시세 구독 ─────────────────────────────────
    def on_tick(snapshot):
        position_mgr.update_price(snapshot.ticker, snapshot.price)

    market.subscribe_realtime(args.tickers, on_tick)

    # ── 장 시작/마감 훅 ─────────────────────────────────
    def on_market_open():
        risk_mgr.reset_daily_halt()
        logger.info("장 시작 — 일일 리스크 한도 초기화")

    def on_market_close():
        position_mgr.print_summary()
        logger.info("장 마감 — 포트폴리오 현황 출력")

    scheduler.run_at_open(on_market_open)
    scheduler.run_at_close(on_market_close)

    # ── 전략 실행 루프 ───────────────────────────────────
    def run_strategy():
        for ticker in args.tickers:
            try:
                df = market.get_ohlcv(ticker, period="D", count=60)
                signal = strategy.generate_signal(df)
                logger.info("[%s] 신호: %s", ticker, signal.value)

                current_price = df["close"].iloc[-1]
                pos = position_mgr.get_position(ticker)

                if signal.value == "BUY" and pos is None:
                    qty = int(position_mgr.cash * config.MAX_POSITION_PCT // current_price)
                    if qty > 0:
                        order_mgr.submit_order(ticker, "BUY", qty, current_price, "LIMIT")

                elif signal.value == "SELL" and pos is not None:
                    order_mgr.submit_order(ticker, "SELL", pos.qty, current_price, "LIMIT")

            except Exception as exc:
                logger.error("[%s] 전략 오류: %s", ticker, exc, exc_info=True)

    scheduler.run_every(config.RUN_INTERVAL_SECONDS, run_strategy, market_only=True)

    # ── Graceful Shutdown ────────────────────────────────
    open_orders: list = []

    def graceful_shutdown(signum: int, frame: Optional[object]) -> None:
        logger.info("종료 신호 수신 — 정리 중...")
        order_mgr.cancel_all_open_orders(open_orders)
        market.stop()
        position_mgr.print_summary()
        logger.info("자동매매 시스템 종료")
        sys.exit(0)

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # ── 메인 루프 ────────────────────────────────────────
    logger.info("메인 루프 시작 (Ctrl+C 로 종료)")
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
