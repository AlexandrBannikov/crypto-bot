from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BybitAccountConfig:
    api_key: str
    api_secret: str
    testnet: bool = False
    recv_window: int = 5000
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        api_key = self.api_key.strip()
        api_secret = self.api_secret.strip()

        if not api_key:
            raise ValueError("api_key must not be empty")

        if not api_secret:
            raise ValueError("api_secret must not be empty")

        if self.recv_window <= 0:
            raise ValueError(
                "recv_window must be greater than zero"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "api_secret", api_secret)


from decimal import Decimal


@dataclass(frozen=True, slots=True)
class WalletBalance:
    coin: str
    wallet_balance: Decimal
    available_balance: Decimal

    def __post_init__(self) -> None:
        coin = self.coin.strip().upper()

        if not coin:
            raise ValueError("coin must not be empty")

        if self.wallet_balance < 0 or self.available_balance < 0:
            raise ValueError("balance must not be negative")

        if self.available_balance > self.wallet_balance:
            raise ValueError(
                "available_balance must not exceed wallet_balance"
            )

        object.__setattr__(self, "coin", coin)
