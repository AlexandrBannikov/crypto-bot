from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import trade_reporting
from app.trade_journal import JsonlTradeJournal
from app.trade_reporting import TradeReportError
from app.strategies import Signal
from app.trade_signal import TradeSignal
from app.trading_controller import TradingControllerState
from app.trading_types import TradeAction
from scripts import run_bybit_controller
from tests.test_trade_journal import make_entry


STOP_LOSS_PERCENT = run_bybit_controller.STOP_LOSS_PERCENT
build_execution_signal = run_bybit_controller.build_execution_signal


def test_stop_loss_percent_is_two_percent() -> None:
    assert STOP_LOSS_PERCENT == Decimal("0.02")


def test_buy_signal_receives_stop_loss() -> None:
    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.BUY,
        price=Decimal("1950"),
        state=TradingControllerState(),
    )

    assert isinstance(signal, TradeSignal)
    assert signal.action == Signal.BUY
    assert signal.stop_loss == Decimal("1911.00")
    assert stop_triggered is False


def test_stop_loss_closes_open_position() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.HOLD,
        price=Decimal("1910"),
        state=state,
    )

    assert isinstance(signal, TradeSignal)
    assert signal.action == TradeAction.CLOSE_LONG
    assert stop_triggered is True


def test_stop_loss_triggers_at_exact_price() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.HOLD,
        price=Decimal("1911"),
        state=state,
    )

    assert isinstance(signal, TradeSignal)
    assert signal.action == TradeAction.CLOSE_LONG
    assert stop_triggered is True


def test_hold_above_stop_does_not_close() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.HOLD,
        price=Decimal("1920"),
        state=state,
    )

    assert signal == Signal.HOLD
    assert stop_triggered is False


def test_strategy_sell_is_preserved() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.SELL,
        price=Decimal("2000"),
        state=state,
    )

    assert signal == Signal.SELL
    assert stop_triggered is False


def test_buy_does_not_replace_existing_stop() -> None:
    state = TradingControllerState(
        position_quantity=Decimal("0.01"),
        entry_price=Decimal("1950"),
        stop_loss=Decimal("1911"),
    )

    signal, stop_triggered = build_execution_signal(
        strategy_signal=Signal.BUY,
        price=Decimal("2000"),
        state=state,
    )

    assert signal == Signal.BUY
    assert stop_triggered is False


def install_successful_run(
    monkeypatch,
    *,
    journal_entry,
) -> None:
    candle = SimpleNamespace(timestamp=123, close=100.0)
    feed = SimpleNamespace(get_candles=lambda: (candle,))
    monkeypatch.setattr(
        run_bybit_controller,
        "BybitMarketDataFeed",
        lambda config: feed,
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "load_last_candle_timestamp",
        lambda: None,
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "calculate_latest_signal",
        lambda candles: (Signal.HOLD, 99.0, 100.0),
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "save_last_candle_timestamp",
        lambda timestamp: None,
    )

    state = TradingControllerState()
    store = SimpleNamespace(save=lambda value: None)
    monkeypatch.setattr(
        run_bybit_controller,
        "TradingControllerStateStore",
        lambda path: store,
    )

    result = SimpleNamespace(
        action=SimpleNamespace(value="HOLD"),
        execution=None,
        skipped_reason="hold",
        state=state,
        accounting=None,
        journal_entry=journal_entry,
    )
    controller = SimpleNamespace(
        state=state,
        process_signal=lambda **kwargs: result,
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "TradingController",
        lambda runtime, state_store, trade_journal: controller,
    )


