from decimal import Decimal
import os
from pathlib import Path
import select
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app import trade_reporting
from app.candle import Candle
from app.config import PaperStrategyConfig, PaperStrategyMode
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

HOLDER_CODE = """
import sys
from app.process_lock import ProcessLock
with ProcessLock(sys.argv[1]):
    print("locked", flush=True)
    sys.stdin.read()
"""


@pytest.fixture(autouse=True)
def isolate_break_even_shadow_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        run_bybit_controller,
        "BE_SHADOW_STATE_PATH",
        tmp_path / "state/break_even_shadow.json",
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "BE_SHADOW_JOURNAL_PATH",
        tmp_path / "state/break_even_shadow.jsonl",
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "TRAILING_SHADOW_STATE_PATH",
        tmp_path / "state/trailing_stop_shadow.json",
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "TRAILING_SHADOW_JOURNAL_PATH",
        tmp_path / "state/trailing_stop_shadow.jsonl",
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "PROFIT_LOCK_SHADOW_STATE_PATH",
        tmp_path / "state/profit_lock_shadow.json",
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "PROFIT_LOCK_SHADOW_JOURNAL_PATH",
        tmp_path / "state/profit_lock_shadow.jsonl",
    )


def start_lock_holder(path):
    process = subprocess.Popen(
        [sys.executable, "-c", HOLDER_CODE, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], 5)
    assert ready, "lock-holder process did not become ready"
    assert process.stdout.readline().strip() == "locked"
    return process


def stop_lock_holder(process):
    try:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


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
    monkeypatch.setattr(
        run_bybit_controller.PaperStrategyConfig,
        "from_env",
        lambda **kwargs: PaperStrategyConfig(
            mode=PaperStrategyMode.OFF,
            shadow_diagnostics_enabled=False,
        ),
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "run_break_even_shadow_observer",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(run_bybit_controller, "run_pyramiding_shadow_observer", lambda **kwargs: True)
    monkeypatch.setattr(run_bybit_controller, "run_strategy_v2_shadow_observer", lambda **kwargs: True)
    candle = Candle(timestamp=0, open=100, high=101, low=99, close=100, volume=1)
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
        run_bybit_controller, "_prepare_canonical_features",
        lambda candles: SimpleNamespace(),
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
        state=state, _state=state, state_store=store,
        process_signal=lambda **kwargs: result,
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "TradingController",
        lambda runtime, state_store, trade_journal: controller,
    )
    cycle = SimpleNamespace(
        candle=candle,
        open_step=SimpleNamespace(executions=((result,) if journal_entry is not None else ())),
        close_execution=None,
        score_snapshot=None,
        state_before=state,
        state_after=state,
        decision=SimpleNamespace(
            baseline_signal=SimpleNamespace(action=TradeAction.HOLD),
        ),
        effective_action=TradeAction.HOLD,
        unresolved_gap=False,
        score_status="PENDING",
        strategy_signal=Signal.HOLD,
    )
    monkeypatch.setattr(
        run_bybit_controller, "process_production_candles",
        lambda *args, **kwargs: (cycle,),
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
        run_bybit_controller, "process_production_candles",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("trading failed")),
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
    journal_path = tmp_path / "state/journal.jsonl"
    timestamp_path = tmp_path / "state/last-candle.txt"
    text_path = tmp_path / "reports/statistics.txt"
    png_path = tmp_path / "reports/statistics.png"
    entry = make_entry()
    JsonlTradeJournal(journal_path).append(entry)
    install_successful_run(monkeypatch, journal_entry=entry)
    monkeypatch.setattr(run_bybit_controller, "JOURNAL_PATH", journal_path)

    process_calls = 0
    timestamp_writes = 0
    original_process = run_bybit_controller.process_production_candles

    def process(*args, **kwargs):
        nonlocal process_calls
        process_calls += 1
        return original_process(*args, **kwargs)

    def load_timestamp():
        return int(timestamp_path.read_text()) if timestamp_path.exists() else None

    def save_timestamp(timestamp: int):
        nonlocal timestamp_writes
        timestamp_writes += 1
        timestamp_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp_path.write_text(f"{timestamp}\n")

    monkeypatch.setattr(run_bybit_controller, "process_production_candles", process)
    monkeypatch.setattr(run_bybit_controller, "load_last_candle_timestamp", load_timestamp)
    monkeypatch.setattr(run_bybit_controller, "save_last_candle_timestamp", save_timestamp)

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
    assert timestamp_path.read_text(encoding="utf-8") == "0\n"
    assert text_path.exists()
    assert not png_path.exists()

    assert run_bybit_controller.main(arguments) == 0
    assert len(JsonlTradeJournal(journal_path).read_all()) == 1
    assert timestamp_path.read_text(encoding="utf-8") == "0\n"
    assert process_calls == 1
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


