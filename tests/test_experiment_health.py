from dataclasses import replace
from app.experiments.health import research_health
from app.experiments.registry import ExperimentRegistry,build_registry

def test_optional_health_does_not_reference_production(tmp_path):
 base=build_registry(tmp_path,enabled_ids=("control_baseline_v1",))
 reg=ExperimentRegistry([replace(x,root_path=tmp_path/x.experiment_id) for x in base.all()])
 result=research_health(reg)
 assert result=={"status":"OK","configured":3,"enabled":1,"running":0,"errors":[],"last_cycle":None,"total_closed_trades":0}
