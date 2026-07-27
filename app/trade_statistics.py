from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.trade_journal import TradeJournalEntry


ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class TradeStatistics:
    """Aggregated statistics for closed trade-journal records.

    Financial values use ``Decimal``.  Empty inputs produce zero counts,
    zero sums/averages/extremes and an empty equity curve.  ``profit_factor``
    is ``None`` when there are no losing trades, because division by zero is
    undefined.  ``gross_loss`` is positive, while ``average_loss`` retains
    the negative sign of losing trades.  ``recovery_factor`` is ``None`` when
    there is no drawdown.

    Drawdown starts from the balance reconstructed before the first record.
    Absolute drawdown is still measured when the running peak is zero, but
    percentage drawdown is skipped until a positive peak exists; this avoids
    inventing a percentage for division by zero.
    """

    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    average_net_pnl: Decimal
    average_win: Decimal
    average_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal
    max_drawdown_absolute: Decimal
    max_drawdown_percent: Decimal
    recovery_factor: Decimal | None
    longest_win_streak: int
    longest_loss_streak: int
    average_holding_seconds: Decimal
    min_holding_seconds: Decimal
    max_holding_seconds: Decimal
    starting_balance: Decimal
    ending_balance: Decimal
    equity_curve: tuple[Decimal, ...]


def _holding_seconds(entry: TradeJournalEntry) -> Decimal:
    timestamps: dict[str, datetime] = {}
    for field_name in ("opened_at", "closed_at"):
        value = getattr(entry, field_name)
        try:
            timestamps[field_name] = datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid {field_name} for trade journal entry "
                f"{entry.record_id!r}: {value!r}"
            ) from exc

    try:
        seconds = (
            timestamps["closed_at"] - timestamps["opened_at"]
        ).total_seconds()
    except TypeError as exc:
        raise ValueError(
            "opened_at and closed_at must use compatible timezones "
            f"for trade journal entry {entry.record_id!r}"
        ) from exc

    if seconds < 0:
        raise ValueError(
            "closed_at must not be earlier than opened_at "
            f"for trade journal entry {entry.record_id!r}"
        )
    return Decimal(str(seconds))


def calculate_drawdown_curve(
    starting_balance: Decimal,
    equity_curve: Sequence[Decimal],
) -> tuple[Decimal, ...]:
    """Return absolute drawdown for the starting point and each equity value.

    Drawdown is measured from the historical maximum equity and is always
    non-negative.  The first result is always ``Decimal("0")`` for
    ``starting_balance``; consequently an empty ``equity_curve`` returns a
    one-item tuple.  Zero and negative balances use the same peak-minus-equity
    definition without percentage calculations or special cases.
    """

    peak = starting_balance
    drawdowns = [ZERO]
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdowns.append(max(ZERO, peak - equity))
    return tuple(drawdowns)


def _calculate_drawdown(
    *,
    starting_balance: Decimal,
    equity_curve: Sequence[Decimal],
) -> tuple[Decimal, Decimal]:
    peak = starting_balance
    drawdown_curve = calculate_drawdown_curve(
        starting_balance,
        equity_curve,
    )
    maximum_absolute = max(drawdown_curve)
    maximum_percent = ZERO

    for equity, absolute in zip(equity_curve, drawdown_curve[1:]):
        if equity > peak:
            peak = equity

        if peak > ZERO:
            percentage = absolute / peak * HUNDRED
            maximum_percent = max(maximum_percent, percentage)

    return maximum_absolute, maximum_percent


def calculate_trade_statistics(
    entries: Sequence[TradeJournalEntry],
) -> TradeStatistics:
    """Calculate statistics, treating every journal record as one trade.

    This includes records produced by partial position closes.  The function
    performs no I/O and preserves journal order in ``equity_curve``.
    """

    total_trades = len(entries)
    winning = [entry.net_pnl for entry in entries if entry.net_pnl > ZERO]
    losing = [entry.net_pnl for entry in entries if entry.net_pnl < ZERO]
    winning_trades = len(winning)
    losing_trades = len(losing)
    breakeven_trades = total_trades - winning_trades - losing_trades

    gross_profit = sum(winning, ZERO)
    losing_total = sum(losing, ZERO)
    gross_loss = abs(losing_total)
    gross_pnl = sum((entry.gross_pnl for entry in entries), ZERO)
    total_fees = sum((entry.total_fee for entry in entries), ZERO)
    net_pnl = sum((entry.net_pnl for entry in entries), ZERO)
    average_net_pnl = (
        net_pnl / total_trades if total_trades else ZERO
    )
    average_win = (
        gross_profit / winning_trades if winning_trades else ZERO
    )
    average_loss = (
        losing_total / losing_trades if losing_trades else ZERO
    )
    largest_win = (
        max(entry.net_pnl for entry in entries) if entries else ZERO
    )
    largest_loss = (
        min(entry.net_pnl for entry in entries) if entries else ZERO
    )
    profit_factor = (
        gross_profit / gross_loss if gross_loss > ZERO else None
    )

    equity_curve = tuple(
        entry.virtual_balance_after for entry in entries
    )
    if entries:
        starting_balance = (
            entries[0].virtual_balance_after - entries[0].net_pnl
        )
        ending_balance = entries[-1].virtual_balance_after
    else:
        starting_balance = ZERO
        ending_balance = ZERO

    max_drawdown_absolute, max_drawdown_percent = _calculate_drawdown(
        starting_balance=starting_balance,
        equity_curve=equity_curve,
    )
    recovery_factor = (
        net_pnl / max_drawdown_absolute
        if max_drawdown_absolute > ZERO
        else None
    )

    longest_win_streak = 0
    longest_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0
    for entry in entries:
        if entry.net_pnl > ZERO:
            current_win_streak += 1
            current_loss_streak = 0
        elif entry.net_pnl < ZERO:
            current_loss_streak += 1
            current_win_streak = 0
        else:
            current_win_streak = 0
            current_loss_streak = 0
        longest_win_streak = max(
            longest_win_streak, current_win_streak
        )
        longest_loss_streak = max(
            longest_loss_streak, current_loss_streak
        )

    holding_seconds = [_holding_seconds(entry) for entry in entries]
    average_holding_seconds = (
        sum(holding_seconds, ZERO) / total_trades
        if total_trades
        else ZERO
    )

    return TradeStatistics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        breakeven_trades=breakeven_trades,
        win_rate=(
            Decimal(winning_trades) / total_trades * HUNDRED
            if total_trades
            else ZERO
        ),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        gross_pnl=gross_pnl,
        total_fees=total_fees,
        net_pnl=net_pnl,
        average_net_pnl=average_net_pnl,
        average_win=average_win,
        average_loss=average_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
        profit_factor=profit_factor,
        expectancy=average_net_pnl,
        max_drawdown_absolute=max_drawdown_absolute,
        max_drawdown_percent=max_drawdown_percent,
        recovery_factor=recovery_factor,
        longest_win_streak=longest_win_streak,
        longest_loss_streak=longest_loss_streak,
        average_holding_seconds=average_holding_seconds,
        min_holding_seconds=(
            min(holding_seconds) if holding_seconds else ZERO
        ),
        max_holding_seconds=(
            max(holding_seconds) if holding_seconds else ZERO
        ),
        starting_balance=starting_balance,
        ending_balance=ending_balance,
        equity_curve=equity_curve,
    )
