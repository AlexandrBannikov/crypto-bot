from app.models import PaperStatistics


def test_create_paper_statistics() -> None:
    stats = PaperStatistics(
        start_balance=1000.0,
        current_balance=1085.5,
        net_profit=85.5,
        return_percent=8.55,
        total_trades=12,
        winning_trades=7,
        losing_trades=5,
        win_rate_percent=58.33,
        gross_profit=140.0,
        gross_loss=-54.5,
        profit_factor=2.57,
        average_win=20.0,
        average_loss=-10.9,
        max_drawdown_percent=4.2,
    )

    assert stats.start_balance == 1000.0
    assert stats.current_balance == 1085.5
    assert stats.total_trades == 12
    assert stats.winning_trades == 7
    assert stats.losing_trades == 5
    assert stats.profit_factor == 2.57
