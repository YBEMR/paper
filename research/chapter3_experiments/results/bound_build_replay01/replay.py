"""Read-only algebra over archived P0 builds; never a production filter.

Only the standalone exact bound module may be imported from the research tree.
Archive extraction and domain reconstruction have independent evidence files.
"""
import argparse
import copy
from fractions import Fraction as F
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCIENCE = REPO/'research/chapter3_experiments'
CORE_SHA256 = '9b4fc402a00c71d9f919c3829df0b43277df614fbd5fcfe2aec6d67de02c6e0a'


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def select_timely_upper(updates, *, case_id, input_sha256, call_directory, build_at_s):
    """Admit only independently archive-verified, delivered same-call globals.

    This trusts the extraction's evidence verification, not a fresh heat check.
    It cannot issue the private production admission token in K170.
    """
    build = F(str(build_at_s))
    admitted, rejected = [], []
    for update in updates:
        row = copy.deepcopy(update)
        reason = None
        if (row.get('case_id') != case_id or row.get('input_sha256') != input_sha256
                or row.get('call_directory') != call_directory):
            reason = 'DIFFERENT_CALL_OR_INPUT'
        elif (row.get('state') != 'SAFE' or row.get('complete_global') is not True
                or row.get('evidence_verified') is not True):
            reason = 'NO_VERIFIED_COMPLETE_GLOBAL_SAFE_EVIDENCE'
        else:
            try:
                ticks = [F(str(row[k])) for k in ('formed_at_s','committed_at_s',
                    'transferred_at_s','observer_completed_at_s')]
                upper = F(row['upper_J'])
                if upper < 0 or min(ticks) < 0:
                    reason = 'INVALID_UPPER_OR_TIME'
                elif ticks != sorted(ticks):
                    reason = 'NONCAUSAL_EVIDENCE_TIMES'
                elif max(ticks) >= 300 or max(ticks) >= build:
                    reason = 'NOT_DELIVERED_BEFORE_BUILD'
                else:
                    row['available_at_s_exact'] = str(max(ticks))
                    admitted.append(row)
            except (KeyError,ValueError,TypeError,ZeroDivisionError):
                reason = 'MISSING_OR_INVALID_EXACT_FIELDS'
        if reason:
            rejected.append({'source_index':row.get('source_update_index'),'reason':reason})
    best = min(admitted,key=lambda x:(F(x['upper_J']),F(x['available_at_s_exact']))) if admitted else None
    return {'upper':best,'admitted_indices':[x.get('source_update_index') for x in admitted],
            'rejected':rejected,'production_pruning_authorized':False}


def mode_is_countable(row):
    """A mode must be open and have at least one original nonzero option."""
    return (row.get('opened') is True and row.get('domain_verified') is True
            and isinstance(row.get('remaining_option_count'),int)
            and not isinstance(row['remaining_option_count'],bool)
            and row['remaining_option_count'] > 0)


def strict_decision(bound, upper, *, witness_compatible=False, witness_upper_J=None):
    """Exact strict comparison and a contradiction gate for compatible SAFE U."""
    if upper is None:
        return {'state':'NO_TIMELY_SAFE_U','excludable':False,
                'production_pruning_authorized':False}
    lower, value = F(bound['lower_bound_J']), F(upper['upper_J'])
    if witness_compatible:
        if witness_upper_J is None:
            raise ValueError('Compatible safe witness requires its exact upper')
        if lower > F(witness_upper_J):
            raise ValueError('Bound exceeds a compatible archived SAFE witness')
    return {'state':'EXCLUDABLE' if lower > value else 'KEEP_TIE' if lower == value else 'KEEP',
            'excludable':lower > value,'difference_J':str(lower-value),
            'legacy_excludable':F(bound['legacy_conditioned_lower_bound_J']) > value,
            'capacity_excludable':F(bound['capacity_lower_bound_J']) > value,
            'forced_excludable':F(bound['forced_residency_lower_bound_J']) > value,
            'production_pruning_authorized':False}


