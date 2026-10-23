"""Independent read-only archive checks; no scientific imports or evaluations."""
from datetime import datetime
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import psutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
NEW = REPO / 'research/chapter4_scheduler/results/resume_execution01'
OLD = REPO / 'research/chapter4_scheduler/results/execution_preparation01/frozen'


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


checks = []
def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})


d = read(NEW / 'declaration.json'); old = read(OLD / 'declaration.json')
t = read(NEW / 'batch_terminal.json'); prior = read(OLD / 'batch_terminal.json')
batch = read(NEW / 'batch.claim.json'); old_batch = read(OLD / 'batch.claim.json')
check('exact seven original unstarted slots', d['slots'] == old['slots'][1:] and len(d['slots']) == 7)
check('no replacement R1 C', not (NEW / 'calls/base__R1__C').exists())
check('one inherited and seven new reserved calls', prior['research_calls_reserved'] == 1
      and t['method_calls_reserved'] == 7 and t['combined_method_calls'] == 8)
check('exact claims and seven unique posts', len(list((NEW / 'calls').glob('*/slot.claim.json'))) == 7
      and len(list((NEW / 'calls').glob('*/postcheck.claim.json'))) == 7
      and t['post_calls_reserved'] == 7)
check('old absolute deadline retained', d['calendar_deadline_utc'] == batch['deadline_utc']
      == t['calendar_deadline_utc'] == old_batch['deadline_utc'])
check('completion before original cutoff', datetime.fromisoformat(t['returned_utc'])
      < datetime.fromisoformat(old_batch['deadline_utc']))
check('budget reservation no refunds', t['reserved_method_s'] == 2100
      and t['reserved_post_s'] == 420 and t['no_retry'] is True)
check('batch completed normally', t['passed'] is True and t['state'] == 'COMPLETED' and not t['errors'])
check('279 frozen sources unchanged', len(d['source_sha256']) == 279
      and all(sha(REPO / n) == h for n, h in d['source_sha256'].items()))
for field in ['frozen_dependency_sha256', 'protected_archive_sha256']:
    check(field + ' unchanged', all(sha(REPO / n) == h for n, h in d[field].items()))

rows = []; results = {}; live_observations = []; inputs = {}
for slot in d['slots']:
    sid = slot['slot_id']; folder = NEW / 'calls' / sid
    r = read(folder / 'result.json'); results[sid] = r
    a = read(folder / 'audit.json'); w = read(folder / 'worker_identity.json')
    post = read(folder / 'post_return.json'); fresh = read(folder / 'postcheck.json')
    config = read(folder / 'input_config.json'); instance = read(folder / 'input_instance.json')
    mp = read(folder / 'supervisor_method.json'); pp = read(folder / 'supervisor_post.json')
    candidate = r['safe_candidate']; common = next(c['common'] for c in d['cases']
                                               if c['common']['case_id'] == slot['case_id'])
    inputs[sid] = {'result_sha256': sha(folder/'result.json'), 'audit_sha256': sha(folder/'audit.json'),
                   'post_sha256': sha(folder/'postcheck.json')}
    check(sid + ' root and scientific identity', w['root_limit_s'] == 300
          and w['root_deadline_s'] == w['root_start_s'] + 300
          and w['source_sha256'] == d['source_sha256'] and w['fresh_input_calls'] == 1
          and all(w[k] is True for k in ['input_verified', 'source_verified', 'environment_verified'])
          and w['not_scientific'] is False and w['backend_budget_unchanged'] is True)
    check(sid + ' original input and raw preserved', canonical(instance) == common['input_sha256']
          and canonical(config) == common['config_sha256']
          and sha(folder/'wrapper_raw_result.json') == sha(folder/'result.json'))
    check(sid + ' normal admitted SAFE with unique bound post', r['state'] == 'SAFE'
          and a['eligible_for_post'] is True and a['technical_failure'] is False and not a['errors']
          and post['passed'] is True and post['evaluation_calls'] == 1 and post['new_U'] is False
          and post['candidate_sha256'] == canonical(candidate)
          and F(post['original_U_J']) == F(r['safe_upper_bound_J'])
          and post['return_wall_s'] < 60 and post['result_after_sha256'] == sha(folder/'result.json'))
    old_energy = list(map(F, a['admitted_interval'])); new_energy = list(map(F, post['post_interval']))
    check(sid + ' reproduced energy intervals overlap', max(old_energy[0], new_energy[0])
          <= min(old_energy[1], new_energy[1]) and old_energy[1] == F(r['safe_upper_bound_J']))
    check(sid + ' independent full continuous receipt', fresh['state'] == 'SAFE'
          and fresh['evidence_identity']['candidate_sha256'] == canonical(candidate)
          and fresh['evidence_identity']['input_sha256'] == canonical(instance)
          and set(fresh['scenes']) == {s['id'] for s in instance['scenarios']}
          and all(s['state'] == 'SAFE' and s['complete'] is True
                  and s['energy_accuracy_met'] is True
                  and F(s['covered_until_s']) == F(instance['window_ms'])/1000
                  and set(s['peaks_degC']) == set(instance['platform']['node_order'])
                  for s in fresh['scenes'].values()))
    for phase, proc in [('method', mp), ('post', pp)]:
        context = read(folder / (phase + '_host_context.json'))['context']
        check(sid + ' ' + phase + ' host and closed process', context['token_is_appcontainer'] is False
              and proc['returncode'] == 0 and proc['process_closed'] is True
              and proc['watchdog_stop'] is None and proc['launched'] is True)
        pid = proc['owned_root_pid']
        live_observations.append({'slot': sid, 'phase': phase, 'pid': pid,
            'pid_currently_exists': psutil.pid_exists(pid),
            'note': 'Receipt proves owned process exit; PID existence alone does not rule out reuse.'})
    rows.append({'slot_id': sid, 'U_J': str(F(r['safe_upper_bound_J'])),
        'U_float_J': float(F(r['safe_upper_bound_J'])), 'method_s': r['timing']['method_elapsed_s'],
        'worker_root_s': w['method_root_elapsed_s'], 'method_process_s': mp['process_wall_seconds'],
        'post_s': post['return_wall_s'], 'post_process_s': pp['process_wall_seconds'],
        'classification': a['classification'], 'first_strict_graph_at_s': r.get('first_graph_strict_improvement_at_s'),
        'graph_strict_improvements': r.get('graph_strict_improvements')})

