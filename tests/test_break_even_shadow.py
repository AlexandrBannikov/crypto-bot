from decimal import Decimal
import json

from app.break_even_shadow import (
    BreakEvenShadowJournal,
    BreakEvenShadowObservation,
    BreakEvenShadowState,
    BreakEvenShadowStateStore,
    observe_break_even_shadow,
    reconcile_break_even_shadow,
)
from app.candle import Candle
from app.trading_controller import TradingControllerState
from scripts import run_bybit_controller


D = Decimal


def candle(timestamp: int, *, high: float, low: float, close: float = 100) -> Candle:
    return Candle(timestamp, close, high, low, close, 1)


def flat() -> TradingControllerState:
    return TradingControllerState()


def opened(
    *,
    entry_price: str = "100",
    quantity: str = "2",
    opened_at: str = "1970-01-01T01:00:00+00:00",
) -> TradingControllerState:
    return TradingControllerState(
        position_quantity=D(quantity),
        entry_price=D(entry_price),
        stop_loss=D(entry_price) * D("0.98"),
        opened_at=opened_at,
    )


def enter() -> BreakEvenShadowState:
    return observe_break_even_shadow(
        BreakEvenShadowState(), candle=candle(0, high=102, low=99),
        production_before=flat(), production_after=opened(),
    ).state


def test_entry_candle_cannot_activate_shadow_break_even() -> None:
    state = enter()
    assert state.be_shadow_status == "inactive"
    assert state.activation_price == D("101.00")
    assert state.protective_price == D("100") * D("1.001") / D("0.999")


def test_activation_is_causal_and_cannot_trigger_on_activation_candle() -> None:
    state = enter()
    update = observe_break_even_shadow(
        state, candle=candle(3600, high=101.5, low=99),
        production_before=opened(), production_after=opened(),
    )
    assert update.state.be_shadow_status == "armed"
    assert update.state.armed_at_candle == 3600
    assert update.state.triggered_at_candle is None


def test_armed_break_even_triggers_from_next_candle_at_protective_price() -> None:
    armed = observe_break_even_shadow(
        enter(), candle=candle(3600, high=101.5, low=99),
        production_before=opened(), production_after=opened(),
    ).state
    update = observe_break_even_shadow(
        armed, candle=candle(7200, high=101, low=100),
        production_before=opened(), production_after=opened(),
    )
    assert update.state.be_shadow_status == "triggered"
    assert update.state.triggered_at_candle == 7200
    assert update.state.hypothetical_exit_price == armed.protective_price
    assert update.state.hypothetical_pnl == 0


def test_shadow_trigger_does_not_change_production_position() -> None:
    production = opened()
    armed = observe_break_even_shadow(
        enter(), candle=candle(3600, high=102, low=99),
        production_before=production, production_after=production,
    ).state
    update = observe_break_even_shadow(
        armed, candle=candle(7200, high=101, low=100),
        production_before=production, production_after=production,
    )
    assert production.has_open_position
    assert production.position_quantity == D("2")
    assert update.state.be_shadow_status == "triggered"


def test_production_exit_classifies_and_resets_shadow_state() -> None:
    production = opened()
    armed = observe_break_even_shadow(
        enter(), candle=candle(3600, high=102, low=101),
        production_before=production, production_after=production,
    ).state
    triggered = observe_break_even_shadow(
        armed, candle=candle(7200, high=101, low=100),
        production_before=production, production_after=production,
    ).state
    update = observe_break_even_shadow(
        triggered, candle=candle(10800, high=99, low=95, close=96),
        production_before=production, production_after=flat(),
        production_exit_pnl=D("-8"),
    )
    assert update.state == BreakEvenShadowState()
    assert update.observation.be_shadow_status == "triggered"
    assert update.observation.saved_loss is True
    assert update.observation.worsened_winner is False