class NoScience(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.attempts = []

    def find_spec(self,fullname,path=None,target=None):
        first = fullname.split('.')[0]
        if first in {'scipy','numpy','matlab','thermal','milp','inputs','schedules',
                     'formal','method_runner','linked_method','neighborhood_method',
                     'scene_adapter','partial_receipts','subprocess','socket'}:
            self.attempts.append(fullname)
            raise RuntimeError('Read-only replay forbids scientific/process imports: '+fullname)
        return None


def main(output):
    if output.exists():
        raise FileExistsError('Replay records are append-only')
    output.mkdir(parents=True)
    started = time.perf_counter()
    frozen_paths = [HERE/'protocol.md',HERE/'timeline/facts.json',
        HERE/'domain/facts.json',Path(__file__),SCIENCE/'conditional_energy_bound/bounds.py']
    frozen_before = {str(p.relative_to(REPO)).replace('\\','/'):sha(p) for p in frozen_paths}
    if sha(SCIENCE/'conditional_energy_bound/bounds.py') != CORE_SHA256:
        raise ValueError('K170 core source changed')
    timeline, domain = read(HERE/'timeline/facts.json'), read(HERE/'domain/facts.json')
    if timeline['status'] != 'PASS' or not domain['passed']:
        raise ValueError('Archive extraction is not complete and verified')
    original_hashes = dict(timeline['original_file_sha256'])
    for name,value in domain['source_and_archive_before_sha256'].items():
        if name in original_hashes and original_hashes[name] != value:
            raise ValueError('Archive extractors bind different original content')
        original_hashes[name] = value
    if any(sha(REPO/name)!=value for name,value in original_hashes.items()):
        raise ValueError('Original archive/source changed since extraction')
    guard = NoScience()
    sys.meta_path.insert(0,guard)
    process_attempts = []

    def audit(event,args):
        if event in ('subprocess.Popen','os.system','os.posix_spawn','socket.connect'):
            process_attempts.append(event)
            raise RuntimeError('Read-only replay forbids process/network entry')

    sys.addaudithook(audit)
    sys.path.insert(0,str(SCIENCE))
    from conditional_energy_bound.bounds import prepare,compare_exact_bound
    checks, records, prepare_seconds = {}, [], {}
    input_hashes = {}
    for case in timeline['cases']:
        case_id = case['problem_id']
        folder = (REPO/case['result_path']).parent
        call_directory = str(folder.relative_to(REPO)).replace('\\','/')
        instance, result = read(REPO/case['input_path']), read(folder/'result.json')
        input_hashes[case_id] = canonical(instance)
        tick = time.perf_counter()
        ctx = prepare(instance)
        prepare_seconds[case_id] = time.perf_counter()-tick
        if ctx.input_sha256 != case['input_sha256']:
            raise ValueError('Original full input identity mismatch')
        for point in case['builds']:
            key = f"{case_id}/phase_{point['phase_index']}/{point['scene_id']}"
            matches = [d for d in domain['builds'] if d['build_key'] == key]
            if len(matches) != 1 or not matches[0]['all_checks_passed']:
                raise ValueError('Missing or unresolved exact original domain: '+key)
            d = matches[0]
            if point['condition_sha256'] != d['condition_sha256']:
                raise ValueError('Build time and domain use different conditions')
            selected = select_timely_upper(case['verified_updates'],case_id=case_id,
                input_sha256=ctx.input_sha256,call_directory=call_directory,
                build_at_s=point['build_started_at_s'])
            upper = selected['upper']
            if (upper is None or F(upper['upper_J']) != F(point['available_safe_upper_bound_J'])
                    or upper['source_update_index'] != point['chosen_update_index']):
                raise ValueError('Independent timeline selectors disagree')
            phase = next(p for p in result['phases'] if p['phase_index']==point['phase_index'])
            condition = phase['condition']
            partial = d['phase_condition']
            timely_receipt = result['aggregation_attempts'][upper['source_aggregation_index']]
            if (timely_receipt['receipt_sha256'] != upper['receipt_sha256']
                    or canonical(timely_receipt['safe_candidate']) != upper['candidate_sha256']
                    or F(timely_receipt['safe_upper_bound_J']) != F(upper['upper_J'])):
                raise ValueError('Selected update/aggregate/candidate identities disagree')
            witnesses = []
            for label,candidate,receipt in [
                    ('fresh_seed',condition['seed_candidate'],condition['seed_receipt']),
                    ('phase_anchor',condition.get('warm_candidate',condition['seed_candidate']),
                     condition.get('warm_receipt',condition['seed_receipt'])),
                    ('timely_global_U',timely_receipt['safe_candidate'],timely_receipt)]:
                witnesses.append({'label':label,'candidate':candidate,
                    'upper_J':receipt['safe_upper_bound_J'],
                    'candidate_sha256':canonical(candidate)})

            def compatible(candidate,restriction):
                lookup={sid:{r['stage_id']:r for r in rows}
                        for sid,rows in candidate['scenes'].items()}
                return all(all(lookup[sid][stage][field]==value for field,value in fields.items())
                    for sid,stages in restriction['by_scene'].items() for stage,fields in stages.items())

            tick = time.perf_counter()
            base = ctx.bound(partial)
            base_s = time.perf_counter()-tick
            base_witnesses = [w for w in witnesses if compatible(w['candidate'],partial)]
            if not base_witnesses or any(F(base['lower_bound_J'])>F(w['upper_J']) for w in base_witnesses):
                raise ValueError('Base bound contradicts compatible archived SAFE evidence')
            probes, skipped = [], []
            tick = time.perf_counter()
            for copyrow in d['opened_rows']+d['closed_rows']:
                for mode in copyrow['modes']:
                    countrow={'opened':copyrow['opened'],'domain_verified':d['all_checks_passed'],
                              'remaining_option_count':mode['options_nonzero']}
                    label={'stage_id':copyrow['stage_id'],'shared_stage_id':copyrow['shared_stage_id'],
                        'unit':mode['unit'],'opp':mode['opp'],
                        'remaining_option_count':mode['options_nonzero'],
                        'remaining_starts_ms':mode['starts_ms'],'option_columns':mode['option_columns']}
                    if not mode_is_countable(countrow):
                        skipped.append(dict(label,reason='CLOSED' if not copyrow['opened'] else 'NO_ORIGINAL_NONZERO_OPTION'))
                        continue
                    child = copy.deepcopy(partial)
                    child['by_scene'][d['scene_id']][copyrow['stage_id']].update(unit=mode['unit'],opp=mode['opp'])
                    bound = ctx.bound(child)
                    cmp = compare_exact_bound(bound,upper['upper_J'],ctx.input_sha256)
                    child_witnesses = [w for w in witnesses if compatible(w['candidate'],child)]
                    for w in child_witnesses:
                        if F(bound['lower_bound_J']) > F(w['upper_J']):
                            raise ValueError('Mode bound excludes compatible old SAFE witness')
                    decision = strict_decision(bound,upper)
                    if (cmp['comparison']=='HIGHER') != decision['excludable']:
                        raise ValueError('Exact comparison implementations disagree')
                    x0_rows = d['actual_x0']['candidate']['scenes'][d['scene_id']]
                    in_x0 = any(r['stage_id']==label['stage_id'] and r['unit']==label['unit']
                        and r['opp']==label['opp'] for r in x0_rows)
                    # The actual initial candidate is the local projection of
                    # the selected complete SAFE generation (timeline check).
                    if decision['excludable'] and in_x0:
                        raise ValueError('Read-only screen would remove original SAFE warm start')
                    probes.append({'label':label,'partial':child,'bound':bound,'comparison':cmp,
                        'decision':decision,'in_actual_x0':in_x0,
                        'compatible_archived_witnesses':[w['label'] for w in child_witnesses],
                        'new_beyond_conditioned_legacy':decision['excludable'] and not decision['legacy_excludable'],
                        'forced_extra_over_capacity':decision['excludable'] and not decision['capacity_excludable']})
            probe_s = time.perf_counter()-tick
            records.append({'build_key':key,'case_id':case_id,'phase_index':d['phase_index'],
                'scene_id':d['scene_id'],'condition_sha256':d['condition_sha256'],
                'build_started_at_s':point['build_started_at_s'],'timely_upper':upper,
                'timeline_selection':{k:v for k,v in selected.items() if k!='upper'},
                'phase_condition':partial,'base_bound':base,
                'base_compatible_witnesses':[w['label'] for w in base_witnesses],
                'original_domain_counts':d['counts'],'probes':probes,'skipped':skipped,
                'statistics':{'countable_open_modes':len(probes),
                    'excludable_modes':sum(p['decision']['excludable'] for p in probes),
                    'excludable_nonzero_option_columns':sum(p['label']['remaining_option_count'] for p in probes if p['decision']['excludable']),
                    'beyond_conditioned_legacy':sum(p['new_beyond_conditioned_legacy'] for p in probes),
                    'forced_extra_over_capacity':sum(p['forced_extra_over_capacity'] for p in probes),
                    'all_safe_actual_x0_modes_preserved':all(not p['in_actual_x0'] or not p['decision']['excludable'] for p in probes)},
                'replay_algebra_seconds':{'base':base_s,'open_mode_probes':probe_s},
                'interpretation':'Read-only opportunity at original start; not actual production deletion or a new 300s-budget execution'})
    frozen_after = {str(p.relative_to(REPO)).replace('\\','/'):sha(p) for p in frozen_paths}
    checks['frozen_sources_and_facts_unchanged'] = frozen_before==frozen_after
    checks['all_extraction_original_files_unchanged'] = all(sha(REPO/name)==value for name,value in original_hashes.items())
    checks['twenty_original_builds_no_missing'] = len(records)==20
    checks['all_timely_U_before_build'] = all(F(r['timely_upper']['available_at_s_exact']) < F(str(r['build_started_at_s'])) for r in records)
    checks['all_actual_x0_modes_kept'] = all(r['statistics']['all_safe_actual_x0_modes_preserved'] for r in records)
    checks['all_bases_compatible_with_old_SAFE'] = all(r['base_compatible_witnesses'] for r in records)
    checks['all_probes_real_open_nonzero_options'] = all(p['label']['remaining_option_count']>0 for r in records for p in r['probes'])
    checks['no_forbidden_imports_or_process'] = not guard.attempts and not process_attempts
    rows=[p for r in records for p in r['probes']]
    summary={'builds':len(records),'open_mode_instances':len(rows),
        'excludable_modes':sum(p['decision']['excludable'] for p in rows),
        'excludable_nonzero_option_columns':sum(p['label']['remaining_option_count'] for p in rows if p['decision']['excludable']),
        'beyond_conditioned_legacy':sum(p['new_beyond_conditioned_legacy'] for p in rows),
        'forced_extra_over_capacity':sum(p['forced_extra_over_capacity'] for p in rows)}
    evidence={'protocol':'K171-timely-P0-build-exact-bound-readonly-replay-v1',
        'passed':all(checks.values()),'checks':checks,'summary':summary,
        'frozen_sha256_before':frozen_before,'frozen_sha256_after':frozen_after,
        'original_file_sha256':original_hashes,
        'input_sha256':input_hashes,'records':records,'prepare_seconds_by_case':prepare_seconds,
        'guard':{'forbidden_import_attempts':guard.attempts,'process_network_attempts':process_attempts,
                 'new_model_builds':0,'optimization_calls':0,'thermal_calls':0,'formal_evaluations':0,
                 'new_research_calls':0,'production_filters_changed':False},
        'total_replay_wall_s':time.perf_counter()-started,
        'cost_scope':'One archive+algebra replay, not original method time or a speedup measurement'}
    (output/'results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print(json.dumps({'passed':evidence['passed'],**summary,'output':str(output)},ensure_ascii=False))
    if not evidence['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
