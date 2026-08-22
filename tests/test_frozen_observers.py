import sys

from scripts import run_scored_threshold60_shadow, run_scored_threshold62_shadow


def test_threshold60_runner_is_frozen_without_touching_market(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["threshold60"])
    monkeypatch.setattr(
        run_scored_threshold60_shadow, "BybitMarketDataFeed",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("frozen observer requested market data")
        ),
    )
    assert run_scored_threshold60_shadow.main() == 0
    assert "frozen" in capsys.readouterr().out


def test_threshold62_runner_is_frozen_without_touching_market(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["threshold62"])
    monkeypatch.setattr(
        run_scored_threshold62_shadow, "BybitMarketDataFeed",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("frozen observer requested market data")
        ),
    )
    assert run_scored_threshold62_shadow.main() == 0
    assert "frozen" in capsys.readouterr().out
