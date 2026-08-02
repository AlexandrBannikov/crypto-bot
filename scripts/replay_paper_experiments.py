from __future__ import annotations
import argparse,sys,tempfile
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.candle import Candle
from app.experiments.framework import MarketSnapshot,process_experiment
from app.experiments.registry import build_registry
from app.experiments.reporting import comparison,render
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--data",type=Path,default=ROOT/"data/eth_usdt_1h.csv");p.add_argument("--output",type=Path,default=ROOT/"reports/experiments/bootstrap_v1");a=p.parse_args(argv);df=pd.read_csv(a.data); candles=[Candle(int(pd.Timestamp(r.datetime).timestamp()),float(r.open),float(r.high),float(r.low),float(r.close),float(r.volume)) for r in df.itertuples()]
 reg=build_registry(a.output.parent.parent,enabled_ids=("control_baseline_v1","relaxed_signal_v1"))
 # Registry root convention is <root>/state/experiments; isolate replay under output.
 from dataclasses import replace
 specs=[replace(s,root_path=a.output/s.experiment_id) for s in reg.all() if s.enabled]
 for i,c in enumerate(candles):
  snap=MarketSnapshot.from_candle(c,"ETHUSDT",60,"historical_csv")
  for s in specs: process_experiment(s,snap,candles[:i+1])
 from app.experiments.registry import ExperimentRegistry
 rows=comparison(ExperimentRegistry(specs),include_disabled=True);print(render(rows));return 0
if __name__=="__main__":raise SystemExit(main())
