from decimal import Decimal

from app.trade_journal import JsonlTradeJournal
from scripts.report_trade_journal import main
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

    assert main(["--journal", str(path)]) == 0

    output = capsys.readouterr().out
    assert "Количество записей: 2" in output
    assert "Прибыльных: 1" in output
    assert "Убыточных: 1" in output
    assert "Win rate: 50.0%" in output
    assert "Суммарный net PnL: 4.79" in output
    assert "Итоговый виртуальный баланс: 1009.790" in output


def test_empty_journal_report(tmp_path, capsys) -> None:
    assert (
        main(["--journal", str(tmp_path / "missing.jsonl")])
        == 0
    )

    output = capsys.readouterr().out
    assert "Количество записей: 0" in output
    assert "Win rate: 0%" in output
    assert "Лучшая сделка: нет" in output
    assert "Итоговый виртуальный баланс: нет" in output
