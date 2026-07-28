from pathlib import Path

from app.config import PaperStrategyConfig
from scripts import run_bybit_controller
from tests.conftest import PRODUCTION_ROOTS


def test_runtime_defaults_are_redirected_outside_production(
    isolated_runtime_artifacts: Path,
) -> None:
    paths = (
        run_bybit_controller.STATE_PATH,
        run_bybit_controller.LAST_CANDLE_PATH,
        run_bybit_controller.RUNTIME_STATE_PATH,
        run_bybit_controller.JOURNAL_PATH,
        run_bybit_controller.DEFAULT_LOCK_PATH,
        run_bybit_controller.DEFAULT_STATISTICS_REPORT_PATH,
        run_bybit_controller.DEFAULT_STATISTICS_PLOT_PATH,
        PaperStrategyConfig.from_env().shadow_diagnostics_path,
    )
    for path in paths:
        resolved = Path(path).resolve()
        assert resolved.is_relative_to(
            isolated_runtime_artifacts.resolve()
        )
        assert not any(
            resolved.is_relative_to(root.resolve())
            for root in PRODUCTION_ROOTS
        )
