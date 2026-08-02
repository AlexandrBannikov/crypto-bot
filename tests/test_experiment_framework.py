from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import json
import pytest

from app.candle import Candle
from app.experiments.framework import (CanonicalJsonl, ConflictError, Decision,
 ExperimentCoordinator, ExperimentPaperExecutor, ExperimentState, MarketSnapshot,
 process_experiment)
from app.experiments.registry import ExperimentDefinition,ExperimentRegistry,build_registry
from app.experiments.reporting import adequacy,comparison

def candles(n=60,start=1_700_000_000,rising=True):
 out=[]
 for i in range(n):
  price=100+i if rising else 160-i
  out.append(Candle(start+i*3600,price-1,price+2,price-2,price,10))
 return out

def isolated(tmp_path,enabled=("control_baseline_v1","relaxed_signal_v1")):
 reg=build_registry(tmp_path,enabled_ids=enabled)
 return ExperimentRegistry([replace(x,root_path=tmp_path/x.experiment_id) for x in reg.all()])

def test_registry_order_defaults_and_disabled(tmp_path):
 reg=isolated(tmp_path)
 assert [x.experiment_id for x in reg.all()]==sorted(x.experiment_id for x in reg.all())
 assert not reg.get("scored_allocation_v1").enabled
 assert all(x.execution_mode=="paper_research" for x in reg.all())

def test_registry_duplicate_id_path_mode_strategy_denied(tmp_path):
 one=isolated(tmp_path).get("control_baseline_v1")
 with pytest.raises(ValueError,match="duplicate experiment_id"):ExperimentRegistry([one,one])
 with pytest.raises(ValueError,match="paper_research"):ExperimentRegistry([replace(one,execution_mode="real")])
 with pytest.raises(ValueError,match="unknown strategy"):ExperimentRegistry([replace(one,strategy_version="evil")])
 with pytest.raises(ValueError,match="shared runtime path"):ExperimentRegistry([one,replace(one,experiment_id="other")])

def test_path_traversal_denied(tmp_path):
 one=isolated(tmp_path).get("control_baseline_v1")
 with pytest.raises(ValueError,match="traversal"):ExperimentRegistry([replace(one,root_path=Path("safe/../bad"))])

def test_canonical_duplicate_and_conflict(tmp_path):
 store=CanonicalJsonl(tmp_path/"x.jsonl",("experiment_id","strategy_version","candle_close_timestamp"));row={"experiment_id":"a","strategy_version":"v","candle_close_timestamp":1,"equity":"1"}
 assert store.append(row);assert not store.append(row)
 with pytest.raises(ConflictError):store.append({**row,"equity":"2"})

def test_same_snapshot_and_idempotency_isolation(tmp_path):
 reg=isolated(tmp_path); coord=ExperimentCoordinator(reg); cs=candles()
 first=coord.run(cs); second=coord.run(cs)
 assert {r["candle_close_timestamp"] for r in first}=={cs[-1].timestamp+3600}
 assert all(not r["processed"] for r in second)
 a,b=reg.get("control_baseline_v1"),reg.get("relaxed_signal_v1")
 assert a.state_path!=b.state_path and a.decision_path!=b.decision_path
 assert len(CanonicalJsonl(a.decision_path,()).rows())==1
 assert len(CanonicalJsonl(b.decision_path,()).rows())==1

def test_out_of_order_rejected(tmp_path):
 spec=isolated(tmp_path,("control_baseline_v1",)).get("control_baseline_v1");cs=candles()
 process_experiment(spec,MarketSnapshot.from_candle(cs[-1],spec.symbol,60),cs)
 with pytest.raises(ValueError,match="out-of-order"):process_experiment(spec,MarketSnapshot.from_candle(cs[-2],spec.symbol,60),cs[:-1])

def test_executor_enter_hold_stop_fee_mfe_mae_and_no_real(tmp_path):
 spec=isolated(tmp_path).get("control_baseline_v1");state=ExperimentState(spec.experiment_id,spec.strategy_version)
 snap=MarketSnapshot.from_candle(Candle(1,100,103,99,100,1),spec.symbol,60)
 ex=ExperimentPaperExecutor();entered=ex.execute(spec,state,Decision("ENTER","enter",None,None,("x",),(),{},1,98),snap)
 assert Decimal(entered.state.quantity)>0 and entered.fee>0 and entered.state.open_trade["MFE"]!="0"
 stopped=ex.execute(spec,entered.state,Decision("HOLD","hold",None,None,(),(),{},0,None),MarketSnapshot.from_candle(Candle(3601,100,101,97,99,1),spec.symbol,60))
 assert stopped.trade_event["exit_reason"]=="stop_loss" and Decimal(stopped.state.quantity)==0
 with pytest.raises(ValueError,match="forbidden"):ExperimentPaperExecutor(execution_mode="real")

def test_executor_minimum_and_cap(tmp_path):
 spec=isolated(tmp_path).get("control_baseline_v1");state=ExperimentState(spec.experiment_id,spec.strategy_version)
 ex=ExperimentPaperExecutor(minimum_notional=Decimal("10000"));r=ex.execute(spec,state,Decision("ENTER","e",None,None,(),(),{},1,98),MarketSnapshot.from_candle(Candle(1,100,101,99,100),spec.symbol,60))
 assert r.execution_reason=="minimum_order" and state.skipped_minimum_order_count==1

def test_adequacy_boundaries():
 assert [adequacy(x) for x in (0,9,10,29,30,49,50,99,100)]==["VERY_INSUFFICIENT","VERY_INSUFFICIENT","INSUFFICIENT","INSUFFICIENT","PRELIMINARY","PRELIMINARY","USABLE","USABLE","STRONGER_SAMPLE"]

def test_comparison_zero_trades_and_disabled(tmp_path):
 rows=comparison(isolated(tmp_path),include_disabled=True)
 assert len(rows)==3 and rows[0]["sample_adequacy"]=="VERY_INSUFFICIENT"
 assert next(x for x in rows if x["experiment_id"]=="scored_allocation_v1")["status"]=="disabled"

def test_production_candidate_paths_not_referenced(tmp_path):
 reg=isolated(tmp_path)
 paths=" ".join(str(p) for s in reg.all() for p in (s.state_path,s.decision_path,s.journal_path,s.equity_path))
 assert "bybit_paper" not in paths and "candidate_shadow" not in paths