def test_frozen_trailing_and_profit_lock_observers_are_not_called(monkeypatch) -> None:
    install_successful_run(monkeypatch, journal_entry=None)
    monkeypatch.setattr(
        run_bybit_controller, "run_trailing_shadow_observer",
        lambda **kwargs: pytest.fail("frozen trailing observer was called"),
    )
    monkeypatch.setattr(
        run_bybit_controller, "run_profit_lock_shadow_observer",
        lambda **kwargs: pytest.fail("frozen profit-lock observer was called"),
    )
    assert run_bybit_controller.main([]) == 0


def test_default_report_paths_are_test_isolated(
    isolated_runtime_artifacts,
) -> None:
    assert (
        run_bybit_controller.DEFAULT_STATISTICS_REPORT_PATH
        == isolated_runtime_artifacts / "reports/trade_statistics.txt"
    )
    assert (
        run_bybit_controller.DEFAULT_STATISTICS_PLOT_PATH
        == isolated_runtime_artifacts / "reports/trade_statistics.png"
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
            run_bybit_controller.DEFAULT_STATISTICS_REPORT_PATH,
            run_bybit_controller.DEFAULT_STATISTICS_PLOT_PATH,
        )
    ]


def test_successful_run_with_free_custom_lock(
    tmp_path,
    monkeypatch,
) -> None:
    install_successful_run(monkeypatch, journal_entry=None)

    assert run_bybit_controller.main(
        ["--lock-file", str(tmp_path / "controller.lock")]
    ) == 0