def test_reports_are_created_after_successful_journal_change(
    tmp_path,
    monkeypatch,
) -> None:
    entry = make_entry()
    journal_path = tmp_path / "journal.jsonl"
    JsonlTradeJournal(journal_path).append(entry)
    monkeypatch.setattr(
        run_bybit_controller,
        "JOURNAL_PATH",
        journal_path,
    )
    install_successful_run(monkeypatch, journal_entry=entry)
    text_path = tmp_path / "custom/report.txt"
    png_path = tmp_path / "custom/report.png"

    exit_code = run_bybit_controller.main(
        [
            "--statistics-report",
            str(text_path),
            "--statistics-plot",
            str(png_path),
        ]
    )

    assert exit_code == 0
    assert "Количество записей: 1" in text_path.read_text(
        encoding="utf-8"
    )
    assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_reports_are_not_created_before_successful_processing(
    tmp_path,
    monkeypatch,
) -> None:
    install_successful_run(monkeypatch, journal_entry=make_entry())

    class FailedController:
        state = TradingControllerState()

        def process_signal(self, **kwargs):
            raise RuntimeError("trading failed")

    monkeypatch.setattr(
        run_bybit_controller,
        "TradingController",
        lambda runtime, state_store, trade_journal: FailedController(),
    )
    text_path = tmp_path / "report.txt"
    png_path = tmp_path / "report.png"

    with pytest.raises(RuntimeError, match="trading failed"):
        run_bybit_controller.main(
            [
                "--statistics-report",
                str(text_path),
                "--statistics-plot",
                str(png_path),
            ]
        )

    assert not text_path.exists()
    assert not png_path.exists()


def test_no_new_candle_does_not_overwrite_reports(
    tmp_path,
    monkeypatch,
) -> None:
    candle = SimpleNamespace(timestamp=123, close=100.0)
    monkeypatch.setattr(
        run_bybit_controller,
        "BybitMarketDataFeed",
        lambda config: SimpleNamespace(
            get_candles=lambda: (candle,)
        ),
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "load_last_candle_timestamp",
        lambda: 123,
    )
    text_path = tmp_path / "report.txt"
    png_path = tmp_path / "report.png"
    text_path.write_text("old text", encoding="utf-8")
    png_path.write_bytes(b"old png")

    assert run_bybit_controller.main(
        [
            "--statistics-report",
            str(text_path),
            "--statistics-plot",
            str(png_path),
        ]
    ) == 0
    assert text_path.read_text(encoding="utf-8") == "old text"
    assert png_path.read_bytes() == b"old png"


def test_second_run_recovers_reports_without_duplicate_trade(
    tmp_path,
    monkeypatch,
) -> None:
    candle = SimpleNamespace(timestamp=123, close=100.0)
    journal_path = tmp_path / "state/journal.jsonl"
    state_path = tmp_path / "state/controller.json"
    timestamp_path = tmp_path / "state/last-candle.txt"
    text_path = tmp_path / "reports/statistics.txt"
    png_path = tmp_path / "reports/statistics.png"
    entry = make_entry()
    process_calls = 0
    controller_constructions = 0
    timestamp_writes = 0

    monkeypatch.setattr(
        run_bybit_controller,
        "JOURNAL_PATH",
        journal_path,
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "STATE_PATH",
        state_path,
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "LAST_CANDLE_PATH",
        timestamp_path,
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "BybitMarketDataFeed",
        lambda config: SimpleNamespace(
            get_candles=lambda: (candle,)
        ),
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "calculate_latest_signal",
        lambda candles: (Signal.HOLD, 99.0, 100.0),
    )

    original_save_timestamp = (
        run_bybit_controller.save_last_candle_timestamp
    )

    def save_timestamp(timestamp):
        nonlocal timestamp_writes
        timestamp_writes += 1
        original_save_timestamp(timestamp)

    monkeypatch.setattr(
        run_bybit_controller,
        "save_last_candle_timestamp",
        save_timestamp,
    )

    class FileBackedController:
        def __init__(self, runtime, *, state_store, trade_journal):
            nonlocal controller_constructions
            controller_constructions += 1
            self.state_store = state_store
            self.trade_journal = trade_journal
            self.state = TradingControllerState()

        def process_signal(self, **kwargs):
            nonlocal process_calls
            process_calls += 1
            self.state = TradingControllerState(closed_trades=1)
            self.state_store.save(self.state)
            self.trade_journal.append(entry)
            return SimpleNamespace(
                action=SimpleNamespace(value="CLOSE_LONG"),
                execution=None,
                skipped_reason=None,
                state=self.state,
                accounting=None,
                journal_entry=entry,
            )

    monkeypatch.setattr(
        run_bybit_controller,
        "TradingController",
        FileBackedController,
    )

    original_plot_writer = (
        trade_reporting.save_trade_statistics_plot
    )
    plot_attempts = 0

    def fail_first_plot(*args, **kwargs):
        nonlocal plot_attempts
        plot_attempts += 1
        if plot_attempts == 1:
            raise RuntimeError("temporary PNG failure")
        return original_plot_writer(*args, **kwargs)

    monkeypatch.setattr(
        trade_reporting,
        "save_trade_statistics_plot",
        fail_first_plot,
    )
    arguments = [
        "--statistics-report",
        str(text_path),
        "--statistics-plot",
        str(png_path),
    ]

    assert run_bybit_controller.main(arguments) == 1
    assert len(JsonlTradeJournal(journal_path).read_all()) == 1
    assert timestamp_path.read_text(encoding="utf-8") == "123\n"
    assert text_path.exists()
    assert not png_path.exists()

    assert run_bybit_controller.main(arguments) == 0
    assert len(JsonlTradeJournal(journal_path).read_all()) == 1
    assert timestamp_path.read_text(encoding="utf-8") == "123\n"
    assert process_calls == 1
    assert controller_constructions == 1
    assert timestamp_writes == 1
    assert plot_attempts == 2
    assert text_path.exists()
    assert png_path.exists()
    assert png_path.stat().st_size > 0


