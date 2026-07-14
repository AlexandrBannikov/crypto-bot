from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Trade:
    side: TradeSide
    timestamp: datetime
    price: float
    quantity: float
    fee: float
    balance_after: float


@dataclass
class BacktestResult:
    start_balance: float
    final_balance: float
    return_percent: float
    max_drawdown_percent: float
    total_fees: float
    operations: int
    completed_trades: int
    winning_trades: int
    win_rate_percent: float
    trades: list[Trade]

