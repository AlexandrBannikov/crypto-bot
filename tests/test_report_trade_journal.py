from decimal import Decimal

import pytest

from app import trade_reporting
from app.trade_journal import JsonlTradeJournal
from scripts import report_trade_journal
from tests.test_trade_journal import make_entry


def test_successful_report_uses_custom_journal_path(
    tmp_path,
    capsys,
) -> None:
    path = tmp_path / "custom.jsonl"
    journal = JsonlTradeJournal(path)
    journal.append(make_entry(net_pnl=Decimal("9.79")))
    journal.append(
        make_entry(
            record_id="loss",
            net_pnl=Decimal("-5.00"),
        )
    )

    assert report_trade_journal.main(["--journal", str(path)]) == 0

    output = capsys.readouterr().out
    assert "Количество записей: 2" in output
    assert "Прибыльных: 1" in output
    assert "Убыточных: 1" in output
    assert "Win rate: 50.0%" in output
    assert "Суммарный net PnL: 4.79" in output
    assert "Gross profit: 9.79" in output
    assert "Profit factor: 1.958" in output
    assert "Максимальная серия побед: 1" in output
    assert "Среднее время удержания, сек.: 3600.0" in output
    assert "Начальный виртуальный баланс: 1000.000" in output
    assert "Итоговый виртуальный баланс: 1009.790" in output


def test_empty_journal_report(tmp_path, capsys) -> None:
    assert (
        report_trade_journal.main(
            ["--journal", str(tmp_path / "missing.jsonl")]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Количество записей: 0" in output
    assert "Win rate: 0%" in output
    assert "Лучшая сделка: нет" in output
    assert "Итоговый виртуальный баланс: нет" in output


def test_corrupt_custom_journal_is_reported(tmp_path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text("{broken\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"corrupt trade journal line 1",
    ):
        report_trade_journal.main(["--journal", str(path)])


def test_cli_uses_library_formatting(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    expected = "formatted by app.trade_reporting"
    monkeypatch.setattr(
        trade_reporting,
        "format_trade_report",
        lambda entries, statistics: expected,
    )

    assert report_trade_journal.main(
        ["--journal", str(tmp_path / "missing.jsonl")]
    ) == 0
    assert capsys.readouterr().out == expected + "\n"
