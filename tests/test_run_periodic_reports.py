from datetime import date
from pathlib import Path

import scripts.run_periodic_reports as driver


class Clock:
    @staticmethod
    def now(zone):
        class Value:
            date = staticmethod(lambda: date(2026, 1, 6))
        return Value()


def test_periodic_does_not_overwrite_without_force(monkeypatch, tmp_path):
    monkeypatch.setattr(driver, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(driver, "datetime", Clock)
    base = tmp_path / "reports/runtime/daily/2026-01-05"
    base.parent.mkdir(parents=True)
    base.with_suffix(".json").write_text("old")
    base.with_suffix(".txt").write_text("old")
    monkeypatch.setattr(driver.daily, "create_report", lambda args: (_ for _ in ()).throw(AssertionError("overwritten")))
    assert driver.main(["--daily-only"]) == 0


def test_force_overwrites(monkeypatch, tmp_path):
    monkeypatch.setattr(driver, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(driver, "datetime", Clock)
    called = []
    monkeypatch.setattr(driver.daily, "create_report", lambda args: called.append(args))
    assert driver.main(["--daily-only", "--force"]) == 0
    assert called


def test_templates_use_absolute_paths_and_shadow():
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/crypto-paper-shadow.service").read_text()
    assert "/opt/crypto-bot/venv/bin/python" in service
    assert "--strategy-mode shadow" in service
    assert "bybit_executor" not in service
