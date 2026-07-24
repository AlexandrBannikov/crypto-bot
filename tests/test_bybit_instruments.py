from decimal import Decimal

import pytest

from app.bybit_instruments import (
    INSTRUMENTS_INFO_PATH,
    BybitInstrumentClient,
    InstrumentInfo,
)


def test_instrument_info_normalizes_values() -> None:
    instrument = InstrumentInfo(
        symbol=" ethusdt ",
        status=" Trading ",
        tick_size=Decimal("0.01"),
        qty_step=Decimal("0.0001"),
        min_order_qty=Decimal("0.0001"),
        max_order_qty=Decimal("100"),
        min_order_value=Decimal("5"),
    )

    assert instrument.symbol == "ETHUSDT"
    assert instrument.status == "Trading"
    assert instrument.is_trading is True


def test_client_gets_spot_instrument_info() -> None:
    calls = []

    def fake_get_json(url, timeout_seconds):
        calls.append((url, timeout_seconds))
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "spot",
                "list": [
                    {
                        "symbol": "ETHUSDT",
                        "status": "Trading",
                        "priceFilter": {
                            "tickSize": "0.01",
                        },
                        "lotSizeFilter": {
                            "basePrecision": "0.000001",
                            "quotePrecision": "0.0000001",
                            "minOrderQty": "0.0001",
                            "maxLimitOrderQty": "100",
                            "minOrderAmt": "5",
                        },
                    }
                ],
            },
        }

    client = BybitInstrumentClient(
        base_url="https://example.test",
        http_get_json=fake_get_json,
        timeout_seconds=3,
    )

    instrument = client.get_spot_instrument("ethusdt")

    assert instrument.symbol == "ETHUSDT"
    assert instrument.status == "Trading"
    assert instrument.tick_size == Decimal("0.01")
    assert instrument.qty_step == Decimal("0.000001")
    assert instrument.min_order_qty == Decimal("0.0001")
    assert instrument.max_order_qty == Decimal("100")
    assert instrument.min_order_value == Decimal("5")
    assert calls == [
        (
            "https://example.test"
            f"{INSTRUMENTS_INFO_PATH}?category=spot&symbol=ETHUSDT",
            3,
        )
    ]


def test_client_reports_missing_instrument() -> None:
    def fake_get_json(url, timeout_seconds):
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "spot",
                "list": [],
            },
        }

    client = BybitInstrumentClient(
        http_get_json=fake_get_json,
    )

    with pytest.raises(
        LookupError,
        match="Spot instrument UNKNOWNUSDT was not found",
    ):
        client.get_spot_instrument("UNKNOWNUSDT")


def test_client_rejects_api_error() -> None:
    def fake_get_json(url, timeout_seconds):
        return {
            "retCode": 10001,
            "retMsg": "Request parameter error",
        }

    client = BybitInstrumentClient(
        http_get_json=fake_get_json,
    )

    with pytest.raises(
        RuntimeError,
        match="Bybit API error 10001",
    ):
        client.get_spot_instrument("ETHUSDT")
