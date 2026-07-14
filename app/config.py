from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    symbol: str = "ETH/USDT"
    timeframe: str = "1h"
    start_balance: float = 1000.0
    fee_rate: float = 0.001

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Торговая пара не может быть пустой")

        if not self.timeframe.strip():
            raise ValueError("Таймфрейм не может быть пустым")

        if self.start_balance <= 0:
            raise ValueError(
                "Стартовый баланс должен быть больше нуля"
            )

        if not 0 <= self.fee_rate < 1:
            raise ValueError("Некорректная комиссия")


DEFAULT_CONFIG = BacktestConfig()

