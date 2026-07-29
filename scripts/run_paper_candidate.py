from __future__ import annotations

import argparse
import json
import grp
import os
from decimal import Decimal
from datetime import datetime, timezone
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
from app.equity_history import (
    SnapshotService,
    SnapshotStorage,
    load_equity_history_config,
    read_trades as read_equity_trades,
)


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
            before_state = CandidateStateStore(args.state).load()
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
            if (
                state.last_processed_candle is not None
                and state.last_processed_candle
                == before_state.last_processed_candle
            ):
                try:
                    history_config = load_equity_history_config(
                        PROJECT_ROOT / "config/equity_history.json",
                        root=PROJECT_ROOT,
                    )
                    history_storage = SnapshotStorage(
                        history_config.database_path
                    )
                    history_service = SnapshotService(
                        history_storage, history_config
                    )
                    candle_close = (
                        state.last_processed_candle
                        + int(config.timeframe) * 60
                    )
                    if not history_storage.has_candle(
                        "candidate", "candidate_adx_hybrid", candle_close
                    ):
                        price = next(
                            Decimal(str(item.close))
                            for item in reversed(candles)
                            if item.timestamp == state.last_processed_candle
                        )
                        recovered, _ = history_service.capture(
                            environment="candidate",
                            strategy_name="candidate_adx_hybrid",
                            state=state.controller,
                            trades=read_equity_trades(args.trades),
                            market_price=price,
                            candle_open_timestamp=state.last_processed_candle,
                            timeframe_minutes=int(config.timeframe),
                            symbol=config.symbol,
                            reason="startup_recovery",
                            source_cycle_id=(
                                "candidate_adx_hybrid:"
                                f"{state.last_processed_candle}:recovery"
                            ),
                        )
                        if recovered is not None:
                            history_service.maybe_daily_close(
                                recovered, now=datetime.now(timezone.utc)
                            )
                    else:
                        existing = history_storage.latest("candidate")
                        if existing is not None:
                            history_service.maybe_daily_close(
                                existing, now=datetime.now(timezone.utc)
                            )
                except Exception as exc:
                    print(
                        "Equity history observer warning: "
                        f"{type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
            if (
                state.last_processed_candle is not None
                and state.last_processed_candle
                != before_state.last_processed_candle
            ):
                try:
                    history_config = load_equity_history_config(
                        PROJECT_ROOT / "config/equity_history.json",
                        root=PROJECT_ROOT,
                    )
                    service = SnapshotService(
                        SnapshotStorage(history_config.database_path),
                        history_config,
                    )
                    price = next(
                        Decimal(str(item.close))
                        for item in reversed(candles)
                        if item.timestamp == state.last_processed_candle
                    )
                    cycle_snapshot, _ = service.capture(
                        environment="candidate",
                        strategy_name="candidate_adx_hybrid",
                        state=state.controller,
                        trades=read_equity_trades(args.trades),
                        market_price=price,
                        candle_open_timestamp=state.last_processed_candle,
                        timeframe_minutes=int(config.timeframe),
                        symbol=config.symbol, reason="cycle",
                        source_cycle_id=(
                            f"candidate_adx_hybrid:{state.last_processed_candle}"
                        ),
                    )
                    if cycle_snapshot is not None:
                        service.maybe_daily_close(
                            cycle_snapshot, now=datetime.now(timezone.utc)
                        )
                    if (
                        before_state.controller.has_open_position
                        != state.controller.has_open_position
                    ):
                        service.capture(
                            environment="candidate",
                            strategy_name="candidate_adx_hybrid",
                            state=state.controller,
                            trades=read_equity_trades(args.trades),
                            market_price=price,
                            candle_open_timestamp=state.last_processed_candle,
                            timeframe_minutes=int(config.timeframe),
                            symbol=config.symbol,
                            reason=(
                                "trade_open"
                                if state.controller.has_open_position
                                else "trade_close"
                            ),
                            source_cycle_id=(
                                "candidate_adx_hybrid:"
                                f"{state.last_processed_candle}:trade"
                            ),
                        )
                except Exception as exc:
                    print(
                        "Equity history observer warning: "
                        f"{type(exc).__name__}: {exc}",
                        file=sys.stderr,
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
