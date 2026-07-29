from __future__ import annotations

import argparse
import json
import grp
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bybit_market_data import BybitMarketDataConfig, BybitMarketDataFeed
from app.candidate_runtime import (
    CandidateConfig,
    CandidateStateStore,
    ensure_paper_only,
    process_candidate_candles,
)
from app.process_lock import ProcessAlreadyRunningError, ProcessLock


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run isolated Strategy V2 paper candidate")
    result.add_argument("--state", type=Path, default=PROJECT_ROOT / "state/bybit_candidate_controller.json")
    result.add_argument("--trades", type=Path, default=PROJECT_ROOT / "state/bybit_candidate_trades.jsonl")
    result.add_argument("--decisions", type=Path, default=PROJECT_ROOT / "state/bybit_candidate_decisions.jsonl")
    result.add_argument("--lock-file", type=Path, default=PROJECT_ROOT / "state/bybit_candidate.lock")
    result.add_argument("--summary", type=Path, default=PROJECT_ROOT / "state/bybit_candidate_runtime.json")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    ensure_paper_only()
    config = CandidateConfig()
    try:
        with ProcessLock(args.lock_file):
            candles = BybitMarketDataFeed(
                BybitMarketDataConfig(
                    symbol=config.symbol,
                    interval=config.timeframe,
                    category="spot",
                    limit=500,
                    closed_candles_only=True,
                )
            ).get_candles()
            state = process_candidate_candles(
                candles,
                state_store=CandidateStateStore(args.state),
                trade_journal_path=args.trades,
                decision_journal_path=args.decisions,
                config=config,
            )
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            args.summary.write_text(
                json.dumps(
                    {
                        "mode": "paper",
                        "live_trading_enabled": False,
                        "strategy": "ADX_HYBRID_PULLBACK",
                        "parameters": {
                            "max_wait_bars": config.max_wait_bars,
                            "tolerance": config.tolerance,
                            "retrace_pct": config.retrace_pct,
                            "adx_minimum": config.adx_minimum,
                        },
                        "last_processed_candle": state.last_processed_candle,
                        "balance": str(state.controller.virtual_balance),
                        "position": (
                            "LONG" if state.controller.has_open_position else "FLAT"
                        ),
                        "active_halt": state.active_halt,
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            try:
                runtime_gid = grp.getgrnam("crypto-bot-runtime").gr_gid
            except KeyError:
                runtime_gid = None
            for path in (
                args.state, args.trades, args.decisions, args.lock_file,
                args.summary,
            ):
                if path.exists():
                    os.chmod(path, 0o640)
                    if runtime_gid is not None:
                        os.chown(path, -1, runtime_gid)
    except ProcessAlreadyRunningError as exc:
        print(f"Candidate already running: {exc}", file=sys.stderr)
        return 2
    print(
        "Candidate paper: strategy=ADX+HYBRID_PULLBACK "
        f"last_candle={state.last_processed_candle} "
        f"balance={state.controller.virtual_balance} "
        f"position={'LONG' if state.controller.has_open_position else 'FLAT'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
