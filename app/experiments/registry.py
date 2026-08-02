from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable


StrategyFactory = Callable[[], object]
ALLOWED_STRATEGIES = {"control_ema_cross_v1", "relaxed_ema_gate_v1", "scored_allocation_v1"}


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    experiment_id: str
    display_name: str
    strategy_version: str
    enabled: bool
    execution_mode: str
    initial_balance: Decimal
    symbol: str
    timeframe: int
    risk_profile: str
    strategy_factory: StrategyFactory
    config: dict = field(default_factory=dict)
    root_path: Path = Path(".")
    created_at: str = "2026-08-01"
    description: str = ""
    hypothesis: str = ""
    changed_parameter: str = ""
    baseline_experiment_id: str | None = None
    review: dict = field(default_factory=dict)

    @property
    def state_path(self) -> Path: return self.root_path / "runtime.json"
    @property
    def decision_path(self) -> Path: return self.root_path / "decisions.jsonl"
    @property
    def journal_path(self) -> Path: return self.root_path / "trades.jsonl"
    @property
    def equity_path(self) -> Path: return self.root_path / "equity.jsonl"
    @property
    def lock_path(self) -> Path: return self.root_path / "runtime.lock"
    @property
    def summary_path(self) -> Path: return self.root_path / "summary.json"


class ExperimentRegistry:
    def __init__(self, definitions: list[ExperimentDefinition]):
        self._items: dict[str, ExperimentDefinition] = {}
        paths: dict[Path, str] = {}
        for item in definitions:
            if item.experiment_id in self._items:
                raise ValueError(f"duplicate experiment_id: {item.experiment_id}")
            if item.execution_mode != "paper_research":
                raise ValueError("execution_mode must be paper_research")
            if item.strategy_version not in ALLOWED_STRATEGIES:
                raise ValueError(f"unknown strategy: {item.strategy_version}")
            if not item.changed_parameter or not item.hypothesis:
                raise ValueError("hypothesis and changed_parameter are required")
            root = item.root_path.resolve()
            if ".." in item.root_path.parts:
                raise ValueError("path traversal is forbidden")
            for path in (item.state_path, item.decision_path, item.journal_path,
                         item.equity_path, item.lock_path, item.summary_path):
                resolved = path.resolve()
                if resolved in paths:
                    raise ValueError(f"shared runtime path: {resolved}")
                paths[resolved] = item.experiment_id
            self._items[item.experiment_id] = replace(item, root_path=root)

    def all(self) -> tuple[ExperimentDefinition, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def get(self, experiment_id: str) -> ExperimentDefinition:
        try: return self._items[experiment_id]
        except KeyError as exc: raise KeyError(f"unknown experiment_id: {experiment_id}") from exc


def _factory(name: str) -> StrategyFactory:
    # Closed allow-list; no dynamic imports or user code.
    return lambda: name


def build_registry(root: Path, *, enabled_ids: tuple[str, ...] = ()) -> ExperimentRegistry:
    base = root.resolve() / "state" / "experiments"
    common = dict(execution_mode="paper_research", initial_balance=Decimal("1000"),
                  symbol="ETHUSDT", timeframe=60, risk_profile="risk_1pct_stop_2pct_cap_100pct",
                  created_at=str(date(2026, 8, 1)), review={"minimum_closed_trades": 50,
                  "minimum_unique_episodes": 30, "minimum_runtime_days": 60,
                  "maximum_acceptable_dd": 20, "maximum_fee_ratio": 50,
                  "review_after_date": "2026-09-30"})
    definitions = [
        ExperimentDefinition("control_baseline_v1", "Control Baseline", "control_ema_cross_v1",
            "control_baseline_v1" in enabled_ids, strategy_factory=_factory("control"),
            root_path=base/"control_baseline_v1", description="Frozen research copy of Production Control",
            hypothesis="Current unchanged strategy used as baseline", changed_parameter="none", **common),
        ExperimentDefinition("relaxed_signal_v1", "Relaxed Signal", "relaxed_ema_gate_v1",
            "relaxed_signal_v1" in enabled_ids, strategy_factory=_factory("relaxed"),
            root_path=base/"relaxed_signal_v1", description="Single-gate research variant",
            hypothesis="Bullish EMA alignment increases trades without materially worsening MAE",
            changed_parameter="entry gate: crossover event -> EMA20 > EMA50 alignment",
            baseline_experiment_id="control_baseline_v1", **common),
        ExperimentDefinition("scored_allocation_v1", "Scored Allocation", "scored_allocation_v1",
            False, strategy_factory=_factory("scored"), root_path=base/"scored_allocation_v1",
            description="Disabled until execution semantics are independently validated",
            hypothesis="Existing score_v1 continuous allocation improves risk efficiency",
            changed_parameter="position risk fraction from existing unchanged score_v1", config={"disabled_reason": "paper execution validation pending", "score_version": "score_v1", "minimum_entry_score": 65},
            baseline_experiment_id="control_baseline_v1", **common),
    ]
    return ExperimentRegistry(definitions)
