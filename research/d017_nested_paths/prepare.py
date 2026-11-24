"""Materialize input/audit only. No thermal search or parameter selection."""
from common import *
from dataclasses import asdict
import csv

def csvout(path, rows):
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    frozen,loads=definitions()
    warm=json.loads((ROOT/"research/multidnn_model_review/inputs/cases/balanced_forward_preheated.json").read_bytes())["initial_c"]
    cfg=dict(schema="d017-nested-paths/v1",date="2026-11-24",
        source_parent="d61e84d13f6ee1063e53f71999a6ab6df23274ac",
        ambient_C=[25,30], initial_C=dict(reference=[30.,30.,30.,30.],preheated=warm),
        modes=list(MODES),period_ns=PERIOD,limit_C=80.,opps=list(catalog.OPPS),
        batch_wall_budget_s=900,admission_stop_s=895,formal_repetitions=1,
        thermal_peak_width_C=thermal.DEFAULT_PEAK_WIDTH,
        tie_energy_J=1e-7,dominance_temperature_C=0.001,dominance_slack_ms=1e-6,
        material_energy_percent=0.1,
        scope="single 40 ms cycle and original 62/63-cycle scene residence, no 10.04 s whole-flow claim",
        warm_at_30C="common exogenous initial vector originally generated at ambient 25C",
        power_control="ideal zero overhead; never changes compute OPP, order, active power, requests or resident stages")
    resident=sorted({(a,*s) for a,ss in BASE["deployments"]["D017"]["stages"].items() for s in ss if s[0].startswith("DLA")})
    assert resident==[("0","DLA0",0,29),("0","DLA1",30,40),("3","DLA0",37,78),("3","DLA1",0,36)]
    audits=[];profiles=[]
    for path,d in frozen["deployments"].items():
        used=[]
        for a,chain in d["stages"].items():
            cuts=catalog.check_chain(a,chain)
            used += [(a,*s) for s in chain if s[0].startswith("DLA")]
            audits.append(dict(path=path,app=int(a),stages=chain,live_tensors=cuts,
                complete=True,abstract_operator_legal=True,hardware_engine_verified=False))
        assert set(used)<=set(resident)
        old=BASE["deployments"][path.rstrip("*")]["stages"]
        if path.endswith("*"):
            assert d["stages"]!=old and d["stages"]==catalog._swap(old)
        else: assert d["stages"]==old
        for opp in catalog.OPPS:
            for a,chain in build_chains(PLATFORM,frozen,path,opp).items():
                for i,s in enumerate(chain):
                    profiles.append(dict(path=path,opp=opp,app=a,index=i,**asdict(s),
                        activity_energy_J=s.duration_ns*1e-9*s.activity_w))
    save(HERE/"config.json",cfg);save(HERE/"inputs.json",dict(frozen=frozen,loads=loads,resident=resident))
    save(HERE/"path_audit.json",audits);csvout(HERE/"stage_profiles.csv",profiles)
    print(dict(paths=len(frozen["deployments"]),unique_loads=len(loads),
        cycle_actions=len(loads)*243,dwell_actions=sum(len(r["frames"]) for r in loads.values())*243,
        resident=resident,profiles=len(profiles)))

if __name__=="__main__":main()
