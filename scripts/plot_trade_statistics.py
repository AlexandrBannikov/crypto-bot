from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt

from app.trade_journal import JsonlTradeJournal
from app.trade_statistics import (
    TradeStatistics,
    calculate_drawdown_curve,
    calculate_trade_statistics,
)


DEFAULT_JOURNAL_PATH = Path("state/controller_trade_journal.jsonl")
DEFAULT_OUTPUT_PATH = Path("reports/trade_statistics.png")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a PNG report for the closed-trade journal",
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=DEFAULT_JOURNAL_PATH,
        help="path to the JSONL trade journal",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="path to the output PNG",
    )
    parser.add_argument(
        "--title",
        default="Trade Statistics",
        help="report title",
    )
    parser.add_argument("--dpi", type=positive_int, default=150)
    parser.add_argument("--width", type=positive_float, default=12.0)
    parser.add_argument("--height", type=positive_float, default=9.0)
    return parser


def format_optional(value: object | None) -> str:
    return str(value) if value is not None else "N/A"


def statistics_text(statistics: TradeStatistics) -> str:
    return (
        f"Total trades: {statistics.total_trades}  |  "
        f"Net PnL: {statistics.net_pnl}  |  "
        f"Win rate: {statistics.win_rate}%  |  "
        f"Profit factor: {format_optional(statistics.profit_factor)}\n"
        f"Max drawdown absolute: {statistics.max_drawdown_absolute}  |  "
        f"Max drawdown percent: {statistics.max_drawdown_percent}%  |  "
        f"Starting balance: {statistics.starting_balance}  |  "
        f"Ending balance: {statistics.ending_balance}"
    )


def render_figure(
    statistics: TradeStatistics,
    *,
    title: str,
    width: float,
    height: float,
):
    equity = (statistics.starting_balance,) + statistics.equity_curve
    drawdown = calculate_drawdown_curve(
        statistics.starting_balance,
        statistics.equity_curve,
    )
    trade_numbers = range(len(equity))

    figure, (equity_axis, drawdown_axis) = plt.subplots(
        2,
        1,
        figsize=(width, height),
        sharex=True,
    )
    figure.suptitle(f"{title}\n{statistics_text(statistics)}")

    equity_axis.plot(
        trade_numbers,
        [float(value) for value in equity],
        marker="o",
        linewidth=1.8,
    )
    equity_axis.set_title("Equity Curve")
    equity_axis.set_ylabel("Balance")
    equity_axis.grid(True, alpha=0.3)
    equity_axis.annotate(
        f"Starting balance: {statistics.starting_balance}",
        (0, float(equity[0])),
        xytext=(8, 10),
        textcoords="offset points",
    )
    equity_axis.annotate(
        f"Ending balance: {statistics.ending_balance}",
        (len(equity) - 1, float(equity[-1])),
        xytext=(8, -16),
        textcoords="offset points",
        ha="right" if len(equity) > 1 else "left",
    )

    drawdown_axis.plot(
        trade_numbers,
        [float(value) for value in drawdown],
        color="tab:red",
        marker="o",
        linewidth=1.8,
    )
    drawdown_axis.fill_between(
        trade_numbers,
        [float(value) for value in drawdown],
        color="tab:red",
        alpha=0.15,
    )
    drawdown_axis.set_title("Drawdown Curve")
    drawdown_axis.set_xlabel("Trade number")
    drawdown_axis.set_ylabel("Absolute drawdown")
    drawdown_axis.grid(True, alpha=0.3)

    max_index = drawdown.index(statistics.max_drawdown_absolute)
    drawdown_axis.annotate(
        f"Maximum drawdown: {statistics.max_drawdown_absolute}",
        (max_index, float(drawdown[max_index])),
        xytext=(8, 10),
        textcoords="offset points",
    )

    if statistics.total_trades == 0:
        for axis in (equity_axis, drawdown_axis):
            axis.text(
                0.5,
                0.5,
                "No closed trades",
                transform=axis.transAxes,
                ha="center",
                va="center",
                fontsize=12,
                bbox={"facecolor": "white", "alpha": 0.8},
            )

    figure.tight_layout(rect=(0, 0, 1, 0.88))
    return figure


def save_report(
    statistics: TradeStatistics,
    output: Path,
    *,
    title: str,
    dpi: int,
    width: float,
    height: float,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.png")
    figure = render_figure(
        statistics,
        title=title,
        width=width,
        height=height,
    )
    try:
        figure.savefig(temporary, dpi=dpi, format="png")
        temporary.replace(output)
    finally:
        plt.close(figure)
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        entries = JsonlTradeJournal(args.journal).read_all()
        statistics = calculate_trade_statistics(entries)
        save_report(
            statistics,
            args.output,
            title=args.title,
            dpi=args.dpi,
            width=args.width,
            height=args.height,
        )
    except (OSError, ValueError) as exc:
        print(f"Failed to create trade statistics report: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
