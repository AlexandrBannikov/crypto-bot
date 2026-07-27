from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trade_journal import JsonlTradeJournal, TradeJournalEntry
from app.trade_statistics import (
    TradeStatistics,
    calculate_trade_statistics,
)


DEFAULT_JOURNAL_PATH = Path(
    "state/controller_trade_journal.jsonl"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Отчёт по журналу закрытых сделок",
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=DEFAULT_JOURNAL_PATH,
        help="путь к JSONL-журналу",
    )
    return parser


def format_trade(entry: TradeJournalEntry | None) -> str:
    if entry is None:
        return "нет"
    return (
        f"{entry.symbol} {entry.net_pnl} "
        f"({entry.record_id})"
    )


def format_optional(value: object | None) -> str:
    return str(value) if value is not None else "не определён"


def format_statistics(statistics: TradeStatistics) -> list[str]:
    return [
        f"Количество записей: {statistics.total_trades}",
        f"Прибыльных: {statistics.winning_trades}",
        f"Убыточных: {statistics.losing_trades}",
        f"Безубыточных: {statistics.breakeven_trades}",
        f"Win rate: {statistics.win_rate}%",
        f"Суммарный gross PnL: {statistics.gross_pnl}",
        f"Суммарные комиссии: {statistics.total_fees}",
        f"Суммарный net PnL: {statistics.net_pnl}",
        f"Средний net PnL: {statistics.average_net_pnl}",
        f"Gross profit: {statistics.gross_profit}",
        f"Gross loss: {statistics.gross_loss}",
        f"Средняя прибыль: {statistics.average_win}",
        f"Средний убыток: {statistics.average_loss}",
        f"Максимальная прибыль: {statistics.largest_win}",
        f"Максимальный убыток: {statistics.largest_loss}",
        "Profit factor: "
        + format_optional(statistics.profit_factor),
        f"Expectancy: {statistics.expectancy}",
        "Максимальная просадка: "
        f"{statistics.max_drawdown_absolute}",
        "Максимальная просадка, %: "
        f"{statistics.max_drawdown_percent}%",
        "Recovery factor: "
        + format_optional(statistics.recovery_factor),
        "Максимальная серия побед: "
        f"{statistics.longest_win_streak}",
        "Максимальная серия поражений: "
        f"{statistics.longest_loss_streak}",
        "Среднее время удержания, сек.: "
        f"{statistics.average_holding_seconds}",
        "Минимальное время удержания, сек.: "
        f"{statistics.min_holding_seconds}",
        "Максимальное время удержания, сек.: "
        f"{statistics.max_holding_seconds}",
        f"Начальный виртуальный баланс: {statistics.starting_balance}",
        f"Конечный виртуальный баланс: {statistics.ending_balance}",
    ]


def render_report(
    entries: list[TradeJournalEntry],
) -> str:
    statistics = calculate_trade_statistics(entries)
    best = max(
        entries,
        key=lambda entry: entry.net_pnl,
        default=None,
    )
    worst = min(
        entries,
        key=lambda entry: entry.net_pnl,
        default=None,
    )

    return "\n".join(
        format_statistics(statistics)
        + [
            f"Лучшая сделка: {format_trade(best)}",
            f"Худшая сделка: {format_trade(worst)}",
            "Итоговый виртуальный баланс: "
            + (
                str(statistics.ending_balance)
                if entries
                else "нет"
            ),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entries = JsonlTradeJournal(args.journal).read_all()
    print(render_report(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
