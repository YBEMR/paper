"""Exact event/state arithmetic from archived options; no model or solver import."""
import ast
from collections import Counter
import csv
from datetime import datetime, timezone, timedelta
from fractions import Fraction as F
import hashlib
from itertools import product
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCHIVE = REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02'
COMMIT = '7631a16d420fbd8711af1e6cb2f35bc03cf9700d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    with (HERE/name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')


def main():
    started=datetime.now(timezone.utc); t=time.monotonic()
    files=[ARCHIVE/p for p in ['plan.json','input_instance.json','input_config.json',
            'execution/on/result.json','execution/on/options.json',
            'execution/on/variable_names.json','execution/on/exported_model.npz']]
    hashes={str(p.relative_to(REPO)):sha(p) for p in files}
    # The local primary checkout has an older HEAD; verify fixed commit blob
    # identities via the isolated publication repository, without fetching.
    gitrepo=Path('/workspace/paper_publish_autol_lp_20261111')
    blob_checks={}
    for p in files:
        rel=str(p.relative_to(REPO))
        expected=subprocess.check_output(['git','rev-parse',COMMIT+':'+rel],cwd=gitrepo,text=True).strip()
        b=p.read_bytes(); actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        assert actual==expected,rel
        blob_checks[rel]=expected
    plan=read(ARCHIVE/'plan.json'); instance=read(ARCHIVE/'input_instance.json')
    options=read(ARCHIVE/'execution/on/options.json')
    names=read(ARCHIVE/'execution/on/variable_names.json')
    result=read(ARCHIVE/'execution/on/result.json')
    for p,h in plan['frozen_input_sha256'].items(): assert sha(ARCHIVE/p)==h
    for p,h in plan['frozen_source_sha256'].items(): assert sha(ARCHIVE/'frozen'/p)==h
    assert result['variant']=='on' and result['failure'] is None
    assert instance['execution_rules']['idle_policy']=='auto_low_immediate_v1'
    assert {s['id']:len(s['stage_instances']) for s in instance['scenarios']}=={'AB_offset_0ms':6,'AC_offset_0ms':6}
    assert len(options)==1125 and len(names)==19857
    domains=list(instance['platform']['domains']); assert domains==['CPU','GPU','NPU']
    nodes=instance['platform']['node_order']; assert len(nodes)==4
    window=F(instance['window_ms']); assert window==400
    by_interval={}
    for i,name in enumerate(names):
        if name.startswith('w:'):
            _,sid,interval,state=name.split(':',3)
            by_interval.setdefault((sid,int(interval)),[]).append((ast.literal_eval(state),i))
    records=[]; scenes={}; checks=[]
    checks.append('Seven archived evidence files match exact 7631a16d Git blobs; frozen input/source SHA256 matches')
    for scene in instance['scenarios']:
        sid=scene['id']; local=[o for o in options if o['scenario_id']==sid]
        events=sorted({F(0),window}|{F(o['start_ms']) for o in local}|{F(o['end_ms']) for o in local})
        scene_rows=[]; event_pairs=list(zip(events,events[1:]))
        for l,(left,right) in enumerate(event_pairs):
            # Events include every start/end, so an option is active throughout
            # [left,right) exactly when start <= left < end.
            active=[o for o in local if F(o['start_ms'])<=left<F(o['end_ms'])]
            possible=[sorted({'L'}|{o['opp_id'] for o in active if o['domain_id']==d}) for d in domains]
            states=list(product(*possible)); archived=by_interval[sid,l]
            assert states==[v[0] for v in archived],(sid,l)
            assert len(states)==len(set(states))
            assert all(F(o['end_ms'])>=right for o in active)
            n=len(states)
            row=dict(scenario_id=sid,interval_index=l,left_ms=str(left),right_ms=str(right),
                duration_ms=str(right-left),duration_ms_decimal=float(right-left),
                active_option_count=len(active),active_stage_count=len({o['stage_instance_id'] for o in active}),
                possible_opps=dict(zip(domains,possible)),joint_state_blocks=n,states=states,
                archived_w_variable_indices=[v[1] for v in archived],
                thermal_propagation_equalities=4*n,thermal_propagation_rows=8*n,
                complete_energy_equalities=n,complete_energy_rows=2*n,electrothermal_rows=10*n)
            records.append(row);scene_rows.append(row)
        assert len(events)-1==result['event_intervals'][sid]
        assert sum(r['joint_state_blocks'] for r in scene_rows)==result['joint_state_blocks'][sid]
        histogram=Counter(r['joint_state_blocks'] for r in scene_rows)
        durations=Counter(F(r['duration_ms']) for r in scene_rows)
        scenes[sid]=dict(events=len(events),intervals=len(scene_rows),
            options=len(local),joint_state_blocks=sum(r['joint_state_blocks'] for r in scene_rows),
            state_block_histogram=dict(sorted(histogram.items())),
            thermal_propagation_rows=sum(r['thermal_propagation_rows'] for r in scene_rows),
            complete_energy_rows=sum(r['complete_energy_rows'] for r in scene_rows),
            interval_min_ms=str(min(durations)),interval_max_ms=str(max(durations)),
            intervals_lt_1ms=sum(v for k,v in durations.items() if k<1),
            intervals_lt_0_1ms=sum(v for k,v in durations.items() if k<F(1,10)),
            maximum_blocks=max(histogram),
            maximum_block_interval_indices=[r['interval_index'] for r in scene_rows if r['joint_state_blocks']==max(histogram)],
            shortest_interval_indices=[r['interval_index'] for r in scene_rows if F(r['duration_ms'])==min(durations)])
        assert sum(F(r['duration_ms']) for r in scene_rows)==window
        checks.append(sid+': exact half-open intervals cover400ms; every interval state tuple/order/index matches archived w variables')
    assert len(records)==424 and sum(r['joint_state_blocks'] for r in records)==9798
    actual=Counter()
    for r in records:
        for key in ['thermal_propagation_rows','complete_energy_rows','electrothermal_rows']:actual[key]+=r[key]
    assert actual['thermal_propagation_rows']==result['row_family_counts']['thermal_propagation']==78384
    assert actual['complete_energy_rows']==result['row_family_counts']['complete_energy']==19596
    assert actual['electrothermal_rows']==97980
    assert len(by_interval)==424 and sum(len(v) for v in by_interval.values())==9798
    assert result['row_family_counts']['joint_unique']==2*len(records)==848
    assert result['row_family_counts']['joint_marginal']==2*len(records)*sum(len(d['opps']) for d in instance['platform']['domains'].values())==7632
    checks.append('424 intervals/9798 states; thermal8/state=78384, energy2/state=19596, total10/state=97980; joint unique/marginal counts match')
    save('interval_states.json',records)
    fields=[k for k in records[0] if k not in ['states','archived_w_variable_indices']]
    with (HERE/'interval_counts.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in records:
            writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row[k],dict) else row[k] for k in fields})
    with (HERE/'duration_histogram.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['scenario_id','duration_ms','duration_ms_decimal','interval_count']);writer.writeheader()
        for sid in scenes:
            for duration,count in sorted(Counter(F(r['duration_ms']) for r in records if r['scenario_id']==sid).items()):
                writer.writerow(dict(scenario_id=sid,duration_ms=str(duration),duration_ms_decimal=float(duration),interval_count=count))
    ended=datetime.now(timezone.utc)
    summary=dict(started_utc=started.isoformat(),ended_utc=ended.isoformat(),wall_s=time.monotonic()-t,
        command=[sys.executable,*sys.argv],cwd=str(REPO),based_on_commit=COMMIT,
        environment=dict(python=sys.version,platform=platform.platform()),
        archive_variant='auto-L full12-execution R1 ON',propagate_support=True,
        baseline_flags=plan['baseline_flags'],input_execution_rules=instance['execution_rules'],
        frozen_source_sha256=plan['frozen_source_sha256']['research/chapter3_experiments/milp.py'],
        source_file_sha256=hashes,git_blob_checks=blob_checks,scenes=scenes,
        totals=dict(intervals=len(records),states=9798,temperature_nodes=4,thermal_rows=78384,energy_rows=19596,total_electrothermal_rows=97980,all_rows=124338,share_electrothermal_rows=97980/124338),
        checks=checks,new_solver_calls=0,new_model_builds=0,new_thermal_evaluations=0,
        source_formula='milp.py states=product(*possible) at1045; each state temperature4 plusenergy1 conditional_eq, eachupper/lower2 at1096-1105',
        limitations='Pure archive/event arithmetic. A Cartesian tuple is only generated possibility, not a proof of reachability or feasibility. Does not verify thermal safety or convergence.')
    save('summary.json',summary)
    source=(ARCHIVE/'frozen/research/chapter3_experiments/milp.py').read_text()
    snippets={}
    for a,b in [(1033,1056),(1091,1111)]:snippets[f'{a}-{b}']='\n'.join(source.splitlines()[a-1:b])
    save('source_formula_excerpt.json',dict(source_sha256=summary['frozen_source_sha256'],snippets=snippets))
    print(json.dumps({k:summary[k] for k in ['started_utc','ended_utc','wall_s','scenes','totals','checks']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
