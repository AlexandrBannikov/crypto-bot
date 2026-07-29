from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.equity_history import (
    SnapshotService,
    SnapshotStorage,
    load_equity_history_config,
    read_trades,
)
from app.trading_controller import TradingControllerState


PATHS = {
    "production": Path("state/controller_trade_journal.jsonl"),
    "candidate": Path("state/bybit_candidate_trades.jsonl"),
}
STRATEGIES = {
    "production": "production",
    "candidate": "candidate_adx_hybrid",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Safe confirmed-trade equity backfill")
    result.add_argument("--environment", required=True, choices=tuple(PATHS))
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    result.add_argument(
        "--config", type=Path, default=ROOT / "config/equity_history.json"
    )
    result.add_argument("--trades", type=Path)
    return result


def execute(args: argparse.Namespace) -> dict:
    environment = args.environment
    journal = args.trades or ROOT / PATHS[environment]
    try:
        trades = read_trades(journal)
    except (OSError, ValueError) as exc:
        return {
            "environment": environment, "mode": "apply" if args.apply else "dry-run",
            "source": str(journal), "confirmed_records": 0, "created": 0,
            "skipped": 0, "invalid": 1, "date_range": None,
            "reason": f"trade journal unavailable: {exc}",
        }
    report = {
        "environment": environment, "mode": "apply" if args.apply else "dry-run",
        "source": str(journal), "confirmed_records": len(trades),
        "created": 0, "skipped": 0, "invalid": 0,
        "date_range": (
            [trades[0].closed_at, trades[-1].closed_at] if trades else None
        ),
        "reason": (
            "only confirmed trade-close states are eligible; no artificial "
            "daily or open-position history is generated"
        ),
    }
    if not args.apply:
        config_root = (
            ROOT
            if args.config == ROOT / "config/equity_history.json"
            else args.config.parent
        )
        config = load_equity_history_config(args.config, root=config_root)
        existing = {
            item.source_cycle_id
            for item in SnapshotStorage(config.database_path).query(
                environment=environment
            )
        }
        eligible = {
            f"backfill:{item.record_id}" for item in trades
        }
        report["would_create"] = len(eligible - existing)
        report["skipped"] = len(eligible & existing)
        return report
    config_root = (
        ROOT
        if args.config == ROOT / "config/equity_history.json"
        else args.config.parent
    )
    config = load_equity_history_config(args.config, root=config_root)
    service = SnapshotService(SnapshotStorage(config.database_path), config)
    cumulative_fees = Decimal("0")
    prefix = []
    for trade in trades:
        prefix.append(trade)
        cumulative_fees += trade.total_fee
        closed = datetime.fromisoformat(trade.closed_at.replace("Z", "+00:00"))
        state = TradingControllerState(
            position_quantity=trade.remaining_position_quantity,
            entry_price=(
                trade.entry_price if trade.remaining_position_quantity > 0 else None
            ),
            virtual_balance=trade.virtual_balance_after,
            total_fees=cumulative_fees,
            realized_pnl=trade.realized_pnl_after,
            closed_trades=trade.closed_trades_after,
            entry_fee=Decimal("0"),
            opened_at=(
                trade.opened_at if trade.remaining_position_quantity > 0 else None
            ),
        )
        try:
            _, created = service.capture(
                environment=environment,
                strategy_name=STRATEGIES[environment],
                state=state, trades=prefix,
                market_price=trade.exit_price,
                candle_open_timestamp=int(closed.timestamp()) - 3600,
                reason="manual_backfill",
                source_cycle_id=f"backfill:{trade.record_id}",
                snapshot_at=closed,
            )
            report["created" if created else "skipped"] += 1
        except (ValueError, OSError) as exc:
            report["invalid"] += 1
            report.setdefault("errors", []).append(type(exc).__name__)
    service.storage.rebuild_equity_peaks(environment)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = execute(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["invalid"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
