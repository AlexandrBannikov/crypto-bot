from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal as D
import json, statistics
from pathlib import Path
from .framework import CanonicalJsonl, load_state
from .registry import ExperimentDefinition, ExperimentRegistry

def adequacy(n:int)->str:
    return "VERY_INSUFFICIENT" if n<10 else "INSUFFICIENT" if n<30 else "PRELIMINARY" if n<50 else "USABLE" if n<100 else "STRONGER_SAMPLE"

def metrics(spec:ExperimentDefinition, start:int|None=None,end:int|None=None)->dict:
    trades=CanonicalJsonl(spec.journal_path,()).rows(); equity=CanonicalJsonl(spec.equity_path,()).rows(); decisions=CanonicalJsonl(spec.decision_path,()).rows()
    def inside(r):
        ts=int(r.get("exit_timestamp") or r.get("candle_close_timestamp") or 0); return (start is None or ts>=start) and (end is None or ts<=end)
    trades=[r for r in trades if inside(r)]; equity=[r for r in equity if inside(r)]; decisions=[r for r in decisions if inside(r)]
    pnls=[float(r["realised_pnl"]) for r in trades]; wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
    fees=sum(float(r["total_fees"]) for r in trades); gross=sum(pnls)+fees; holds=[float(r["holding_time"])/3600 for r in trades]
    mfes=[float(r.get("MFE",0)) for r in trades]; maes=[float(r.get("MAE",0)) for r in trades]
    initial=float(spec.initial_balance); current=float(equity[-1]["equity"]) if equity else initial
    maximum_dd=max((float(r["drawdown"]) for r in equity),default=0)
    period=(max((int(r["candle_close_timestamp"]) for r in decisions),default=0)-min((int(r["candle_close_timestamp"]) for r in decisions),default=0))/86400 if decisions else 0
    return {"experiment_id":spec.experiment_id,"display_name":spec.display_name,"status":"disabled" if not spec.enabled else "running" if equity else "configured","decisions":len(decisions),"closed_trades":len(trades),"initial_balance":initial,"current_equity":current,"return_percent":(current/initial-1)*100,"max_drawdown":maximum_dd,"win_rate":len(wins)/len(pnls)*100 if pnls else None,"profit_factor":sum(wins)/abs(sum(losses)) if losses else None,"average_trade":statistics.mean(pnls) if pnls else None,"median_trade":statistics.median(pnls) if pnls else None,"average_win":statistics.mean(wins) if wins else None,"average_loss":statistics.mean(losses) if losses else None,"payoff_ratio":statistics.mean(wins)/abs(statistics.mean(losses)) if wins and losses else None,"total_fees":fees,"fees_pct_gross_pnl":fees/abs(gross)*100 if gross else None,"average_mfe":statistics.mean(mfes) if mfes else None,"average_mae":statistics.mean(maes) if maes else None,"average_holding_hours":statistics.mean(holds) if holds else None,"median_holding_hours":statistics.median(holds) if holds else None,"sample_adequacy":adequacy(len(trades)),"unique_market_episodes":len({int(r["entry_timestamp"])//(7*86400) for r in trades}),"non_overlapping_trade_count":len(trades),"observation_days":period,"active_market_share":len(decisions)/(period*24)*100 if period else 0,"data_quality":"OK"}

def comparison(registry:ExperimentRegistry,*,include_disabled=False,start=None,end=None,ids=())->list[dict]:
    rows=[metrics(s,start,end) for s in registry.all() if (include_disabled or s.enabled) and (not ids or s.experiment_id in ids)]
    baseline=next((r for r in rows if r["experiment_id"]=="control_baseline_v1"),None)
    for r in rows:
        r["baseline_difference"]={"return_delta":r["return_percent"]-baseline["return_percent"],"drawdown_delta":r["max_drawdown"]-baseline["max_drawdown"],"trade_count_delta":r["closed_trades"]-baseline["closed_trades"],"fee_delta":r["total_fees"]-baseline["total_fees"],"mfe_delta":None if r["average_mfe"] is None or baseline["average_mfe"] is None else r["average_mfe"]-baseline["average_mfe"],"mae_delta":None if r["average_mae"] is None or baseline["average_mae"] is None else r["average_mae"]-baseline["average_mae"]} if baseline else None
        r["research_status"]="DATA_QUALITY_ERROR" if r["data_quality"]!="OK" else "INSUFFICIENT_DATA" if r["closed_trades"]<30 else "CONTINUE"
    return rows

def render(rows:list[dict])->str:
    head=f"{'Experiment':24} {'Status':12} {'Dec':>5} {'Trades':>6} {'Return':>9} {'MaxDD':>8} {'Win%':>7} {'PF':>7} {'Fees':>8} {'AvgMFE':>8} {'AvgMAE':>8} {'Hold':>7} Data quality"
    lines=[head]
    for r in rows:
        f=lambda v,p=2:"N/A" if v is None else f"{v:.{p}f}"
        lines.append(f"{r['display_name'][:24]:24} {r['status'][:12]:12} {r['decisions']:5d} {r['closed_trades']:6d} {f(r['return_percent']):>9} {f(r['max_drawdown']):>8} {f(r['win_rate']):>7} {f(r['profit_factor']):>7} {f(r['total_fees']):>8} {f(r['average_mfe']):>8} {f(r['average_mae']):>8} {f(r['average_holding_hours']):>7} {r['sample_adequacy']}")
    return "\n".join(lines)
