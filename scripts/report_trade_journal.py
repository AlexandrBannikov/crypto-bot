from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trade_journal import JsonlTradeJournal, TradeJournalEntry


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


def render_report(
    entries: list[TradeJournalEntry],
) -> str:
    count = len(entries)
    profitable = sum(entry.net_pnl > 0 for entry in entries)
    losing = sum(entry.net_pnl < 0 for entry in entries)
    gross_pnl = sum(
        (entry.gross_pnl for entry in entries),
        Decimal("0"),
    )
    total_fees = sum(
        (entry.total_fee for entry in entries),
        Decimal("0"),
    )
    net_pnl = sum(
        (entry.net_pnl for entry in entries),
        Decimal("0"),
    )
    average_net = (
        net_pnl / count if count else Decimal("0")
    )
    win_rate = (
        Decimal(profitable) / count * Decimal("100")
        if count
        else Decimal("0")
    )
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
    final_balance = (
        entries[-1].virtual_balance_after
        if entries
        else None
    )

    return "\n".join(
        [
            f"Количество записей: {count}",
            f"Прибыльных: {profitable}",
            f"Убыточных: {losing}",
            f"Win rate: {win_rate}%",
            f"Суммарный gross PnL: {gross_pnl}",
            f"Суммарные комиссии: {total_fees}",
            f"Суммарный net PnL: {net_pnl}",
            f"Средний net PnL: {average_net}",
            f"Лучшая сделка: {format_trade(best)}",
            f"Худшая сделка: {format_trade(worst)}",
            "Итоговый виртуальный баланс: "
            + (
                str(final_balance)
                if final_balance is not None
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
