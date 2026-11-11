"""Independent exact complete structural-schedule oracle for the static filter."""
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction as F
from itertools import product,combinations
import hashlib
import json
from pathlib import Path
import sys
import time
import run_reachability as candidate

HERE=Path(__file__).resolve().parent
def option(oid,scene,stage,unit,opp,start,end):
    return dict(option_id=oid,scenario_id=scene,stage_instance_id=stage,unit_id=unit,
        domain_id={'CPU1':'CPU','CPU2':'CPU','GPU0':'GPU','NPU0':'NPU'}[unit],
        opp_id=opp,start_ms=str(start),end_ms=str(end))
def scene(sid,stages,edges=()):
    return dict(id=sid,stage_instances=[dict(id=s,shared_stage_id=shared) for s,shared in stages],dependencies=[list(e) for e in edges])

def fixtures():
    o=option;s=scene
    return [
      ('same_stage_modes_noninteger',[s('s',[('a','A')])],[o('ac','s','a','CPU1','H',0,'3/2'),o('ag','s','a','GPU0','H',0,'3/2'),o('am','s','a','CPU1','M',5,'13/2')]),
      ('dependency_equality',[s('s',[('p','P'),('q','Q')],[('p','q')])],[o('p1','s','p','CPU1','H',0,'3/2'),o('p2','s','p','CPU1','H',0,3),o('q1','s','q','GPU0','H','3/2','5/2'),o('q2','s','q','GPU0','H',5,6)]),
      ('transitive_dependency',[s('s',[('a','A'),('b','B'),('c','C')],[('a','b'),('b','c')])],[o('a1','s','a','CPU1','H',0,1),o('a2','s','a','CPU1','H',0,4),o('b','s','b','NPU0','L',1,2),o('c1','s','c','GPU0','H',2,3),o('c2','s','c','GPU0','H',5,6)]),
      ('three_independent_nonL_reachable',[s('s',[('a','A'),('b','B'),('c','C')])],[o('a','s','a','CPU1','H',0,2),o('b','s','b','GPU0','H',0,2),o('c','s','c','NPU0','H',0,2)]),
      ('cpu_shared_domain',[s('s',[('a','A'),('b','B')])],[o('a','s','a','CPU1','H',0,2),o('bM','s','b','CPU2','M',0,2),o('bH','s','b','CPU2','H',0,2)]),
      ('L_active_and_idle',[s('s',[('a','A'),('b','B')])],[o('a','s','a','CPU1','L',0,2),o('b','s','b','GPU0','L',0,2)]),
      ('cross_scene_shared_mapping',[s('s',[('a','A')]),s('t',[('aa','A')])],[o('s1','s','a','CPU1','M',0,2),o('s2','s','a','CPU2','H',0,2),o('t1','t','aa','CPU1','H',5,7),o('t2','t','aa','GPU0','H',5,7)]),
      ('support_is_not_sufficiency',[s('s',[('a','A'),('b','B')])],[o('a','s','a','CPU1','H',0,2),o('b','s','b','CPU1','H',0,2)]),
      ('same_scene_shared_id',[s('s',[('a','A'),('aa','A')])],[o('aC','s','a','CPU1','H',0,2),o('aG','s','a','GPU0','H',0,2),o('aaC','s','aa','CPU1','H',0,2),o('aaG','s','aa','GPU0','H',0,2)])]

def legal(scenes,chosen):
    """No candidate helper calls: exact original structural constraints only."""
    lookup={(x['scenario_id'],x['stage_instance_id']):x for x in chosen}
    shared={}
    for sc in scenes:
        rows=[]
        for st in sc['stage_instances']:
            x=lookup[sc['id'],st['id']];rows.append(x)
            if not (F(0)<=F(x['start_ms'])<F(x['end_ms'])<=F(10)):return False
            old=shared.setdefault(st['shared_stage_id'],x['unit_id'])
            if old!=x['unit_id']:return False
        for a,b in sc['dependencies']:
            if F(lookup[sc['id'],a]['end_ms'])>F(lookup[sc['id'],b]['start_ms']):return False
        for a,b in combinations(rows,2):
            overlap=max(F(a['start_ms']),F(b['start_ms']))<min(F(a['end_ms']),F(b['end_ms']))
            if overlap and a['unit_id']==b['unit_id']:return False
            if overlap and a['domain_id']==b['domain_id'] and a['opp_id']!=b['opp_id']:return False
    return True

