"""K171: replay stored local option domains with stdlib/Fraction only.

This does not import or call an input builder, MILP constructor, solver,
schedule generator or thermal evaluator. It enumerates only saved finite
mode/start labels and intersects the exact archived declaration/filter rules.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / 'research/chapter3_experiments'
HERE = Path(__file__).resolve().parent
SOURCES = ['inputs.py', 'start_domain.py', 'milp.py', 'scene_adapter.py',
           'scene_method.py', 'neighborhood.py', 'linked_neighborhood.py',
           'anchor_preelimination.py', 'neighborhood_method.py', 'linked_method.py',
           'build_observer.py']
READS = {}
GUARD = {'scientific_import': 0, 'production_code_entry': 0, 'process_launch': 0}
CHECKS = []


class GuardViolation(BaseException):
    pass


def audit(event, args):
    if event == 'import':
        name = args[0].split('.')[0]
        if name in {'numpy', 'scipy', 'matlab', 'milp', 'inputs', 'thermal',
                    'initial_schedule', 'initial_point', 'neighborhood',
                    'linked_neighborhood', 'anchor_preelimination', 'schedules',
                    'scene_adapter', 'neighborhood_method', 'linked_method'}:
            GUARD['scientific_import'] += 1
            raise GuardViolation('forbidden import: '+name)
    if event == 'subprocess.Popen' or event == 'os.system' or event.startswith('os.spawn'):
        GUARD['process_launch'] += 1
        raise GuardViolation('forbidden process: '+event)


def profile(frame, event, arg):
    if event == 'call':
        filename = str(Path(frame.f_code.co_filename)).replace('\\', '/')
        if '/research/chapter3_experiments/' in filename and '/results/' not in filename:
            GUARD['production_code_entry'] += 1
            raise GuardViolation('forbidden production call: '+filename)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path, *, parsed=True):
    raw = path.read_bytes()
    READS[str(path.relative_to(ROOT)).replace('\\', '/')] = sha(raw)
    return json.loads(raw) if parsed else raw.decode('utf-8-sig')


def canonical(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8'))


def check(name, actual, expected, **context):
    CHECKS.append({'name': name, 'passed': actual == expected,
                   'actual': actual, 'expected': expected, **context})


def original_options(instance, sid, fixed_shared=None):
    """Independent transcription of release/grid/window label expansion only."""
    if 'start_domain' in instance:
        raise ValueError('This archived P0 replay supports the declared full grid only')
    scene = next(s for s in instance['scenarios'] if s['id'] == sid)
    requests = {r['id']: r for r in scene['requests']}
    grid, window = F(instance['start_grid_ms']), F(instance['window_ms'])
    out = []
    for stage in scene['stage_instances']:
        request = requests[stage['request_id']]
        release = F(request['release_ms'])
        first = max(0, -((-release)//grid))
        for mode in instance['stage_modes'][stage['shared_stage_id']]:
            if fixed_shared is not None and stage['shared_stage_id'] in fixed_shared:
                if mode['unit_id'] != fixed_shared[stage['shared_stage_id']]:
                    continue
            last = min(window//grid, (window-F(mode['duration_ms']))//grid)
            for index in range(first, last+1):
                start, end = index*grid, index*grid+F(mode['duration_ms'])
                row = dict(mode)
                row.update(option_id=f"{stage['id']}@{mode['unit_id']}:{mode['opp_id']}:g{index}",
                    scenario_id=sid, request_id=request['id'], stage_instance_id=stage['id'],
                    start_grid_index=index, start_ms=str(start), end_ms=str(end),
                    request_release_ms=request['release_ms'],
                    request_deadline_ms=request['deadline_ms'])
                out.append(row)
    return out


def neighborhood_options(instance, condition, options, phase_index):
    counts = {sid: {stage: {'before': 0, 'after': 0} for stage in rows}
              for sid, rows in condition['seed_options_by_scene'].items()}
    out = []
    for row in options:
        sid, stage = row['scenario_id'], row['stage_instance_id']
        counts[sid][stage]['before'] += 1
        seed = condition['seed_options_by_scene'][sid][stage]
        closed = (condition['warm_options_by_scene'] if phase_index == 2
                  else condition['seed_options_by_scene'])[sid][stage]
        member = row['unit_id'] == seed['unit'] and (
            stage in condition['opened_by_scene'][sid] or (
                row['opp_id'] == closed['opp'] and F(row['start_ms']) == F(closed['start_ms'])))
        if member:
            out.append(row)
            counts[sid][stage]['after'] += 1
    return out, {'before': len(options), 'after': len(out),
                 'removed': len(options)-len(out), 'by_scene_stage': counts,
                 'complete': True, 'condition_sha256': condition['condition_sha256']}


def anchor_options(instance, condition, sid, options):
    scene = next(s for s in instance['scenarios'] if s['id'] == sid)
    edges = {tuple(edge) for edge in scene['dependencies']}
    counts = {s['id']: {'before': 0, 'after': 0} for s in scene['stage_instances']}
    anchors = []
    for stage in scene['stage_instances']:
        if stage['id'] in condition['opened_by_scene'][sid]:
            continue
        fixed = condition['warm_options_by_scene'][sid][stage['id']]
        mode = next(m for m in instance['stage_modes'][stage['shared_stage_id']]
                    if m['unit_id'] == fixed['unit'] and m['opp_id'] == fixed['opp'])
        start = F(fixed['start_ms'])
        anchors.append({'stage_id': stage['id'], 'unit_id': fixed['unit'],
            'opp_id': fixed['opp'], 'domain_id': mode['domain_id'],
            'start_ms': str(start), 'end_ms': str(start+F(mode['duration_ms']))})
    kept, removals = [], []
    for row in options:
        stage = row['stage_instance_id']
        counts[stage]['before'] += 1
        reasons = []
        if stage in condition['opened_by_scene'][sid]:
            start, end = F(row['start_ms']), F(row['end_ms'])
            for anchor in anchors:
                astart, aend = F(anchor['start_ms']), F(anchor['end_ms'])
                overlap = max(start, astart) < min(end, aend)
                rules = []
                if overlap and row['unit_id'] == anchor['unit_id']:
                    rules.append('same_unit_overlap')
                if overlap and row['domain_id'] == anchor['domain_id'] and row['opp_id'] != anchor['opp_id']:
                    rules.append('same_domain_different_opp_overlap')
                if (stage, anchor['stage_id']) in edges and end > astart:
                    rules.append('open_predecessor_finishes_after_closed_start')
                if (anchor['stage_id'], stage) in edges and start < aend:
                    rules.append('open_successor_starts_before_closed_end')
                if rules:
                    reasons.append({'rules': rules, 'anchor': dict(anchor)})
        if reasons:
            removals.append({k: row[k] for k in ('scenario_id','stage_instance_id','option_id',
                'unit_id','opp_id','domain_id','start_ms','end_ms')})
            removals[-1]['reasons'] = reasons
        else:
            kept.append(row)
            counts[stage]['after'] += 1
    return kept, {'before': len(options), 'after': len(kept), 'removed': len(removals),
        'input_options_sha256': canonical(options), 'output_options_sha256': canonical(kept),
        'by_scene_stage': {sid: counts}, 'anchors_by_scene': {sid: anchors},
        'removals': removals}


def phase_partial(instance, condition, phase_index):
    """All fixed units and closed OPPs; never impose starts or warm open OPPs."""
    result = {'by_scene': {}}
    for scene in instance['scenarios']:
        sid = scene['id']
        result['by_scene'][sid] = {}
        for stage in scene['stage_instances']:
            stage_id = stage['id']
            row = {'unit': condition['seed_options_by_scene'][sid][stage_id]['unit']}
            if stage_id not in condition['opened_by_scene'][sid]:
                closed = (condition['warm_options_by_scene'] if phase_index == 2
                          else condition['seed_options_by_scene'])[sid][stage_id]
                row['opp'] = closed['opp']
            result['by_scene'][sid][stage_id] = row
    return result


def copy_rows(instance, condition, phase_index, sid, original, after_shared, after_n1,
              after_deadline, actual, zero_ids):
    opened, closed = [], []
    scene = next(s for s in instance['scenarios'] if s['id'] == sid)
    for stage in scene['stage_instances']:
        stage_id = stage['id']
        source = 'warm_options_by_scene' if phase_index == 2 else 'seed_options_by_scene'
        fixed = condition[source][sid][stage_id]
        is_open = stage_id in condition['opened_by_scene'][sid]
        rows = [(column, row) for column, row in enumerate(actual) if row['stage_instance_id'] == stage_id]
        groups = {}
        for column, row in rows:
            key = row['unit_id'], row['opp_id']
            group = groups.setdefault(key, {'unit': key[0], 'opp': key[1],
                'duration_ms': row['duration_ms'], 'options_nonzero': 0,
                'starts_ms': [], 'option_columns': [], 'zero_bound_starts_ms': []})
            if row['option_id'] not in zero_ids:
                group['options_nonzero'] += 1
                group['starts_ms'].append(row['start_ms'])
                group['option_columns'].append(column)
            else:
                group['zero_bound_starts_ms'].append(row['start_ms'])
        modes = [{k:m[k] for k in ('unit_id','opp_id','domain_id','duration_ms','activity_power_W')}
                 for m in instance['stage_modes'][stage['shared_stage_id']]]
        count = lambda seq: sum(o['stage_instance_id'] == stage_id for o in seq)
        out = {'stage_id': stage_id, 'shared_stage_id': stage['shared_stage_id'],
            'request_id': stage['request_id'], 'opened': is_open,
            'unit': condition['seed_options_by_scene'][sid][stage_id]['unit'],
            'closed_opp': None if is_open else fixed['opp'],
            'closed_start_ms': None if is_open else str(F(fixed['start_ms'])),
            'closed_anchor_source': None if is_open else ('last_complete_first_pass_SAFE' if phase_index == 2 else 'fresh_seed'),
            'original_legal_modes': modes,
            'counts': {'original_release_window_options': count(original),
                'after_shared_device_prefilter': count(after_shared),
                'after_neighborhood': count(after_n1), 'after_deadline_delete': count(after_deadline),
                'actual_columns': len(rows), 'actual_nonzero_options': sum(g['options_nonzero'] for g in groups.values()),
                'retained_upper_bound_zero_columns': sum(len(g['zero_bound_starts_ms']) for g in groups.values())},
            'modes': list(groups.values())}
        (opened if is_open else closed).append(out)
    return opened, closed


def replay():
    read(Path(__file__), parsed=False)
    declarations = {}
    source_checks = []
    for campaign in ('p0_execution01', 'p0_resume01'):
        declaration = read(BASE/'results'/campaign/'declaration.json')
        declarations[campaign] = declaration
        for name in SOURCES:
            path = BASE/name
            digest = sha(read(path, parsed=False).encode('utf-8'))
            # Source bytes have CRLF, so use the exact recorded raw-byte digest.
            digest = READS[str(path.relative_to(ROOT)).replace('\\', '/')]
            key = str(path.relative_to(ROOT)).replace('\\', '/')
            expected = declaration['source_sha256'][key]
            source_checks.append({'campaign': campaign, 'path': key, 'sha256': digest,
                                  'matches_original_declaration': digest == expected})
            check('source_matches_original_frozen_declaration', digest, expected, campaign=campaign, source=key)
    builds = []
    for n in range(1, 6):
        campaign = 'p0_execution01' if n == 1 else 'p0_resume01'
        folder = BASE/'results'/campaign/'calls'/f'base__R{n}'/'anchor_linked4'
        instance, config, result = (read(folder/name) for name in ('input_instance.json','input_config.json','result.json'))
        check('instance_config_schema', instance['schema_version'], config['schema_version'], case=n)
        check('original_full_grid_no_subset', 'start_domain' in instance, False, case=n)
        for phase in result['phases']:
            pindex, condition = phase['phase_index'], phase['condition']
            phase_condition = phase_partial(instance, condition, pindex)
            check('condition_input_identity', condition['source_input_sha256'], canonical(instance), case=n, phase=pindex)
            check('condition_hash', condition['condition_sha256'], canonical({k:v for k,v in condition.items() if k!='condition_sha256'}), case=n, phase=pindex)
            for sindex, scene in enumerate(instance['scenarios']):
                sid, saved = scene['id'], phase['scenes'][scene['id']]
                build_key = f'base__R{n}/phase_{pindex}/{sid}'
                context = {'build_key': build_key}
                summary, preprocessing = saved['model_summary'], saved['preprocessing']
                formulation = summary['formulation']
                original = original_options(instance, sid)
                shared = original_options(instance, sid, condition['shared_deployment'])
                n1, stats = neighborhood_options(instance, condition, shared, pindex)
                check('neighborhood_complete_stats', stats, summary['neighborhood']['options'], **context)
                check('pre_deadline_count', len(n1), preprocessing['options_before_deadline_filter'], **context)
                deadline = [o for o in n1 if not formulation['prefilter_deadlines'] or F(o['end_ms'])<=F(o['request_deadline_ms'])]
                check('deadline_removed_count', len(n1)-len(deadline), preprocessing['deadline_removed_count'], **context)
                anchor_stats = None
                actual = deadline
                if formulation.get('preeliminate_closed_anchors', False):
                    actual, anchor_stats = anchor_options(instance, condition, sid, deadline)
                    stored = preprocessing['closed_anchor_preelimination']
                    for key, value in anchor_stats.items():
                        check('anchor_'+key, value, stored[key], **context)
                    check('anchor_source_identity', stored['filter_source_sha256'], READS['research/chapter3_experiments/anchor_preelimination.py'], **context)
                zero_ids = {o['option_id'] for o in actual if formulation['fix_late_options'] and F(o['end_ms'])>F(o['request_deadline_ms'])}
                events = sorted({F(0),F(instance['window_ms'])}|{F(o[k]) for o in actual for k in ('start_ms','end_ms')})
                check('remaining_option_columns', len(actual), summary['options'], **context)
                check('late_retained_zero_bound_columns', len(zero_ids), summary['deadline_fixed_options'], **context)
                check('binary_columns_are_option_columns_with_continuous_auxiliaries', len(actual), summary['binary_variables'], **context)
                check('event_count', len(events), summary['events_per_scene'][sid], **context)
                phase_dir = folder if pindex==1 else folder/'pass_02'
                logpath = phase_dir/f'build_scene_{sindex:03d}.jsonl'
                logs = [json.loads(line) for line in read(logpath, parsed=False).splitlines() if line.strip()]
                finished = [r for r in logs if r['status']=='MODEL_CONSTRUCTED']
                check('complete_model_log_pair_report_then_finish', len(finished), 2, **context)
                check('complete_log_pair_same_model_counts',
                    [{k:row[k] for k in ('options','variables','binary_variables','rows')} for row in finished],
                    [{k:summary[k] for k in ('options','variables','binary_variables','rows')}]*2, **context)
                final_log = finished[-1]
                for key in ('options','variables','binary_variables','rows'):
                    check('log_summary_'+key, final_log[key], summary[key], **context)
                check('log_replayed_option_columns', final_log['options'], len(actual), **context)
                mode_logs=[r for r in logs if r['current_stage']=='mode_variables']
                check('mode_variables_log_replayed_options', mode_logs[0]['options'], len(actual), **context)
                opened, closed = copy_rows(instance,condition,pindex,sid,original,shared,n1,deadline,actual,zero_ids)
                warm_source = condition.get('warm_options_by_scene',condition['seed_options_by_scene'])
                initial_record = read(phase_dir/f'initial_scene_{sindex:03d}.json')
                check('saved_initial_record_matches_phase_metadata', initial_record, saved['initialisation'], **context)
                actual_candidates = initial_record['candidate']['scenes'][sid]
                allowed = {(o['stage_instance_id'],o['unit_id'],o['opp_id'],F(o['start_ms']))
                           for o in actual if o['option_id'] not in zero_ids}
                check('actual_x0_candidate_all_rows_in_exact_replayed_domain',
                    all((o['stage_id'],o['unit'],o['opp'],F(o['start_ms'])) in allowed for o in actual_candidates),
                    True, **context)
                check('actual_x0_candidate_contains_every_active_scene_copy',
                    sorted(o['stage_id'] for o in actual_candidates),
                    sorted(s['id'] for s in scene['stage_instances']), **context)
                build = {'build_key': build_key, 'case_id': f'base__R{n}', 'phase_index': pindex,
                    'scene_id': sid, 'source_folder': str(folder.relative_to(ROOT)).replace('\\','/'),
                    'condition_sha256': condition['condition_sha256'], 'phase_condition': deepcopy(phase_condition),
                    'phase_started_at_s': phase['started_at_s'],
                    'first_build_log_at_s': logs[0]['method_elapsed_seconds'],
                    'model_completed_at_s': saved['model_completed_at_s'],
                    'time_limit': 'first log follows entry to builder; exact function-entry timestamp was not archived',
                    'opened_rows': opened, 'closed_rows': closed,
                    'warm_rows': [{'stage_id':k,**v} for k,v in warm_source[sid].items()],
                    'warm_rows_scope': 'condition anchor only: phase1 fresh seed, phase2 frozen first-pass complete SAFE; distinct from build x0 below',
                    'all_scene_warm_options': deepcopy(warm_source),
                    'actual_x0': {'candidate':deepcopy(initial_record['candidate']),
                        'local_candidate_sha256':canonical(initial_record['candidate']),
                        'source':initial_record.get('source'),
                        'full_snapshot_candidate_sha256':initial_record.get('snapshot_candidate_sha256'),
                        'state':initial_record.get('state'),
                        'completed_at_s':initial_record.get('completed_at_s'),
                        'x0_injected':saved.get('x0_injected'),
                        'numerical_admission':deepcopy(initial_record.get('completion',{}).get('numerical_acceptance')),
                        'different_from_condition_anchor_stage_ids':[o['stage_id'] for o in actual_candidates
                            if any(o[k] != warm_source[sid][o['stage_id']][k] for k in ('unit','opp','start_ms'))],
                        'scope':'archived candidate and original admission only; no x0 vector reconstructed or thermal reevaluation'},
                    'counts': {'original_release_window_options':len(original),'after_shared_device_prefilter':len(shared),
                        'after_neighborhood':len(n1),'deadline_deleted':len(n1)-len(deadline),
                        'after_deadline_delete':len(deadline),
                        'anchor_deleted':len(deadline)-len(actual), 'actual_option_columns':len(actual),
                        'retained_upper_bound_zero_columns':len(zero_ids),'actual_nonzero_options':len(actual)-len(zero_ids),
                        'archived_total_variables':summary['variables'],'archived_binary_variables':summary['binary_variables']},
                    'actual_option_columns_sha256':canonical(actual),
                    'formulation':deepcopy(formulation),
                    'stage_option_column_scope':'0-based y columns; all option columns precede auxiliary columns',
                    'domain_scope':'exact materialized local label domain; not all joint-feasible schedules or a thermal certification',
                    'joint_constraints_not_preeliminated':['open/open resource conflict','open/open dependency',
                        'all non-filtered resource/dependency rows','continuous thermal constraints'],
                    'all_checks_passed':all(c['passed'] for c in CHECKS if c.get('build_key')==build_key)}
                builds.append(build)
    after = {key:sha((ROOT/key).read_bytes()) for key in READS}
    check('all_original_inputs_logs_declarations_sources_unchanged', after, READS)
    return {'protocol':'K171-archived-P0-build-domains-stdlib-replay-v1',
        'builds':builds,'source_checks':source_checks,'checks':CHECKS,
        'source_and_archive_before_sha256':dict(READS),'source_and_archive_after_sha256':after,
        'guard':{**GUARD,'all_zero':not any(GUARD.values()),
            'build_model_calls':0,'input_builder_calls':0,'solver_calls':0,'thermal_calls':0,
            'schedule_or_candidate_generation_calls':0,'research_calls':0},
        'limitations':['No auxiliary MILP matrix reconstructed; total variable/row counts copied and cross-checked only between original log and original summary.',
            'Only finite mode/start label intersection is replayed; it does not solve joint resource, dependency or thermal feasibility.',
            'First build log is not exact function-entry timestamp; use an earlier certified-U time to justify any online counterfactual deletion.'],
        'passed':all(c['passed'] for c in CHECKS) and not any(GUARD.values())}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=HERE/'facts.json')
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError('refuse to overwrite evidence: '+str(args.output))
    sys.addaudithook(audit)
    sys.setprofile(profile)
    try:
        facts=replay()
    finally:
        sys.setprofile(None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(facts,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    failures=[c for c in facts['checks'] if not c['passed']]
    print(json.dumps({'passed':facts['passed'],'builds':len(facts['builds']),
        'checks':len(facts['checks']),'failures':len(failures),'guard':facts['guard'],
        'output':str(args.output)},ensure_ascii=False))
    if failures:
        print(json.dumps(failures[:4],ensure_ascii=False)[:6000])
    return 0 if facts['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
