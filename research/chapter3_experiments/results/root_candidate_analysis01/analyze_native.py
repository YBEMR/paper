"""Extract native dimensions, event timings and stored candidate identities."""
from collections import defaultdict
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
RUN = OUT.parent/'linked_five_open_pair01'
REPO = OUT.parents[3]
bindings = {}


def read(path):
    raw = path.read_bytes()
    bindings[path.relative_to(REPO).as_posix()] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def keyed(rows):
    return {v['stage_id']:(v['unit'],v['opp'],F(v['start_ms'])) for v in rows}


def main():
    assert not (OUT/'native_metrics.json').exists()
    instance = read(RUN/'input_instance.json')
    native = []
    for job in ('old_linked4','new_linked5'):
        result = read(RUN/job/'result.json')
        for number in range(1,5):
            phase,index = (1 if number<=2 else 2),(number-1)%2
            sid = instance['scenarios'][index]['id']
            response = read(RUN/job/'matlab'/f'request_{number:06d}.response.json')
            init = next(c for c in response['callbacks'] if c['state']=='init')
            root = next(c for c in response['callbacks'] if c['values'].get('phase')=='rootlp')
            timeline = [{k:c.get(k) for k in ('event_number','state','request_wall_seconds')}
                        | {'native':c.get('values'),'nonempty_vector':bool(c.get('x'))}
                        for c in response['callbacks']]
            row = {'job':job,'phase':phase,'scene':sid,'request':number,
                'intlinprog_call_s':response['phase_seconds']['intlinprog_call'],
                'rootlp_native_cumulative_s':root['values']['time'],
                'init_to_rootlp_request_wall_s':root['request_wall_seconds']-init['request_wall_seconds'],
                'final_numfeaspoints':response['output']['numfeaspoints'],
                'final_numnodes':response['output']['numnodes'],
                'solver_reported_only':True,'timeline':timeline}
            if phase==2:
                path = RUN/job/'pass_02'/f'scene_{index}'/'augmented_requests'/f'request_{index+1:06d}'
                dimensions = read(path/'matrix_identities.json')
                row['constructed_variables'] = dimensions['original']['c']['length']
                row['native_variables'] = dimensions['augmented']['c']['length']
                row['native_inequalities'] = dimensions['augmented']['A']['shape'][0]
                row['native_equalities'] = dimensions['augmented']['Aeq']['shape'][0]
                row['native_integer_variables'] = dimensions['augmented']['intcon']['length']
                row['added_complement_columns'] = row['native_variables']-row['constructed_variables']
                warm = result['phases'][1]['condition']['warm_options_by_scene'][sid]
                warm = {s:(v['unit'],v['opp'],F(v['start_ms'])) for s,v in warm.items()}
                evaluations = result['phases'][1]['scenes'][sid]['solver_result']['diagnostic']['evaluations']
                row['stored_evaluated_candidates'] = [
                    {'source':v['source'], 'same_as_own_warm':keyed(v['candidate']['scenes'][sid])==warm,
                     'accepted_safe':v['accepted_safe']} for v in evaluations]
            native.append(row)
    path = RUN/'analysis01/exclusive_costs.csv'
    bindings[path.relative_to(REPO).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    totals = defaultdict(lambda:defaultdict(F))
    with path.open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            totals[r['job']][r['budget_phase']] += F(r['exclusive_seconds_exact_fraction'])
    assert all(hashlib.sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in bindings.items())
    facts = {'scope':'saved logs only; rootlp is a cumulative callback timestamp, not exclusive timing',
        'research_calls':0,'native_calls':0,'model_constructions':0,'lp_calls':0,'heat_evaluations':0,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_sha256':bindings,'raw_unchanged':True,'requests':native,
        'exclusive_cost_totals_s':{job:{k:float(v) for k,v in values.items()} for job,values in totals.items()}}
    (OUT/'native_metrics.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields = ['job','scene','native_variables','native_inequalities','native_equalities',
              'native_integer_variables','rootlp_native_cumulative_s','final_numfeaspoints','final_numnodes']
    with (OUT/'native_second_pass.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in native:
            if row['phase']==2:
                writer.writerow({k:row[k] for k in fields})
    print(json.dumps({'requests':len(native),'all_final_numnodes_zero':all(r['final_numnodes']==0 for r in native),
                      'research_calls':0,'raw_unchanged':True}))


if __name__=='__main__':
    main()
