import pytest

from app.bybit_account import BybitAccountConfig


def test_bybit_account_config_normalizes_credentials() -> None:
    config = BybitAccountConfig(
        api_key="  test-key  ",
        api_secret="  test-secret  ",
    )

    assert config.api_key == "test-key"
    assert config.api_secret == "test-secret"
    assert config.testnet is False
    assert config.recv_window == 5000
    assert config.timeout_seconds == 10.0


@pytest.mark.parametrize(
    ("api_key", "api_secret"),
    [
        ("", "secret"),
        ("   ", "secret"),
        ("key", ""),
        ("key", "   "),
    ],
)
def test_bybit_account_config_rejects_empty_credentials(
    api_key: str,
    api_secret: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        BybitAccountConfig(
            api_key=api_key,
            api_secret=api_secret,
        )


def test_bybit_account_config_rejects_invalid_recv_window() -> None:
    with pytest.raises(
        ValueError,
        match="recv_window must be greater than zero",
    ):
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            recv_window=0,
        )


def test_bybit_account_config_rejects_invalid_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds must be greater than zero",
    ):
        BybitAccountConfig(
            api_key="key",
            api_secret="secret",
            timeout_seconds=0,
        )