def test_reporting_error_returns_nonzero(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    install_successful_run(monkeypatch, journal_entry=make_entry())
    monkeypatch.setattr(
        run_bybit_controller,
        "generate_trade_reports",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            TradeReportError(
                "failed to create PNG trade report custom.png"
            )
        ),
    )

    assert run_bybit_controller.main(
        [
            "--statistics-report",
            str(tmp_path / "report.txt"),
            "--statistics-plot",
            str(tmp_path / "report.png"),
        ]
    ) == 1
    assert "PNG trade report custom.png" in capsys.readouterr().err


def test_custom_report_paths_are_forwarded(
    tmp_path,
    monkeypatch,
) -> None:
    install_successful_run(monkeypatch, journal_entry=make_entry())
    calls = []

    def generate(journal, text, png):
        calls.append((journal, text, png))
        return SimpleNamespace(text_report=text, png_report=png)

    monkeypatch.setattr(
        run_bybit_controller,
        "generate_trade_reports",
        generate,
    )
    text_path = tmp_path / "chosen.txt"
    png_path = tmp_path / "chosen.png"

    assert run_bybit_controller.main(
        [
            "--statistics-report",
            str(text_path),
            "--statistics-plot",
            str(png_path),
        ]
    ) == 0
    assert calls == [
        (
            run_bybit_controller.JOURNAL_PATH,
            text_path,
            png_path,
        )
    ]


def test_unchanged_journal_skips_report_generation(
    monkeypatch,
) -> None:
    install_successful_run(monkeypatch, journal_entry=None)
    monkeypatch.setattr(
        run_bybit_controller,
        "generate_trade_reports",
        lambda *args, **kwargs: pytest.fail(
            "reports must not be generated"
        ),
    )

    assert run_bybit_controller.main([]) == 0


def test_default_report_paths_are_project_relative() -> None:
    assert run_bybit_controller.DEFAULT_STATISTICS_REPORT_PATH == (
        run_bybit_controller.PROJECT_ROOT
        / "reports/trade_statistics.txt"
    )
    assert run_bybit_controller.DEFAULT_STATISTICS_PLOT_PATH == (
        run_bybit_controller.PROJECT_ROOT
        / "reports/trade_statistics.png"
    )


def test_default_report_paths_do_not_depend_on_cwd(
    tmp_path,
    monkeypatch,
) -> None:
    install_successful_run(monkeypatch, journal_entry=make_entry())
    calls = []

    def generate(journal, text, png):
        calls.append((journal, text, png))
        return SimpleNamespace(text_report=text, png_report=png)

    monkeypatch.setattr(
        run_bybit_controller,
        "generate_trade_reports",
        generate,
    )
    monkeypatch.chdir(tmp_path)

    assert run_bybit_controller.main([]) == 0
    assert calls == [
        (
            run_bybit_controller.JOURNAL_PATH,
            run_bybit_controller.PROJECT_ROOT
            / "reports/trade_statistics.txt",
            run_bybit_controller.PROJECT_ROOT
            / "reports/trade_statistics.png",
        )
    ]