def test_stale_state_recovers_on_next_flat_production_cycle() -> None:
    stale = BreakEvenShadowState(
        be_shadow_status="triggered",
        entry_price=D("100"),
        quantity=D("2"),
        activation_price=D("101"),
        protective_price=D("100.2"),
        entry_candle=0,
        armed_at_candle=3600,
        triggered_at_candle=7200,
    )
    update = observe_break_even_shadow(
        stale, candle=candle(14400, high=100, low=99),
        production_before=flat(), production_after=flat(),
    )
    assert update.state == BreakEvenShadowState()
    assert update.observation.be_shadow_status == "inactive"


def test_journal_duplicate_observer_invocation_is_idempotent(tmp_path) -> None:
    journal = BreakEvenShadowJournal(tmp_path / "be.jsonl")
    observation = BreakEvenShadowObservation(
        candle_timestamp=3600,
        be_shadow_status="armed",
        activation_price=D("101"),
        protective_price=D("100.2"),
        armed_at_candle=3600,
        triggered_at_candle=None,
        hypothetical_exit_price=None,
        hypothetical_pnl=None,
    )
    assert journal.append(observation) is True
    assert journal.append(observation) is False
    assert len(journal.path.read_text(encoding="utf-8").splitlines()) == 1


def test_state_survives_store_restart(tmp_path) -> None:
    path = tmp_path / "be-state.json"
    expected = enter()
    BreakEvenShadowStateStore(path).save(expected)
    assert BreakEvenShadowStateStore(path).load() == expected


def replay_candles(*prices: tuple[float, float]) -> tuple[Candle, ...]:
    return tuple(
        candle(3600 * (index + 1), high=high, low=low)
        for index, (high, low) in enumerate(prices)
    )


def test_reconciliation_before_activation_restores_inactive_position() -> None:
    production = opened()
    restored = reconcile_break_even_shadow(
        BreakEvenShadowState(), production=production,
        candles=replay_candles((100.5, 99), (100.9, 99.5)),
    )
    assert restored.be_shadow_status == "inactive"
    assert restored.entry_price == D("100")
    assert restored.quantity == D("2")
    assert restored.opened_at == production.opened_at


def test_reconciliation_after_activation_restores_armed() -> None:
    production = opened()
    restored = reconcile_break_even_shadow(
        BreakEvenShadowState(), production=production,
        candles=replay_candles((100.5, 99), (102, 99), (102, 101)),
    )
    assert restored.be_shadow_status == "armed"
    assert restored.armed_at_candle == 7200


def test_reconciliation_after_retrace_restores_triggered() -> None:
    production = opened()
    restored = reconcile_break_even_shadow(
        BreakEvenShadowState(), production=production,
        candles=replay_candles((100.5, 99), (102, 99), (102, 100)),
    )
    assert restored.be_shadow_status == "triggered"
    assert restored.triggered_at_candle == 10800


def test_reconciliation_does_not_trigger_inside_activation_candle() -> None:
    production = opened()
    restored = reconcile_break_even_shadow(
        BreakEvenShadowState(), production=production,
        candles=replay_candles((102, 99)),
    )
    assert restored.be_shadow_status == "armed"
    assert restored.triggered_at_candle is None


def test_reconciliation_is_idempotent_and_does_not_duplicate_journal(
    tmp_path,
) -> None:
    production = opened()
    candles = replay_candles((100.5, 99), (102, 101))
    first = reconcile_break_even_shadow(
        BreakEvenShadowState(), production=production, candles=candles,
    )
    second = reconcile_break_even_shadow(
        first, production=production, candles=candles,
    )
    assert second == first
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    for _ in range(2):
        assert run_bybit_controller.run_break_even_shadow_observer(
            candle=candles[-1], production_before=production,
            production_after=production, production_exit_pnl=None,
            historical_candles=candles, state_path=state_path,
            journal_path=journal_path,
        ) is True
    assert len(journal_path.read_text().splitlines()) == 1


def test_mismatched_position_state_is_reconciled() -> None:
    old = opened(opened_at="1970-01-01T00:00:00+00:00")
    stale = observe_break_even_shadow(
        BreakEvenShadowState(), candle=candle(0, high=100, low=99),
        production_before=flat(), production_after=old,
    ).state
    current = opened()
    restored = reconcile_break_even_shadow(
        stale, production=current, candles=replay_candles((100.5, 99)),
    )
    assert restored.opened_at == current.opened_at
    assert restored.entry_candle == 0


