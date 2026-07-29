from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.strategy_lab import PERIODS, build_report, load_config, render_report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Read-only Strategy Laboratory v2 report"
    )
    result.add_argument("--period", choices=PERIODS, default="24h")
    result.add_argument("--strategy")
    result.add_argument("--json", action="store_true")
    result.add_argument("--timezone", default="UTC")
    result.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/strategy_lab.json",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = build_report(
        load_config(args.config, root=ROOT),
        period=args.period,
        strategy_filter=args.strategy,
        timezone_name=args.timezone,
    )
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json else render_report(report),
        end="" if not args.json else "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
