from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_candle_consumers_outlive_readiness_window() -> None:
    for name in (
        "crypto-paper.service",
        "crypto-paper-candidate.service",
        "crypto-scored-candidate-shadow.service",
    ):
        unit = (ROOT / "deploy/systemd" / name).read_text(encoding="utf-8")
        assert "Type=oneshot" in unit
        assert "TimeoutStartSec=120" in unit
