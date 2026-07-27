from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.runtime_health import HealthStatus, overall_status, run_health_checks

DEFAULT_STATE = PROJECT_ROOT / "state/trading_controller.json"
DEFAULT_JOURNAL = PROJECT_ROOT / "state/controller_trade_journal.jsonl"
DEFAULT_SHADOW = PROJECT_ROOT / "state/shadow_decisions.jsonl"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Show paper controller runtime status")
    result.add_argument("--json", action="store_true")
    result.add_argument("--no-network", action="store_true")
    result.add_argument("--state-path", type=Path, default=DEFAULT_STATE)
    result.add_argument("--journal-path", type=Path, default=DEFAULT_JOURNAL)
    result.add_argument("--shadow-path", type=Path, default=DEFAULT_SHADOW)
    result.add_argument("--max-candle-age-minutes", type=int, default=90)
    return result


def build_status(args: argparse.Namespace) -> tuple[dict, HealthStatus]:
    checks, context = run_health_checks(
        state_path=args.state_path, candle_path=args.state_path.parent / "trading_controller_last_candle.txt",
        journal_path=args.journal_path, shadow_path=args.shadow_path,
        lock_path=PROJECT_ROOT / "state/bybit_controller.lock", symbol=os.getenv("SYMBOL", "ETHUSDT"),
        timeframe=os.getenv("TIMEFRAME", "60"), max_candle_age_minutes=args.max_candle_age_minutes,
        no_network=args.no_network,
    )
    state = context["state"]
    trades = context.get("trade_journal", [])
    shadows = context.get("shadow_diagnostics", [])
    evaluated = [r for r in shadows if r.get("baseline_signal") in {"open_long", "open_short"}]
    same = sum(r.get("baseline_signal") == r.get("filtered_signal") for r in shadows)
    status = overall_status(checks)
    last = context["last_candle"]
    now = datetime.now(timezone.utc)
    payload = {
        "overall_status": status.name, "project_root": str(PROJECT_ROOT),
        "strategy_mode": os.getenv("PAPER_STRATEGY_MODE", "baseline"),
        "symbol": os.getenv("SYMBOL", "ETHUSDT"), "timeframe": os.getenv("TIMEFRAME", "60"),
        "controller_lock_status": next((c.message for c in checks if c.name == "controller_lock"), "unknown"),
        "controller_state_path": str(args.state_path), "state_readable_valid": state is not None,
        "last_processed_candle_timestamp": last,
        "last_candle_age_minutes": (now.timestamp() - last) / 60 if last is not None else None,
        "current_utc_time": now.isoformat(), "virtual_balance": str(state.virtual_balance) if state else None,
        "current_position": "long" if state and state.has_open_position else "flat",
        "open_position_entry_price": str(state.entry_price) if state and state.entry_price else None,
        "open_position_quantity": str(state.position_quantity) if state else None,
        "recorded_trades": len(trades), "latest_trade_timestamp": trades[-1].closed_at if trades else None,
        "trade_journal_status": next((c.status.name for c in checks if c.name == "trade_journal"), "UNKNOWN"),
        "shadow_diagnostics_path": str(args.shadow_path),
        "shadow_diagnostics_status": next((c.status.name for c in checks if c.name == "shadow_diagnostics"), "UNKNOWN"),
        "latest_shadow_decision_timestamp": shadows[-1].get("candle_timestamp") if shadows else None,
        "shadow_entries_evaluated": len(evaluated), "allowed_entries": sum(r.get("allowed") is True for r in evaluated),
        "blocked_entries": sum(bool(r.get("blocked")) for r in evaluated),
        "detector_errors": sum(bool(r.get("detector_error")) for r in shadows),
        "baseline_filtered_agreement_percentage": same / len(shadows) * 100 if shadows else 0.0,
        "bybit_public_api_connectivity": next(("SKIPPED" if c.details.get("skipped") else c.status.name for c in checks if c.name == "bybit_api"), "UNKNOWN"),
        "latest_closed_bybit_candle_timestamp": context["market_candle"],
        "local_state_lagging_market_data": next((c.status != HealthStatus.OK for c in checks if c.name == "market_lag"), False),
        "checks": [c.to_dict() for c in checks],
    }
    return payload, status


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if args.max_candle_age_minutes <= 0:
            raise ValueError("--max-candle-age-minutes must be positive")
        payload, status = build_status(args)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for key, value in payload.items():
                if key != "checks":
                    print(f"{key}: {value}")
        return int(status)
    except Exception as exc:
        print(f"runtime status error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
