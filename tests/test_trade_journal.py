from decimal import Decimal
import json

import pytest

from app.trade_journal import (
    JsonlTradeJournal,
    TradeJournalEntry,
)


def make_entry(
    *,
    record_id: str = "record-1",
    net_pnl: Decimal = Decimal("9.79"),
) -> TradeJournalEntry:
    return TradeJournalEntry(
        record_id=record_id,
        symbol="ETHUSDT",
        opened_at="2026-07-27T10:00:00+00:00",
        closed_at="2026-07-27T11:00:00+00:00",
        entry_price=Decimal("100.00"),
        exit_price=Decimal("110.00"),
        quantity=Decimal("1.0"),
        entry_notional=Decimal("100.000"),
        exit_notional=Decimal("110.000"),
        gross_pnl=Decimal("10.000"),
        entry_fee=Decimal("0.100"),
        exit_fee=Decimal("0.110"),
        total_fee=Decimal("0.210"),
        net_pnl=net_pnl,
        pnl_percent=Decimal("9.7900"),
        exit_reason="signal",
        remaining_position_quantity=Decimal("0"),
        virtual_balance_after=Decimal("1009.790"),
        realized_pnl_after=net_pnl,
        closed_trades_after=1,
    )


def test_missing_journal_returns_empty_list(tmp_path) -> None:
    journal = JsonlTradeJournal(tmp_path / "missing.jsonl")

    assert journal.read_all() == []


def test_append_creates_parent_and_preserves_decimal_strings(
    tmp_path,
) -> None:
    path = tmp_path / "nested" / "trades.jsonl"
    journal = JsonlTradeJournal(path)

    journal.append(make_entry())

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["entry_price"] == "100.00"
    assert payload["quantity"] == "1.0"
    assert payload["net_pnl"] == "9.79"
    assert journal.read_all() == [make_entry()]


def test_two_entries_are_appended_without_overwrite(tmp_path) -> None:
    journal = JsonlTradeJournal(tmp_path / "trades.jsonl")

    journal.append(make_entry())
    journal.append(
        make_entry(
            record_id="record-2",
            net_pnl=Decimal("-5.00"),
        )
    )

    entries = journal.read_all()
    assert [entry.record_id for entry in entries] == [
        "record-1",
        "record-2",
    ]


def test_corrupt_jsonl_line_has_clear_line_number(tmp_path) -> None:
    path = tmp_path / "trades.jsonl"
    path.write_text('{"record_id":\n', encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"corrupt trade journal line 1",
    ):
        JsonlTradeJournal(path).read_all()
