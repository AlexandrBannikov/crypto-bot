from __future__ import annotations
import argparse,csv,json,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from app.experiments.registry import build_registry
from app.experiments.reporting import comparison,render

def parse_time(v): return int(datetime.fromisoformat(v.replace("Z","+00:00")).timestamp()) if v else None
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument("--hours",type=int);p.add_argument("--days",type=int);p.add_argument("--from",dest="start");p.add_argument("--to",dest="end");p.add_argument("--experiment",action="append",default=[]);p.add_argument("--json",action="store_true");p.add_argument("--csv",action="store_true");p.add_argument("--include-disabled",action="store_true");a=p.parse_args(argv)
 end=parse_time(a.end); start=parse_time(a.start)
 if a.hours or a.days: end=end or int(datetime.now(timezone.utc).timestamp());start=end-(a.hours or a.days*24)*3600
 reg=build_registry(ROOT,enabled_ids=("control_baseline_v1","relaxed_signal_v1"));rows=comparison(reg,include_disabled=a.include_disabled,start=start,end=end,ids=tuple(a.experiment))
 if a.json: print(json.dumps(rows,indent=2,allow_nan=False))
 elif a.csv:
  fields=list(rows[0]) if rows else [];w=csv.DictWriter(sys.stdout,fieldnames=fields);w.writeheader();w.writerows({k:json.dumps(v) if isinstance(v,dict) else v for k,v in r.items()} for r in rows)
 else: print(render(rows))
 return 0
if __name__=="__main__":raise SystemExit(main())
