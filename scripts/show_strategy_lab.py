from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.strategy_confidence import (
    build_promotion_review,
    load_promotion_config,
    render_promotion_review,
)
from app.strategy_lab import PERIODS, load_config, render_report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Read-only Strategy Laboratory v2 report"
    )
    result.add_argument("--period", choices=PERIODS, default="24h")
    result.add_argument("--strategy")
    result.add_argument("--recommendations", action="store_true")
    result.add_argument("--explain", action="store_true")
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
    report = build_promotion_review(
        load_config(args.config, root=ROOT),
        load_promotion_config(args.config),
        period=args.period,
        strategy_filter=args.strategy,
        timezone_name=args.timezone,
    )
    if args.recommendations or args.explain:
        text = render_promotion_review(report, explain=args.explain)
    else:
        text = render_report(report)
    print(
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json else text,
        end="" if not args.json else "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