initialization = []; strict = []
for case in ['base__R1', 'base__R3']:
    h = results[case+'__HEFT']; init_hashes = []
    for arm in ['SINGLE', 'PAIR']:
        r = results[case+'__'+arm]; first = r['initial_safe_snapshot']; init_hashes.append(r['root_context']['root_token'])
        same = first['candidate'] == h['safe_candidate']
        check(case + ' ' + arm + ' independently matching complete HEFT initialization', same
              and first['energy']['all_scenes_complete'] is True
              and F(first['energy']['upper']) == F(h['safe_upper_bound_J'])
              and r['candidate_or_cache_shared_between_calls'] is False)
        initialization.append({'case': case, 'arm': arm, 'candidate_exactly_equal_to_same_batch_heft': same,
                               'source': first['source'], 'candidate_sha256': canonical(first['candidate'])})
        current = list(map(F, [first['energy']['lower'], first['energy']['upper']]))
        improvements = [e for e in r['evaluations'] if e['phase']=='refinement' and e['incumbent_replaced']]
        for e in improvements:
            new = [F(e['energy']['lower']), F(e['energy']['upper'])]
            okay = new[1] < current[0] and e['returned_at_s'] < 300 and e['receipt']['state']=='SAFE'
            check(case + ' ' + arm + ' strict improvement at ' + str(e['returned_at_s']), okay)
            strict.append({'case':case,'arm':arm,'at_s':e['returned_at_s'],
                'old_lower_J':str(current[0]),'new_upper_J':str(new[1]),'strict':okay})
            current = new
        check(case + ' ' + arm + ' strict count and final U preserved', len(improvements)
              == r['graph_strict_improvements'] and current[1] == F(r['safe_upper_bound_J']))
    check(case + ' independent graph roots', len(set(init_hashes)) == 2)

c = results['base__R3__C']; closed = read(NEW/'calls/base__R3__C/method/matlab/closed.json')
check('R3 C normal completion not fault or timeout', c['reason']=='SCENE_SEARCH_SEQUENCE_COMPLETE'
      and c['budget_exhausted'] is False and c['search_failure_latched'] is False)
check('R3 C native closed with captured identities exited', closed['cleanup_status']=='graceful_closed'
      and closed['returncode']==0 and closed['observed_tree_verified_terminated'] is True
      and all(x['state']=='EXITED' for x in closed['process_tree_verification']['identities']))
totals = {k:sum(r[k] for r in rows) for k in ['method_s','worker_root_s','method_process_s','post_s','post_process_s']}
totals.update(resume_wall_s=t['resume_wall_s'], original_batch_elapsed_to_completion_s=(
    datetime.fromisoformat(t['returned_utc'])-datetime.fromisoformat(old_batch['started_utc'])).total_seconds())
facts = {'protocol':'K184-independent-readonly-archive-review-v1', 'passed':all(c['passed'] for c in checks),
    'checks':checks,'checks_count':len(checks),'failed':[c for c in checks if not c['passed']],
    'inputs':inputs,'rows':rows,'initialization':initialization,'strict_graph_improvements':strict,
    'actual_totals':totals,'process_observations':live_observations,'new_research_calls':0,
    'new_thermal_integrations':0,'new_optimization_solves':0,'code_sha256':sha(__file__),
    'declaration_sha256':sha(NEW/'declaration.json'),'terminal_sha256':sha(NEW/'batch_terminal.json')}
with (HERE/'facts.json').open('x',encoding='utf-8') as stream:
    json.dump(facts,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({'passed':facts['passed'],'checks_count':len(checks),'failed':facts['failed'],
                  'totals':totals,'strict_graph_improvements':strict},ensure_ascii=False))
