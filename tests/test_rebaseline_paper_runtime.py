import json
from pathlib import Path

from app.regime_runtime import (
    RegimeRuntimeCounters,
    RegimeRuntimeState,
    RegimeRuntimeStateStore,
)
from app.trading_controller import TradingControllerState
from app.trading_controller_store import TradingControllerStateStore
from scripts.rebaseline_paper_runtime import main


def prepared_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    state = root / "state"
    state.mkdir(parents=True)
    TradingControllerStateStore(
        state / "trading_controller.json"
    ).save(TradingControllerState())
    runtime = RegimeRuntimeState(
        last_processed_closed_candle=999,
        last_journal_sequence=3,
        counters=RegimeRuntimeCounters(signals_total=3, exits_total=1),
    )
    RegimeRuntimeStateStore(state / "regime_runtime.json").save(runtime)
    (state / "trading_controller_last_candle.txt").write_text(
        "999\n", encoding="utf-8"
    )
    records = [
        {
            "candle_timestamp": 123,
            "baseline_signal": "hold",
            "baseline_trade_executed": False,
            "current_position": "flat",
        },
        {
            "candle_timestamp": 999,
            "baseline_signal": "close_long",
            "baseline_trade_executed": False,
            "current_position": "flat",
        },
        {
            "candle_timestamp": 123,
            "baseline_signal": "hold",
            "baseline_trade_executed": False,
            "current_position": "flat",
        },
    ]
    (state / "shadow_decisions.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records),
        encoding="utf-8",
    )
    return root


def test_dry_run_does_not_change_files(tmp_path, capsys) -> None:
    root = prepared_root(tmp_path)
    runtime = root / "state/regime_runtime.json"
    decisions = root / "state/shadow_decisions.jsonl"
    before = (runtime.read_bytes(), decisions.read_bytes())

    assert main(["--project-root", str(root)]) == 0

    assert (runtime.read_bytes(), decisions.read_bytes()) == before
    assert "mode=DRY-RUN" in capsys.readouterr().out
    assert not (root / "backups").exists()


def test_confirm_removes_only_test_records_and_resets_counters(
    tmp_path, capsys
) -> None:
    root = prepared_root(tmp_path)

    assert main(["--project-root", str(root), "--confirm"]) == 0

    state = RegimeRuntimeStateStore(
        root / "state/regime_runtime.json"
    ).load()
    records = [
        json.loads(line)
        for line in (
            root / "state/shadow_decisions.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert [item["candle_timestamp"] for item in records] == [999]
    assert state.counters == RegimeRuntimeCounters()
    assert state.last_journal_sequence == 1
    assert state.last_processed_closed_candle == 999
    assert state.rebaseline_at is not None
    backups = list((root / "backups").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "SHA256SUMS").exists()
    assert "mode=CONFIRM" in capsys.readouterr().out


def test_refuses_when_real_trade_journal_exists(tmp_path, capsys) -> None:
    root = prepared_root(tmp_path)
    (root / "state/controller_trade_journal.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )

    assert main(["--project-root", str(root), "--confirm"]) == 2

    assert "trade journal is not empty" in capsys.readouterr().err
    assert not (root / "backups").exists()
