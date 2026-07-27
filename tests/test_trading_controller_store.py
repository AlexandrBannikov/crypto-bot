import json
from decimal import Decimal

import pytest

from app.trading_controller import TradingControllerState
from app.trading_controller_store import (
    TradingControllerStateStore,
)


def test_missing_file_returns_empty_state(
    tmp_path,
) -> None:
    store = TradingControllerStateStore(
        tmp_path / "controller.json"
    )

    state = store.load()

    assert state.position_quantity == Decimal("0")
    assert state.has_open_position is False


def test_saves_and_loads_state(
    tmp_path,
) -> None:
    path = tmp_path / "state" / "controller.json"
    store = TradingControllerStateStore(path)

    store.save(
        TradingControllerState(
            position_quantity=Decimal("0.12345678"),
        )
    )

    loaded = store.load()

    assert (
        loaded.position_quantity
        == Decimal("0.12345678")
    )
    assert loaded.has_open_position is True


def test_decimal_is_saved_as_string(
    tmp_path,
) -> None:
    path = tmp_path / "controller.json"
    store = TradingControllerStateStore(path)

    store.save(
        TradingControllerState(
            position_quantity=Decimal("0.0500"),
        )
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert payload == {
        "position_quantity": "0.0500",
        "entry_price": None,
        "stop_loss": None,
    }


def test_creates_parent_directory(
    tmp_path,
) -> None:
    path = (
        tmp_path
        / "nested"
        / "state"
        / "controller.json"
    )

    store = TradingControllerStateStore(path)
    store.save(TradingControllerState())

    assert path.exists()


def test_rejects_invalid_json(
    tmp_path,
) -> None:
    path = tmp_path / "controller.json"
    path.write_text(
        "{invalid",
        encoding="utf-8",
    )

    store = TradingControllerStateStore(path)

    with pytest.raises(
        ValueError,
        match="failed to load controller state",
    ):
        store.load()


def test_rejects_non_object_json(
    tmp_path,
) -> None:
    path = tmp_path / "controller.json"
    path.write_text(
        '["0.1"]',
        encoding="utf-8",
    )

    store = TradingControllerStateStore(path)

    with pytest.raises(
        ValueError,
        match=(
            "controller state must be "
            "a JSON object"
        ),
    ):
        store.load()


@pytest.mark.parametrize(
    "value",
    [
        "not-a-number",
        None,
        {},
    ],
)
def test_rejects_invalid_position_quantity(
    tmp_path,
    value,
) -> None:
    path = tmp_path / "controller.json"
    path.write_text(
        json.dumps(
            {"position_quantity": value}
        ),
        encoding="utf-8",
    )

    store = TradingControllerStateStore(path)

    with pytest.raises(
        ValueError,
        match="invalid position_quantity",
    ):
        store.load()


def test_rejects_negative_position_quantity(
    tmp_path,
) -> None:
    path = tmp_path / "controller.json"
    path.write_text(
        json.dumps(
            {"position_quantity": "-0.01"}
        ),
        encoding="utf-8",
    )

    store = TradingControllerStateStore(path)

    with pytest.raises(
        ValueError,
        match=(
            "position_quantity must not "
            "be negative"
        ),
    ):
        store.load()


def test_overwrites_previous_state(
    tmp_path,
) -> None:
    path = tmp_path / "controller.json"
    store = TradingControllerStateStore(path)

    store.save(
        TradingControllerState(
            position_quantity=Decimal("0.1"),
        )
    )

    store.save(
        TradingControllerState(
            position_quantity=Decimal("0"),
        )
    )

    loaded = store.load()

    assert loaded.position_quantity == Decimal("0")
    assert loaded.has_open_position is False


def test_saves_and_loads_entry_price_and_stop_loss(
    tmp_path,
) -> None:
    path = tmp_path / "controller.json"
    store = TradingControllerStateStore(path)

    store.save(
        TradingControllerState(
            position_quantity=Decimal("0.01"),
            entry_price=Decimal("1950.25"),
            stop_loss=Decimal("1911.24"),
        )
    )

    loaded = store.load()

    assert loaded.position_quantity == Decimal("0.01")
    assert loaded.entry_price == Decimal("1950.25")
    assert loaded.stop_loss == Decimal("1911.24")


def test_loads_legacy_state_without_entry_data(
    tmp_path,
) -> None:
    path = tmp_path / "controller.json"
    path.write_text(
        '{"position_quantity": "0"}',
        encoding="utf-8",
    )

    loaded = TradingControllerStateStore(path).load()

    assert loaded.position_quantity == Decimal("0")
    assert loaded.entry_price is None
    assert loaded.stop_loss is None
