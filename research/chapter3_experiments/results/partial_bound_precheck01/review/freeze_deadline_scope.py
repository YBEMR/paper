"""Existing DAG earliest-completion necessity only, never a schedule builder."""
from fractions import Fraction as F
from pathlib import Path
import time
import prepare_probes as audit

HERE=Path(__file__).resolve().parent

def check(instance,partial):
    shared_units=dict(partial.get('shared_units',{}))
    byscene=partial.get('by_scene',{})
    for scene in instance['scenarios']:
        stages={s['id']:s for s in scene['stage_instances']}
        for key,value in byscene.get(scene['id'],{}).items():
            if 'unit' in value:
                identity=stages[key]['shared_stage_id']
                assert identity not in shared_units or shared_units[identity]==value['unit']
                shared_units[identity]=value['unit']
    violations=[]
    for scene in instance['scenarios']:
        stages={s['id']:s for s in scene['stage_instances']}
        requests={r['id']:r for r in scene['requests']}
        pred={key:[] for key in stages}
        for a,b in scene['dependencies']:pred[b].append(a)
        minimum={}
        for key,stage in stages.items():
            rule=byscene.get(scene['id'],{}).get(key,{})
            unit=shared_units.get(stage['shared_stage_id'],rule.get('unit'))
            modes=[m for m in instance['stage_modes'][stage['shared_stage_id']]
                if (unit is None or m['unit_id']==unit) and ('opp' not in rule or m['opp_id']==rule['opp'])]
            assert modes
            minimum[key]=min(F(m['duration_ms']) for m in modes)
        finished={};remaining=set(stages)
        while remaining:
            ready=sorted(key for key in remaining if all(p in finished for p in pred[key]))
            assert ready
            for key in ready:
                request=requests[stages[key]['request_id']]
                finished[key]=max([F(request['release_ms']),*(finished[p] for p in pred[key])])+minimum[key]
                remaining.remove(key)
        for request in scene['requests']:
            optimistic=max(finished[key] for key in request['stage_instance_ids'])
            deadline=F(request['deadline_ms'])
            if optimistic>deadline:
                violations.append({'scene':scene['id'],'request':request['id'],
                    'minimum_completion_lower_ms':str(optimistic),'deadline_ms':str(deadline),
                    'excess_ms':str(optimistic-deadline)})
    return violations

def partial_of(p):
    if p['kind']=='single_shared_unit':return {'shared_units':{p['shared_stage_id']:p['unit_id']}}
    return {'by_scene':{p['scenario_id']:{p['stage_instance_id']:{'unit':p['unit_id'],'opp':p['opp_id']}}}}

def main():
    started=time.perf_counter();frozen=audit.read(HERE/'frozen_probes.json')
    instances={c['case']:audit.read(audit.REPO/c['instance_path']) for c in frozen['cases']}
    rows=[]
    for p in frozen['probes']:
        violations=check(instances[p['case']],partial_of(p))
        rows.append({'probe_id':p['probe_id'],'case':p['case'],
            'already_excluded_by_ordinary_deadline_necessity':bool(violations),
            'violations':violations,'passing_does_not_establish_feasibility':True})
    audit.save('deadline_scope.json',{'protocol':'K170-predeclared-ordinary-deadline-necessity-v1',
        'rule':'Original per-request release/deadline and DAG earliest-completion lower bounds with minimum allowed durations; ignore resource and thermal constraints.',
        'frozen_probes_sha256':audit.sha(HERE/'frozen_probes.json'),'classifier_source_sha256':audit.sha(Path(__file__)),
        'rows':rows,'counts':{'already_deadline_excluded':sum(r['already_excluded_by_ordinary_deadline_necessity'] for r in rows),'all_probes':len(rows)},
        'separate_analysis_wall_s':time.perf_counter()-started,
        'schedule_or_start_times_constructed':False,'solver_or_thermal_calls':0,
        'not_new_energy_bound_specific_exclusion':True})
    print({'ordinary_deadline_excluded':sum(r['already_excluded_by_ordinary_deadline_necessity'] for r in rows),'all_probes':len(rows),'scientific_calls':0})

if __name__=='__main__':main()