def main():
    begin=time.monotonic();started=datetime.now(timezone.utc).isoformat();records=[];case_records=[]
    domains=['CPU','GPU','NPU'];total=0;checked_projections=0
    for name,scenes,options in fixtures():
        snapshot=deepcopy((scenes,options));groups=[(s['id'],st['id']) for s in scenes for st in s['stage_instances']]
        choices=[[x for x in options if (x['scenario_id'],x['stage_instance_id'])==g] for g in groups]
        count=1
        for rows in choices:count*=len(rows)
        assert count<=4096
        complete=list(product(*choices));total+=len(complete)
        all_legal=[xs for xs in complete if legal(scenes,xs)]
        before={tuple(x['option_id'] for x in xs) for xs in all_legal};after=set(before)
        interval_records=[]
        for sc in scenes:
            local=[x for x in options if x['scenario_id']==sc['id']]
            events=sorted({F(0),F(10)}|{F(x[k]) for x in local for k in ['start_ms','end_ms']})
            for l,(left,right) in enumerate(zip(events,events[1:])):
                support=candidate.support_groups(sc,options,left,right,domains)
                states=list(product(*(sorted({'L'}|set(support[d])) for d in domains)))
                classified={state:candidate.classify(state,domains,support,candidate.paths(sc)) for state in states}
                deleted={s for s,p in classified.items() if p['status']=='PROVED_UNREACHABLE'}
                projections=[]
                for xs in all_legal:
                    active=[x for x in xs if x['scenario_id']==sc['id'] and F(x['start_ms'])<=left<F(x['end_ms'])]
                    state=tuple(next((x['opp_id'] for x in active if x['domain_id']==d),'L') for d in domains)
                    assert state in classified
                    identity=tuple(x['option_id'] for x in xs)
                    projections.append(dict(schedule=identity,state=state))
                    checked_projections+=1
                    if state in deleted:after.discard(identity)
                interval_records.append(dict(scene=sc['id'],interval=l,left_ms=str(left),right_ms=str(right),
                    before_states=states,proved_unreachable=sorted(deleted),complete_legal_state_projections=projections))
                if name=='three_independent_nonL_reachable' and left==0:assert ('H','H','H') not in deleted
                if name=='L_active_and_idle' and left==0:assert ('L','L','L') not in deleted
                if name=='support_is_not_sufficiency' and left==0:assert not deleted
        assert before==after and (scenes,options)==snapshot
        if name not in ['support_is_not_sufficiency','same_scene_shared_id']:assert before
        records.append(dict(name=name,cartesian=len(complete),all_assignments=[dict(option_ids=[x['option_id'] for x in xs],legal=legal(scenes,xs)) for xs in complete],
            legal_schedules_before=sorted(before),legal_schedules_after=sorted(after),intervals=interval_records))
        case_records.append(dict(name=name,scenes=scenes,options=options))
    result=dict(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),wall_s=time.monotonic()-begin,
      cases=len(records),complete_assignments=total,legal_schedules_before=sum(len(x['legal_schedules_before']) for x in records),
      legal_schedules_after=sum(len(x['legal_schedules_after']) for x in records),checked_state_projections=checked_projections,
      all_legal_sets_equal=True,solver_calls=0,thermal_calls=0,model_builds=0,
      independence='Full structural legality and state projection do not call classifier helpers; no thermal certificates',
      script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),python=sys.version)
    for name,obj in [('small_domain_inputs.json',case_records),('small_domain_complete_sets.json',records),('small_domain_results.json',result)]:
        with (HERE/name).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
