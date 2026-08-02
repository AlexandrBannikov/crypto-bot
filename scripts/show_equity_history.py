from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.equity_history import (
    SnapshotMetrics,
    SnapshotStorage,
    load_equity_history_config,
)
from app.equity_integrity import check_equity_history


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Read-only historical equity diagnostics")
    result.add_argument("--environment", choices=("production", "candidate"))
    result.add_argument("--window", choices=("24h", "7d", "14d", "30d", "all"), default="all")
    result.add_argument("--daily", action="store_true")
    result.add_argument("--monthly", action="store_true")
    result.add_argument("--quality", action="store_true")
    result.add_argument("--duplicates", action="store_true")
    result.add_argument("--gaps", action="store_true")
    result.add_argument("--json", action="store_true")
    result.add_argument(
        "--config", type=Path, default=ROOT / "config/equity_history.json"
    )
    return result


def build(args: argparse.Namespace) -> dict:
    config_root = (
        ROOT
        if args.config == ROOT / "config/equity_history.json"
        else args.config.parent
    )
    config = load_equity_history_config(args.config, root=config_root)
    storage = SnapshotStorage(config.database_path)
    metrics = SnapshotMetrics(storage, config)
    environments = [args.environment] if args.environment else ["production", "candidate"]
    result = {
        "schema_version": storage.schema_version(),
        "database": str(config.database_path),
        "window": args.window,
        "environments": {},
    }
    for environment in environments:
        aggregate = metrics.aggregate(environment)
        rolling = metrics.rolling(environment, args.window)
        result["environments"][environment] = {
            "aggregate": aggregate,
            "rolling": rolling,
            "quality": metrics.quality(environment),
        }
        if args.daily:
            result["environments"][environment]["daily"] = (
                metrics.period_returns(environment, "daily")
            )
        if args.monthly:
            result["environments"][environment]["monthly"] = (
                metrics.period_returns(environment, "monthly")
            )
    if not args.environment:
        result["comparison"] = metrics.compare()
    if args.quality or args.duplicates or args.gaps:
        integrity = check_equity_history(config.database_path, mode=args.environment)
        if not args.duplicates:
            integrity.pop("duplicate_groups", None)
        if not args.gaps:
            integrity.pop("gaps", None)
        result["integrity"] = integrity
    return result


def render(report: dict) -> str:
    lines = [
        "Historical Equity Snapshots",
        f"Schema: {report['schema_version']}",
        f"Window: {report['window']}",
    ]
    for environment, item in report["environments"].items():
        aggregate, rolling, quality = (
            item["aggregate"], item["rolling"], item["quality"]
        )
        lines.extend(
            [
                "",
                environment.title(),
                f"  snapshots: {quality['total_snapshots']} "
                f"(valid {quality['valid']}, partial {quality['partial']}, "
                f"invalid {quality['invalid']})",
                f"  date range: {aggregate.get('first_snapshot', 'N/A')} — "
                f"{aggregate.get('last_snapshot', 'N/A')}",
                f"  latest candle: {aggregate.get('latest_candle', 'N/A')}",
                f"  latest equity: {aggregate.get('latest_equity', 'N/A')}",
                f"  return: {rolling.get('return_percent', 'N/A')}",
                f"  max/current drawdown: "
                f"{rolling.get('max_drawdown_percent', 'N/A')} / "
                f"{rolling.get('current_drawdown_percent', 'N/A')}",
                f"  daily volatility: {rolling.get('daily_volatility', 'N/A')}",
                f"  fees/trades/PF: {rolling.get('fees', 'N/A')} / "
                f"{rolling.get('closed_trades', 'N/A')} / "
                f"{rolling.get('profit_factor', 'N/A')}",
                f"  best/worst day: {aggregate.get('best_day', 'N/A')} / "
                f"{aggregate.get('worst_day', 'N/A')}",
                f"  completeness: {rolling.get('completeness_pct', 'N/A')}",
                f"  gaps: {quality.get('gap_count', 'N/A')}; "
                f"reason: {rolling.get('insufficient_reason') or 'none'}",
            ]
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = build(args)
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json else render(report),
        end="\n" if args.json else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
