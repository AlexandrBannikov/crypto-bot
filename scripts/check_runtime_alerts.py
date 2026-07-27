from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.runtime_health import HealthCheckResult, HealthStatus, overall_status, run_health_checks


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check paper runtime alerts")
    p.add_argument("--json", action="store_true")
    p.add_argument("--max-candle-age-minutes", type=int, default=90)
    p.add_argument("--max-market-lag-candles", type=int, default=1)
    p.add_argument("--max-detector-errors", type=int, default=0)
    p.add_argument("--no-network", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if min(args.max_candle_age_minutes, args.max_market_lag_candles + 1, args.max_detector_errors + 1) <= 0:
            raise ValueError("thresholds are invalid")
        checks, context = run_health_checks(
            state_path=PROJECT_ROOT / "state/trading_controller.json",
            candle_path=PROJECT_ROOT / "state/trading_controller_last_candle.txt",
            journal_path=PROJECT_ROOT / "state/controller_trade_journal.jsonl",
            shadow_path=PROJECT_ROOT / "state/shadow_decisions.jsonl",
            lock_path=PROJECT_ROOT / "state/bybit_controller.lock",
            max_candle_age_minutes=args.max_candle_age_minutes,
            max_market_lag_candles=args.max_market_lag_candles, no_network=args.no_network,
        )
        state = context["state"]
        shadows = context.get("shadow_diagnostics", [])
        errors = sum(bool(r.get("detector_error")) for r in shadows)
        if errors > args.max_detector_errors:
            checks.append(HealthCheckResult("detector_errors", HealthStatus.WARNING, f"detector errors {errors} exceed threshold {args.max_detector_errors}", {"count": errors}, checks[0].checked_at))
        if state is not None and (not state.virtual_balance.is_finite() or state.virtual_balance < 0):
            checks.append(HealthCheckResult("balance", HealthStatus.CRITICAL, "virtual balance is invalid", {}, checks[0].checked_at))
        latest_shadow = max((int(r["candle_timestamp"]) for r in shadows), default=None)
        if context["last_candle"] and (latest_shadow is None or latest_shadow < context["last_candle"]):
            checks.append(HealthCheckResult("shadow_freshness", HealthStatus.WARNING, "shadow diagnostics lag processed candles", {"latest_shadow": latest_shadow}, checks[0].checked_at))
        status = overall_status(checks)
        payload = {"overall_status": status.name, "checks": [c.to_dict() for c in checks]}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"overall_status: {status.name}")
            for check in checks:
                print(f"{check.status.name}: {check.name}: {check.message}")
        return int(status)
    except Exception as exc:
        print(f"runtime alerts error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