def test_occupied_lock_returns_two_without_side_effects(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    lock_path = tmp_path / "controller.lock"
    timestamp_path = tmp_path / "timestamp.txt"
    journal_path = tmp_path / "journal.jsonl"
    report_path = tmp_path / "report.txt"
    plot_path = tmp_path / "report.png"
    timestamp_path.write_text("old timestamp", encoding="utf-8")
    journal_path.write_text("old journal", encoding="utf-8")
    report_path.write_text("old report", encoding="utf-8")
    plot_path.write_bytes(b"old plot")

    def forbidden(*args, **kwargs):
        pytest.fail("controller work must not start while lock is held")

    monkeypatch.setattr(
        run_bybit_controller, "BybitMarketDataFeed", forbidden
    )
    monkeypatch.setattr(
        run_bybit_controller, "BybitMarketDataConfig", forbidden
    )
    monkeypatch.setattr(
        run_bybit_controller,
        "TradingControllerStateStore",
        forbidden,
    )
    monkeypatch.setattr(
        run_bybit_controller, "TradingController", forbidden
    )
    monkeypatch.setattr(
        run_bybit_controller, "load_last_candle_timestamp", forbidden
    )
    monkeypatch.setattr(
        run_bybit_controller, "save_last_candle_timestamp", forbidden
    )
    monkeypatch.setattr(
        run_bybit_controller, "generate_trade_reports", forbidden
    )

    holder = start_lock_holder(lock_path)
    try:
        exit_code = run_bybit_controller.main(
            [
                "--lock-file",
                str(lock_path),
                "--statistics-report",
                str(report_path),
                "--statistics-plot",
                str(plot_path),
            ]
        )
    finally:
        stop_lock_holder(holder)

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "controller уже запущен" in error
    assert str(lock_path) in error
    assert timestamp_path.read_text(encoding="utf-8") == "old timestamp"
    assert journal_path.read_text(encoding="utf-8") == "old journal"
    assert report_path.read_text(encoding="utf-8") == "old report"
    assert plot_path.read_bytes() == b"old plot"


def test_run_succeeds_after_occupied_lock_is_released(
    tmp_path,
    monkeypatch,
) -> None:
    lock_path = tmp_path / "controller.lock"
    holder = start_lock_holder(lock_path)
    try:
        assert run_bybit_controller.main(
            ["--lock-file", str(lock_path)]
        ) == 2
    finally:
        stop_lock_holder(holder)

    install_successful_run(monkeypatch, journal_entry=None)
    assert run_bybit_controller.main(
        ["--lock-file", str(lock_path)]
    ) == 0


def test_custom_lock_path_is_used(tmp_path, monkeypatch) -> None:
    lock_path = tmp_path / "custom/location/controller.lock"
    install_successful_run(monkeypatch, journal_entry=None)

    assert run_bybit_controller.main(
        ["--lock-file", str(lock_path)]
    ) == 0
    assert lock_path.exists()


def test_default_lock_path_is_test_isolated(
    isolated_runtime_artifacts,
) -> None:
    assert run_bybit_controller.DEFAULT_LOCK_PATH == (
        isolated_runtime_artifacts / "state/bybit_controller.lock"
    )


def test_default_lock_path_does_not_depend_on_cwd(
    tmp_path,
    monkeypatch,
) -> None:
    captured = []

    class RecordingLock:
        def __init__(self, path):
            captured.append(path)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(run_bybit_controller, "ProcessLock", RecordingLock)
    monkeypatch.setattr(
        run_bybit_controller,
        "run_controller",
        lambda args: 0,
    )
    monkeypatch.chdir(tmp_path)

    assert run_bybit_controller.main([]) == 0
    assert captured == [run_bybit_controller.DEFAULT_LOCK_PATH]


def test_lock_creation_error_returns_one_with_path(
    tmp_path,
    capsys,
) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("content", encoding="utf-8")
    lock_path = parent_file / "controller.lock"

    assert run_bybit_controller.main(
        ["--lock-file", str(lock_path)]
    ) == 1
    assert str(lock_path) in capsys.readouterr().err


def test_lock_is_held_during_report_generation(
    tmp_path,
    monkeypatch,
) -> None:
    lock_path = tmp_path / "controller.lock"
    install_successful_run(monkeypatch, journal_entry=make_entry())

    def generate(journal, text, png):
        contender = subprocess.run(
            [sys.executable, "-c", HOLDER_CODE, str(lock_path)],
            input="",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert contender.returncode != 0
        return SimpleNamespace(text_report=text, png_report=png)

    monkeypatch.setattr(
        run_bybit_controller,
        "generate_trade_reports",
        generate,
    )

    assert run_bybit_controller.main(
        [
            "--lock-file",
            str(lock_path),
            "--statistics-report",
            str(tmp_path / "report.txt"),
            "--statistics-plot",
            str(tmp_path / "report.png"),
        ]
    ) == 0


def test_help_does_not_import_matplotlib_or_create_files(
    tmp_path,
) -> None:
    script_path = (
        Path(run_bybit_controller.__file__).resolve()
    )
    lock_path = tmp_path / "state/controller.lock"
    text_path = tmp_path / "reports/statistics.txt"
    png_path = tmp_path / "reports/statistics.png"
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path / "unwritable-home")

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--lock-file",
            str(lock_path),
            "--statistics-report",
            str(text_path),
            "--statistics-plot",
            str(png_path),
            "--help",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    stderr = completed.stderr.lower()
    assert "matplotlib" not in stderr
    assert "mplconfigdir" not in stderr
    assert "temporary cache" not in stderr
    assert not lock_path.exists()
    assert not text_path.exists()
    assert not png_path.exists()
    assert not (tmp_path / "state").exists()
