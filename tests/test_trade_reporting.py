from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import matplotlib
from matplotlib.figure import Figure
import pytest

from app import trade_reporting
from app.trade_journal import JsonlTradeJournal
from app.trade_reporting import TradeReportError, generate_trade_reports
from tests.test_trade_journal import make_entry


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def assert_png(path: Path) -> None:
    content = path.read_bytes()
    assert len(content) > len(PNG_SIGNATURE)
    assert content.startswith(PNG_SIGNATURE)


def test_generates_text_and_png_from_nonempty_journal(tmp_path) -> None:
    journal_path = tmp_path / "trades.jsonl"
    JsonlTradeJournal(journal_path).append(make_entry())

    result = generate_trade_reports(
        journal_path,
        tmp_path / "reports/statistics.txt",
        tmp_path / "reports/statistics.png",
    )

    assert result.text_report.read_text(encoding="utf-8").endswith("\n")
    assert "Количество записей: 1" in result.text_report.read_text(
        encoding="utf-8"
    )
    assert_png(result.png_report)


def test_empty_missing_journal_creates_reports_and_directories(
    tmp_path,
) -> None:
    text_path = tmp_path / "deep/text/report.txt"
    png_path = tmp_path / "other/deep/report.png"

    generate_trade_reports(
        tmp_path / "missing.jsonl",
        text_path,
        png_path,
    )

    assert "Количество записей: 0" in text_path.read_text(
        encoding="utf-8"
    )
    assert "Итоговый виртуальный баланс: нет" in text_path.read_text(
        encoding="utf-8"
    )
    assert_png(png_path)


def test_existing_empty_journal_creates_nonempty_reports(
    tmp_path,
) -> None:
    journal_path = tmp_path / "empty.jsonl"
    journal_path.touch()
    text_path = tmp_path / "empty.txt"
    png_path = tmp_path / "empty.png"

    generate_trade_reports(journal_path, text_path, png_path)

    assert text_path.stat().st_size > 0
    assert "Количество записей: 0" in text_path.read_text(
        encoding="utf-8"
    )
    assert_png(png_path)


def test_custom_paths_are_returned_and_safely_overwritten(tmp_path) -> None:
    journal_path = tmp_path / "custom-journal.jsonl"
    text_path = tmp_path / "custom/out.txt"
    png_path = tmp_path / "custom/out.png"
    journal = JsonlTradeJournal(journal_path)
    journal.append(make_entry())

    first = generate_trade_reports(journal_path, text_path, png_path)
    first_png = png_path.read_bytes()
    journal.append(
        replace(
            make_entry(record_id="second", net_pnl=Decimal("-2")),
            virtual_balance_after=Decimal("1007.790"),
        )
    )
    second = generate_trade_reports(journal_path, text_path, png_path)

    assert first.text_report == second.text_report == text_path
    assert first.png_report == second.png_report == png_path
    assert "Количество записей: 2" in text_path.read_text(
        encoding="utf-8"
    )
    assert_png(png_path)
    assert png_path.read_bytes() != first_png
    assert list(text_path.parent.glob(f".{text_path.name}.*")) == []
    assert list(png_path.parent.glob(f".{png_path.name}.*")) == []


def test_corrupt_journal_has_clear_error(tmp_path) -> None:
    journal_path = tmp_path / "broken.jsonl"
    journal_path.write_text("{broken\n", encoding="utf-8")

    with pytest.raises(
        TradeReportError,
        match=r"failed to process trade journal .*corrupt trade journal line 1",
    ):
        generate_trade_reports(
            journal_path,
            tmp_path / "report.txt",
            tmp_path / "report.png",
        )


def test_text_write_error_identifies_text_report(tmp_path) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("block", encoding="utf-8")
    text_path = blocking_file / "report.txt"

    with pytest.raises(
        TradeReportError,
        match=r"failed to create text trade report",
    ):
        generate_trade_reports(
            tmp_path / "missing.jsonl",
            text_path,
            tmp_path / "report.png",
        )


def test_png_write_error_identifies_png_report(tmp_path) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("block", encoding="utf-8")
    png_path = blocking_file / "report.png"

    with pytest.raises(
        TradeReportError,
        match=r"failed to create PNG trade report",
    ):
        generate_trade_reports(
            tmp_path / "missing.jsonl",
            tmp_path / "report.txt",
            png_path,
        )


def test_uses_headless_backend() -> None:
    assert matplotlib.get_backend().lower() == "agg"


