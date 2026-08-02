from __future__ import annotations
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.bybit_market_data import BybitMarketDataConfig,BybitMarketDataFeed
from app.experiments.framework import ExperimentCoordinator
from app.experiments.registry import build_registry
from app.process_lock import ProcessLock
def main():
 if os.getenv("EXPERIMENTS_ENABLED","false").lower() not in {"1","true","yes","on"}: print("Experiments disabled");return 0
 ids=tuple(x.strip() for x in os.getenv("EXPERIMENT_IDS","control_baseline_v1").split(",") if x.strip());reg=build_registry(ROOT,enabled_ids=ids)
 with ProcessLock(Path(os.getenv("EXPERIMENTS_LOCK_PATH",ROOT/"state/experiments/coordinator.lock"))):
  candles=BybitMarketDataFeed(BybitMarketDataConfig(symbol=os.getenv("EXPERIMENTS_SYMBOL","ETHUSDT"),interval=os.getenv("EXPERIMENTS_TIMEFRAME","60"),category="spot",limit=500,closed_candles_only=True)).get_candles();print(json.dumps(ExperimentCoordinator(reg).run(candles),indent=2))
 return 0
if __name__=="__main__":raise SystemExit(main())
