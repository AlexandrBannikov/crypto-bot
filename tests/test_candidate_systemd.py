from pathlib import Path


def test_candidate_systemd_is_paper_only_and_offset():
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/crypto-paper-candidate.service").read_text()
    timer = (root / "deploy/systemd/crypto-paper-candidate.timer").read_text()
    env = (root / "deploy/crypto-paper-candidate.env.example").read_text()
    assert "run_paper_candidate.py" in service
    assert "bybit_candidate.lock" in service
    assert "OnCalendar=*-*-* *:01/5:15 UTC" in timer
    assert "LIVE_TRADING_ENABLED=false" in env
    assert "bybit_executor" not in service
    assert "crypto-paper.service" not in service
    assert "report_paper_comparison.py" not in service
    health = (
        root / "deploy/systemd/crypto-paper-candidate-health.service"
    ).read_text()
    assert "check_candidate_health.py" in health
    assert "crypto-paper-health" not in health


def test_comparison_is_a_daily_oneshot_with_deterministic_offset():
    root = Path(__file__).resolve().parents[1]
    service = (
        root / "deploy/systemd/crypto-paper-comparison.service"
    ).read_text()
    timer = (
        root / "deploy/systemd/crypto-paper-comparison.timer"
    ).read_text()
    assert "Type=oneshot" in service
    assert "report_paper_comparison.py --daily --timezone UTC" in service
    assert "OnCalendar=*-*-* 00:15:00 UTC" in timer