def test_figure_is_closed_when_rendering_fails(
    tmp_path,
    monkeypatch,
) -> None:
    journal_path = tmp_path / "trades.jsonl"
    JsonlTradeJournal(journal_path).append(make_entry())
    statistics = trade_reporting.calculate_trade_statistics(
        JsonlTradeJournal(journal_path).read_all()
    )
    open_figures = set(trade_reporting.plt.get_fignums())

    def fail_after_figure_creation(self, *args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(Figure, "suptitle", fail_after_figure_creation)

    with pytest.raises(RuntimeError, match="render failed"):
        trade_reporting.render_trade_statistics_figure(
            statistics,
            title="Failure",
            width=6,
            height=5,
        )

    assert set(trade_reporting.plt.get_fignums()) == open_figures


def test_runtime_error_during_png_save_is_wrapped_and_cleans_temporary(
    tmp_path,
    monkeypatch,
) -> None:
    output = tmp_path / "report.png"
    statistics = trade_reporting.calculate_trade_statistics([])

    def fail_savefig(self, *args, **kwargs):
        raise RuntimeError("savefig failed")

    monkeypatch.setattr(Figure, "savefig", fail_savefig)

    with pytest.raises(
        TradeReportError,
        match=r"failed to create PNG trade report .*report\.png.*savefig failed",
    ):
        trade_reporting.save_trade_statistics_plot(statistics, output)

    assert not output.exists()
    assert list(tmp_path.glob(f".{output.name}.*")) == []


def test_text_write_failure_after_temporary_creation_cleans_file(
    tmp_path,
    monkeypatch,
) -> None:
    output = tmp_path / "report.txt"
    output.write_text("old report", encoding="utf-8")
    original_write_text = Path.write_text

    def fail_temporary_write(self, *args, **kwargs):
        if self.name.startswith(f".{output.name}."):
            raise OSError("text write failed")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_temporary_write)

    with pytest.raises(
        TradeReportError,
        match=r"failed to create text trade report .*report\.txt",
    ):
        trade_reporting.save_text_report("new report", output)

    assert output.read_text(encoding="utf-8") == "old report"
    assert list(tmp_path.glob(f".{output.name}.*")) == []


def test_replace_failure_preserves_target_and_cleans_temporary(
    tmp_path,
    monkeypatch,
) -> None:
    output = tmp_path / "report.txt"
    output.write_text("old report", encoding="utf-8")
    original_replace = Path.replace

    def fail_target_replace(self, target):
        if Path(target) == output:
            raise OSError("replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_target_replace)

    with pytest.raises(
        TradeReportError,
        match=r"failed to create text trade report .*replace failed",
    ):
        trade_reporting.save_text_report("new report", output)

    assert output.read_text(encoding="utf-8") == "old report"
    assert list(tmp_path.glob(f".{output.name}.*")) == []


def test_statistics_error_is_wrapped_with_journal_path(
    tmp_path,
    monkeypatch,
) -> None:
    journal_path = tmp_path / "trades.jsonl"
    journal_path.touch()
    monkeypatch.setattr(
        trade_reporting,
        "calculate_trade_statistics",
        lambda entries: (_ for _ in ()).throw(
            ValueError("statistics failed")
        ),
    )

    with pytest.raises(
        TradeReportError,
        match=r"failed to process trade journal .*trades\.jsonl.*statistics failed",
    ):
        generate_trade_reports(
            journal_path,
            tmp_path / "report.txt",
            tmp_path / "report.png",
        )


def test_statistics_are_calculated_once_and_remain_decimal(
    tmp_path,
    monkeypatch,
) -> None:
    journal_path = tmp_path / "trades.jsonl"
    JsonlTradeJournal(journal_path).append(make_entry())
    original = trade_reporting.calculate_trade_statistics
    calls = 0
    observed_statistics = []

    def calculate(entries):
        nonlocal calls
        calls += 1
        statistics = original(entries)
        observed_statistics.append(statistics)
        return statistics

    monkeypatch.setattr(
        trade_reporting,
        "calculate_trade_statistics",
        calculate,
    )

    generate_trade_reports(
        journal_path,
        tmp_path / "report.txt",
        tmp_path / "report.png",
    )

    assert calls == 1
    statistics = observed_statistics[0]
    assert isinstance(statistics.net_pnl, Decimal)
    assert isinstance(statistics.equity_curve[0], Decimal)