def test_triggered_state_survives_store_restart(tmp_path) -> None:
    production = opened()
    triggered = reconcile_break_even_shadow(
        BreakEvenShadowState(), production=production,
        candles=replay_candles((102, 99), (101, 100)),
    )
    path = tmp_path / "be-state.json"
    BreakEvenShadowStateStore(path).save(triggered)
    assert BreakEvenShadowStateStore(path).load() == triggered


def test_armed_state_survives_store_restart(tmp_path) -> None:
    production = opened()
    armed = reconcile_break_even_shadow(
        BreakEvenShadowState(), production=production,
        candles=replay_candles((102, 101)),
    )
    path = tmp_path / "be-state.json"
    BreakEvenShadowStateStore(path).save(armed)
    assert BreakEvenShadowStateStore(path).load() == armed


def test_production_runtime_never_uses_test_candle(tmp_path) -> None:
    production = opened()
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    runtime_candle = candle(3600, high=100.5, low=99)
    assert run_bybit_controller.run_break_even_shadow_observer(
        candle=runtime_candle, production_before=production,
        production_after=production, production_exit_pnl=None,
        historical_candles=(runtime_candle,), state_path=state_path,
        journal_path=journal_path,
    )
    row = json.loads(journal_path.read_text())
    assert row["candle_timestamp"] == 3600
    assert row["candle_timestamp"] != 123


def test_failed_exit_reset_save_recovers_on_next_cycle(
    tmp_path, monkeypatch,
) -> None:
    state_path = tmp_path / "be-state.json"
    journal_path = tmp_path / "be.jsonl"
    stale = BreakEvenShadowState(
        be_shadow_status="triggered", entry_price=D("100"), quantity=D("2"),
        activation_price=D("101"), protective_price=D("100.2"),
        entry_candle=0, armed_at_candle=3600, triggered_at_candle=7200,
        hypothetical_exit_price=D("100.2"), hypothetical_pnl=D("0"),
    )
    real_store = BreakEvenShadowStateStore(state_path)
    real_store.save(stale)

    class FailingStore:
        def __init__(self, path):
            self.delegate = BreakEvenShadowStateStore(path)

        def load(self):
            return self.delegate.load()

        def save(self, state):
            raise OSError("simulated reset failure")

    monkeypatch.setattr(run_bybit_controller, "BreakEvenShadowStateStore", FailingStore)
    production = opened()
    assert run_bybit_controller.run_break_even_shadow_observer(
        candle=candle(10800, high=99, low=95),
        production_before=production, production_after=flat(),
        production_exit_pnl=D("-8"), state_path=state_path,
        journal_path=journal_path,
    ) is False
    assert production.has_open_position
    assert real_store.load() == stale

    monkeypatch.setattr(
        run_bybit_controller, "BreakEvenShadowStateStore", BreakEvenShadowStateStore
    )
    assert run_bybit_controller.run_break_even_shadow_observer(
        candle=candle(14400, high=100, low=99),
        production_before=flat(), production_after=flat(),
        production_exit_pnl=None, state_path=state_path,
        journal_path=journal_path,
    ) is True
    assert real_store.load() == BreakEvenShadowState()


def test_persistence_failure_does_not_change_completed_production_execution(
    tmp_path, monkeypatch,
) -> None:
    production_before = opened()
    production_after = flat()

    class FailingStore:
        def __init__(self, path):
            pass

        def load(self):
            return enter()

        def save(self, state):
            raise OSError("disk unavailable")

    monkeypatch.setattr(run_bybit_controller, "BreakEvenShadowStateStore", FailingStore)
    assert run_bybit_controller.run_break_even_shadow_observer(
        candle=candle(10800, high=100, low=95),
        production_before=production_before, production_after=production_after,
        production_exit_pnl=D("-8"), state_path=tmp_path / "state.json",
        journal_path=tmp_path / "journal.jsonl",
    ) is False
    assert production_before.has_open_position
    assert not production_after.has_open_position
