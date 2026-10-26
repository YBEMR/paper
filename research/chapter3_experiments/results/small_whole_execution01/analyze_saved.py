"""K196: read saved evidence only; no optimizer or physical evaluation."""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREP = HERE.parent / 'small_whole_preparation01'
REFERENCE = HERE.parent / 'small_exact_execution01' / 'reference.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(candidate):
    return {scene: sorted(rows, key=lambda row: row['stage_id'])
            for scene, rows in candidate['scenes'].items()}


def decimal(value):
    with localcontext() as ctx:
        ctx.prec = 65
        value = F(value)
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def analyse():
    plan = read(PREP / 'plan.json')
    approval = read(PREP / 'approval.json')
    launch = read(HERE / 'launch.claim.json')
    terminal = read(HERE / 'terminal.json')
    result = read(HERE / 'method/wrapper_raw_result.json')
    admitted = read(HERE / 'method_return.json')
    post = read(HERE / 'post_return.json')
    fresh = read(HERE / 'postcheck.json')
    initial = result['initialisation']['witness']
    native = read(HERE / 'method/matlab/request_000001.response.json')
    events = [json.loads(line) for line in
              (HERE / 'method/diagnostic_events.jsonl').read_text(encoding='utf-8').splitlines()]
    evaluated = [event for event in events if event.get('event') == 'candidate_evaluated']
    reference = read(REFERENCE)
    U = F(result['safe_upper_bound_J'])
    initial_U = F(initial['evaluation']['safe_upper_bound_J'])
    Lref, Uref = F(reference['lower_bound_J']), F(reference['upper_bound_J'])
    first_new = next(event for event in evaluated
                     if canon(event['candidate']) != canon(initial['candidate']))
    metrics = admitted['records']['original_audit']['completion_metrics']
    changes = []
    for scene, rows in canon(result['safe_candidate']).items():
        old = {row['stage_id']: row for row in initial['candidate']['scenes'][scene]}
        for row in rows:
            before = old[row['stage_id']]
            changed = {key: {'before': before[key], 'after': row[key]}
                       for key in ('unit', 'opp', 'start_ms') if before[key] != row[key]}
            if changed:
                changes.append({'scene': scene, 'stage_id': row['stage_id'], 'changes': changed})
    checks = {
        'frozen_plan': sha(PREP / 'plan.json') == '75f692f7681b294e41c7dc229c30517de4d4461da383985e6554cfa415466d5e',
        'approval_bound': launch['approval_sha256'] == sha(PREP / 'approval.json') and approval['approved_by_user'] is True,
        'one_method_one_post_no_retry': terminal['research_calls'] == terminal['post_calls'] == 1 and terminal['no_retry'],
        'root_300_and_cutoff_300': result['timing']['limit_s'] == result['timing']['method_elapsed_s'] == metrics['evidence_cutoff_s'] == 300,
        'calendar_within_480': terminal['calendar_s'] <= 480 and terminal['calendar_limit_respected'],
        'new_safe_before_cutoff': first_new['accepted_safe'] and first_new['evaluation_returned_at_s'] < 300,
        'strict_energy_improvement': U < F(initial['evaluation']['weighted_energy_J'][0]),
        'final_candidate_is_early_new_candidate': canon(result['safe_candidate']) == canon(first_new['candidate']),
        'last_response_not_new_evidence': admitted['records']['original_audit']['execution']['new_or_late_candidate_accepted'] is False,
        'post_fresh_safe_same_candidate_and_U': post['passed'] and post['evaluation_calls'] == 1 and fresh['state'] == 'SAFE' and F(fresh['safe_upper_bound_J']) == U,
        'post_within_60': post['wall_s'] < 60 and fresh['completed_at_elapsed_s'] < 60,
        'original_result_unchanged': post['original_result_unchanged'] and post['original_result_sha256'] == sha(HERE / 'method/wrapper_raw_result.json'),
        'enumeration_reference_valid': reference['formal_reference_accepted'] and reference['formed_before_root_deadline'],
        'finite_domain_epsilon_reached': U >= Lref and U - Lref <= F(reference['epsilon_J']),
        'same_upper_as_enumeration': U == Uref,
        'live_scientific_sources_match': all(sha(ROOT / name) == expected for name, expected in plan['source_sha256'].items()),
        'wrappers_match': all(sha(ROOT / name) == expected for name, expected in plan['wrapper_sha256'].items()),
        'normal_time_limit_not_numeric_failure': admitted['records']['normal_terminal'] and not admitted['records']['original_audit']['context']['observed_numerical_rejection'],
        'owned_native_processes_closed': read(HERE / 'method/matlab/closed.json')['observed_tree_verified_terminated'],
    }
    evidence = {str(path.relative_to(HERE)): sha(path) for path in sorted(HERE.rglob('*'))
                if path.is_file() and path.name not in {'analysis.json', 'analyze_saved.py', 'internal_review_k196.json', 'archival_scope.json'}}
    return {
        'protocol': 'K196-saved-evidence-analysis-v1', 'passed': all(checks.values()), 'checks': checks,
        'scope': 'JSON/hash/rational arithmetic only; zero new optimization or thermal evaluation',
        'method': {
            'state': admitted['records']['original_audit']['execution']['execution_status'],
            'root_seconds': 300, 'process_wall_s': terminal['phases'][0]['wall_s'],
            'cleanup_s': metrics['cleanup_s'], 'wrapper_wall_s': admitted['wall_including_cleanup_s'],
            'calendar_s': terminal['calendar_s'], 'post_wall_s': post['wall_s'],
            'MATLAB_startup_s': metrics['matlab_startup']['wall_s'],
            'model_construction_s': result['timing']['phases_exclusive_s']['model_construction'],
            'solver_entered_received_s': result['diagnostic']['solver_entered_received_s'],
            'first_initial_SAFE_s': result['first_initial_safe_s'],
            'first_callback_integer_received_s': result['diagnostic']['first_candidate_received_s'],
            'first_different_SAFE_at_s': first_new['evaluation_returned_at_s'],
            'native_call_wall_s': native['phase_seconds']['intlinprog_call'],
            'native_internal_final_time_s': native['callbacks'][-1]['values']['time'],
            'native_MaxTime_s': native['options']['MaxTime'], 'exitflag': native['exitflag'],
            'nodes': native['output']['numnodes'], 'numfeaspoints': native['output']['numfeaspoints'],
            'native_reported_relativegap': native['output']['relativegap'],
            'native_reported_absolutegap': native['output']['absolutegap'],
            'raw_model_summary': result['model_summary'], 'feedback_rows_added': len(result['feedback']),
        },
        'energy': {
            'initial_U_J': decimal(initial_U), 'final_U_J': decimal(U),
            'strict_reduction_J': decimal(initial_U-U), 'strict_reduction_percent': decimal(100*(initial_U-U)/initial_U),
            'reference_L_J': str(Lref), 'reference_U_J': str(Uref),
            'final_U_minus_reference_L_J': str(U-Lref),
            'final_U_minus_reference_L_decimal_J': decimal(U-Lref),
            'epsilon_J': reference['epsilon_J'],
            'solver_independently_proved_optimal': result['independently_proven_optimal'],
            'attains_independent_finite_domain_epsilon_reference': checks['finite_domain_epsilon_reached'],
        },
        'candidate_changes': changes,
        'initialisation': initial['candidate'], 'final_candidate': result['safe_candidate'],
        'evaluated_candidates': [{'source': event['source'], 'same_schedule_as_initial': canon(event['candidate']) == canon(initial['candidate']),
                                  'accepted_SAFE': event['accepted_safe'], 'completed_at_s': event['evaluation_returned_at_s'],
                                  'energy_J': event['evaluation']['weighted_energy_J']} for event in evaluated],
        'raw_evidence_sha256': evidence, 'reference_sha256': sha(REFERENCE),
    }


if __name__ == '__main__':
    result = analyse()
    with (HERE / 'analysis.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': result['checks'], 'energy': result['energy']}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 2)
