"""Read-only arithmetic over completed pilot receipts; no scientific imports."""
import json
import sys
from collections import Counter
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
EX = ROOT / 'execution'
def read(p): return json.loads(p.read_text(encoding='utf-8'))

def positive_targets(instance, candidate):
    count = 0
    for scene in instance['scenarios']:
        ids = {s['id']: s['shared_stage_id'] for s in scene['stage_instances']}
        for row in candidate['scenes'][scene['id']]:
            modes = [m for m in instance['stage_modes'][ids[row['stage_id']]] if m['unit_id'] == row['unit']]
            old = next(m for m in modes if m['opp_id'] == row['opp'])
            activity = lambda m: F(m['activity_power_W']) * F(m['duration_ms'])
            count += sum(F(scene['weight']) * (activity(old) - activity(m)) > 0 for m in modes)
    return count

summary, inputs = read(EX/'summary.json'), read(ROOT/'inputs/inputs_manifest.json')
details = []
for row in summary['rows']:
    folder = EX/'calls'/row['id']
    if not (folder/'method/result.json').exists():
        details.append({'id': row['id'], 'missing_raw': True})
        continue
    raw = read(folder/'method/result.json')
    inst = read(folder/'method/input_instance.json')
    returned = read(folder/'method_return.json')
    completed = returned.get('metrics', {}).get('initialization_completed_at_s')
    records = raw['timing']['phase_records']
    init = raw.get('initialization') or {}
    journal = returned.get('evaluation_attempts_journal', [])
    eval_init = sum(a.get('returned_at_s', a['started_at_s'])-a['started_at_s'] for a in journal
                    if completed is None or a['started_at_s'] < completed)
    eval_search = sum(a.get('returned_at_s', a['started_at_s'])-a['started_at_s'] for a in journal
                      if completed is not None and a['started_at_s'] >= completed)
    detail = {'id':row['id'], 'initialization_status':init.get('status'),
        'initialization_attempts':len(init.get('construction_attempts', [])),
        'initialization_local_attempts':len(init.get('local_attempts', [])),
        'initialization_local_accepted':init.get('local_accepted'),
        'initialization_candidate_sequence':[a['candidate_sha256'] for a in journal if completed is None or a['started_at_s'] < completed],
        'initializer_eval_s':eval_init, 'search_eval_s':eval_search,
        'positive_activity_targets_initial':positive_targets(inst, raw['initial_safe_snapshot']['candidate']) if raw.get('initial_safe_snapshot') else None,
        'positive_activity_targets_final':positive_targets(inst,raw['safe_candidate']) if raw.get('safe_candidate') else None,
        'graph_states':dict(Counter(x.get('state') for x in raw.get('reconstruction_attempts', []))),
        'graph_reasons':dict(Counter(x.get('reason') for x in raw.get('reconstruction_attempts', []) if x.get('reason'))),
        'accepted_proposals':[{'additional_reversed_edges':x.get('additional_reversed_edges'), 'proposed_at_s':x.get('proposed_at_s')} for x in raw.get('graph_proposals', []) if x.get('strict_accepted')],
        'exclusive_phase_totals_s':raw['timing']['phases_exclusive_s']}
    details.append(detail)

totals = {key: sum(r.get(key) or 0 for r in summary['rows']) for key in
    ['evaluation_attempts','returned_receipts','validated_SAFE_receipts','cache_hits','returned_thermal_violation_receipts','returned_unresolved_receipts','method_elapsed_s','process_wall_s','initialization_s','search_s','electrothermal_evaluation_s','graph_reconstruction_attempts','graph_strict_improvements']}
value = {'totals':totals,'comparisons':summary['comparisons'],'details':details,
         'input_construction_seconds':inputs['input_construction_seconds'],
         'batch_wall_s':read(EX/'batch_return.json')['wall_s']}
(ROOT/'analysis.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'totals':totals,'comparisons':summary['comparisons'],
 'rows':[{k:r.get(k) for k in ['case_id','arm','energy_upper_J_decimal','method_elapsed_s','process_wall_s','initialization_s','search_s','full_electrothermal_completed_evaluations','initialization_full_SAFE_evaluations','search_full_SAFE_evaluations','electrothermal_evaluation_s','graph_construction_s','graph_reconstruction_attempts','graph_proposals','graph_strict_improvements','peak_temperature_upper_C','reason']} for r in summary['rows']]},ensure_ascii=False,indent=2))
