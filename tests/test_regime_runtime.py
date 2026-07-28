from datetime import datetime, timedelta, timezone
from decimal import Decimal
import stat

import pytest

from app.config import RuntimeSafetyConfig
from app.regime_runtime import (
    RegimeRuntimeCounters,
    RegimeRuntimeState,
    RegimeRuntimeStateStore,
)


def config(**changes):
    values = {
        "max_daily_loss_percent": 5,
        "max_drawdown_percent": 10,
    }
    values.update(changes)
    return RuntimeSafetyConfig(**values)


def test_live_enabled_fails_closed() -> None:
    with pytest.raises(ValueError, match="must remain false"):
        RuntimeSafetyConfig(live_trading_enabled=True)


def test_maximum_positions_is_one() -> None:
    with pytest.raises(ValueError, match="exactly 1"):
        RuntimeSafetyConfig(max_open_positions=2)


def test_counter_invariant() -> None:
    counters = RegimeRuntimeCounters()
    counters.record_block("range", shadow=False)
    counters.record_block("high_volatility", shadow=False)
    assert counters.entries_blocked == 2
    assert counters.blocked_range + counters.blocked_high_volatility == 2


def test_shadow_counter_does_not_increment_actual_blocks() -> None:
    counters = RegimeRuntimeCounters()
    counters.record_block("range", shadow=True)
    assert counters.shadow_would_block == 1
    assert counters.entries_blocked == 0


def test_invalid_counter_state_is_rejected() -> None:
    with pytest.raises(ValueError, match="must equal"):
        RegimeRuntimeCounters(entries_blocked=1).validate()


def test_daily_loss_halts_and_resets_next_utc_day() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = RegimeRuntimeState(
        peak_balance="1000",
        daily_starting_balance="1000",
        daily_utc_date="2026-01-01",
    )
    state.update_risk(Decimal("940"), config(), now=start)
    assert state.active_halt_reason == "daily_loss"
    state.update_risk(
        Decimal("940"), config(), now=start + timedelta(days=1)
    )
    assert state.active_halt_reason is None
    assert state.daily_loss_percent == "0"


def test_drawdown_halt_survives_restart_and_manual_reset(tmp_path) -> None:
    state = RegimeRuntimeState(peak_balance="1000")
    state.update_risk(
        Decimal("890"),
        config(max_daily_loss_percent=50),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    store = RegimeRuntimeStateStore(tmp_path / "runtime.json")
    store.save(state)
    restarted = store.load()
    assert restarted.drawdown_halt_latched is True
    assert restarted.active_halt_reason == "maximum_drawdown"
    restarted.reset_drawdown_halt()
    assert restarted.permits_entry() is True


def test_state_write_is_atomic_and_persists_counters(tmp_path) -> None:
    path = tmp_path / "state/runtime.json"
    state = RegimeRuntimeState()
    state.counters.signals_total = 3
    state.last_processed_closed_candle = 123
    state.last_journal_sequence = 7
    store = RegimeRuntimeStateStore(path)
    store.save(state)
    assert store.load().counters.signals_total == 3
    assert store.load().last_processed_closed_candle == 123
    assert store.load().last_journal_sequence == 7
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert not list(path.parent.glob("*.tmp"))


def test_state_rewrite_restores_read_only_group_mode(tmp_path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o600)

    RegimeRuntimeStateStore(path).save(RegimeRuntimeState())

    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_old_empty_state_is_migrated(tmp_path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text("{}", encoding="utf-8")
    state = RegimeRuntimeStateStore(path).load()
    assert state.version == 1
    assert state.counters.signals_total == 0
