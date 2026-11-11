"""Verify exact K194 coverage and compare the two original R1 formulations."""
import argparse
from collections import Counter
from fractions import Fraction
from functools import partial
import hashlib
import json
from pathlib import Path
import subprocess

from inputs import expand_options
from milp import build_model
from option_propagation import propagate_local_options
from thermal import Budget, Exhausted


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ARCHIVE = '4339bdcc'
RESULTS = 'research/chapter3_experiments/results'
R1 = f'{RESULTS}/prefilter_diagnostic01/base__R1__prefilter'
HEFT = f'{RESULTS}/formal_comparison01/base__R1__heft/result.json'
AUTO_LOW_R1 = f'{RESULTS}/p0_execution01/calls/base__R1/heft'
FLAGS = dict(prefilter_deadlines=True, fix_late_options=True, aggregate_opp_locks=True,
             relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True)
SECONDS = 300


def archived(path):
    return subprocess.check_output(['git', 'show', f'{ARCHIVE}:{path}'], cwd=REPO)


def r1_input(budget, profile='hold-last'):
    folder = AUTO_LOW_R1 if profile == 'auto-low' else R1
    raw = {name: archived(f'{folder}/input_{name}.json') for name in ('config', 'instance')}
    if profile == 'auto-low':
        expected = {'config': '132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2',
                    'instance': '01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89'}
        if any(hashlib.sha256(raw[name]).hexdigest() != expected[name] for name in raw):
            raise ValueError('Current auto-L R1 input identity differs from the frozen experiment')
    config, instance = (json.loads(raw[name]) for name in ('config', 'instance'))
    budget.check()
    return config, instance


def save(path, result):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def check_small_domain():
    from small_exact_preparation.contract import make_manifest

    input_bytes = archived(f'{RESULTS}/small_full_chain_precheck02/restricted_input.json')
    config_bytes = archived(f'{RESULTS}/whole_long_budget01/method/input_config.json')
    instance, config = map(json.loads, (input_bytes, config_bytes))
    manifest, independent = make_manifest(instance, config)
    baseline = [o for o in expand_options(instance, config)
                if Fraction(o['end_ms']) <= Fraction(o['request_deadline_ms'])]
    retained, trace = propagate_local_options(instance, baseline, budget=Budget())

    def supported(catalog):
        labels = {(o['scenario_id'], o['stage_instance_id'], o['unit_id'], o['opp_id'], o['start_ms'])
                  for o in catalog}
        return {r['id'] for r in manifest if all(
            (sid, o['stage_id'], o['unit'], o['opp'], o['start_ms']) in labels
            for sid, rows in r['candidate']['scenes'].items() for o in rows)}

    baseline_ids, retained_ids = map(supported, (baseline, retained))
    if baseline_ids != retained_ids or len(retained_ids) != len(manifest):
        raise ValueError('A complete independently legal schedule is missing')
    return dict(archive=ARCHIVE, input_sha256=hashlib.sha256(input_bytes).hexdigest(),
                config_sha256=hashlib.sha256(config_bytes).hexdigest(),
                baseline_options=len(baseline), retained_options=len(retained),
                scene_schedules_checked=len(manifest), scene_schedule_ids_identical=True,
                scene_schedule_ids_sha256=hashlib.sha256('\n'.join(sorted(retained_ids)).encode()).hexdigest(),
                joint_schedules_identical=independent['global_legal_complete_arrangements'],
                propagation=trace)


def check_r1(out, arm, profile='hold-last'):
    from method_runner import execute_milp

    def build(instance, config, **kwargs):
        model = build_model(instance, config, **FLAGS, propagate_options=arm == 'propagation', **kwargs)
        counts = {sid: dict(options=len(s['options']), intervals=len(s['events'])-1,
                            joint_states=len(s['joint'])) for sid, s in model.scenes.items()}
        rows = Counter(r['tag'] for r in model.rows)
        save(Path(out)/'structure.json', dict(arm=arm, archive=ARCHIVE, profile=profile, scenes=counts,
             conditional_electrothermal_rows=2*(len(instance['platform']['node_order'])+1)
                 *sum(s['joint_states'] for s in counts.values()), raw_row_tags=dict(rows)))
        return model

    return execute_milp(partial(r1_input, profile=profile), out,
                        seconds=60 if profile == 'auto-low' else SECONDS,
                        construct_only=True, model_builder=build)


def prepare_common_seed(model, config, budget, profile='hold-last'):
    from heft_method import run_heft
    from heuristic_runner import CandidateRecorder
    from initial_point import complete_initial_point
    from milp import evaluate_model_candidate

    def evaluate(_instance, candidate, accuracy, root):
        return evaluate_model_candidate(model, candidate, accuracy, root)

    with budget.phase('common_heft_generation_and_validation'):
        recorder = CandidateRecorder(model.instance, config['accuracy_targets'], budget, evaluator=evaluate)
        search = run_heft(model.instance, config, budget, recorder.assess,
                          allow_auto_low=profile == 'auto-low')
        reference = f'{AUTO_LOW_R1}/result.json' if profile == 'auto-low' else HEFT
        expected = json.loads(archived(reference))['safe_candidate']
        if search['status'] != 'BOUNDED_SEARCH_COMPLETED' or recorder.best is None:
            raise ValueError('The common HEFT seed search did not complete with SAFE')
        best = recorder.best
        if best['candidate'] != expected:
            raise ValueError('Fresh HEFT seed differs from the frozen common schedule')
    try:
        completion = complete_initial_point(model, best['candidate'], best['evaluation'], budget)
    except Exhausted as error:
        completion = dict(state='INITIAL_POINT_UNRESOLVED', reason=str(error), x0=None)
    return best, completion


def check_r1_seed(arm, profile='hold-last'):
    import matlab_bridge
    from numeric_case_diagnostic.equality_session import _normalise
    from timing import MethodBudget

    budget = MethodBudget(120 if profile == 'auto-low' else SECONDS)
    config, instance = r1_input(budget, profile)
    model = build_model(instance, config, **FLAGS, propagate_options=arm == 'propagation', budget=budget)
    seed, completion = prepare_common_seed(model, config, budget, profile)
    x0 = completion.pop('x0')
    represented = None
    if x0 is not None:
        with budget.phase('exact_equality_conversion_and_certificate'):
            _, _, native, certificate = _normalise(model.as_solver_dict(), x0, matlab_bridge)
            represented = dict(inequalities=native['A'].shape[0], equalities=native['Aeq'].shape[0],
                               nonzeros=int(native['A'].nnz+native['Aeq'].nnz),
                               equivalence_checks=certificate['checks'])
        budget.check()
    return dict(state=completion['state'], profile=profile,
                initial_vector_size=None if x0 is None else len(x0),
                candidate_sha256=seed['candidate_sha256'], safe_upper_bound_J=seed['evaluation']['safe_upper_bound_J'],
                completion=completion, represented=represented, seed=seed,
                phases_s=budget.summary()['phases_exclusive_s'])


def solve_r1_pair(out, matlab):
    from formal_milp import solve_formal_diagnostic
    from initial_point import _InitialSession
    from matlab_bridge import MatlabSession
    from method_runner import execute_milp
    from numeric_case_diagnostic.equality_session import attach

    if not matlab.is_file():
        raise FileNotFoundError(f'MATLAB R2023b executable unavailable: {matlab}')
    out.mkdir(parents=True, exist_ok=False)

    def create_session(*args, **kwargs):
        session = MatlabSession(*args, **kwargs, matlab_path=matlab.resolve())
        try:
            return attach(session)
        except BaseException:
            session.close()
            raise

    config = None

    def load(budget):
        nonlocal config
        config, instance = r1_input(budget)
        return config, instance

    def solve(model, session, accuracy, budget):
        seed, completion = prepare_common_seed(model, config, budget)
        x0 = completion.pop('x0')
        save(session.workdir.parent/'initial_point.json', {'seed': seed, 'completion': completion})
        result = {'reason': 'COMMON_HEFT_INITIAL_POINT_REJECTED'}
        if x0 is not None:
            result = solve_formal_diagnostic(model, _InitialSession(session, x0), accuracy, budget)
        initial_u = seed['evaluation']['safe_upper_bound_J']
        solver_u = result.get('safe_upper_bound_J')
        result.update(first_initial_safe_s=seed['evaluation']['completed_at_elapsed_s'],
                      initial_safe_upper_bound_J=initial_u, milp_safe_upper_bound_J=solver_u)
        if solver_u is None or Fraction(initial_u) <= Fraction(solver_u):
            result.update(state='SAFE', safe_candidate=seed['candidate'],
                          safe_upper_bound_J=initial_u, evaluation=seed['evaluation'],
                          safe_solution_source='common_heft_seed')
        else:
            result['safe_solution_source'] = 'MILP_candidate'
        return result

    for arm in ('baseline', 'propagation'):
        execute_milp(load, out/arm, seconds=SECONDS, construct_only=False,
                     model_builder=partial(build_model, **FLAGS, propagate_options=arm == 'propagation'),
                     session_factory=create_session, solve=solve)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    small = commands.add_parser('small')
    small.add_argument('output', type=Path)
    r1 = commands.add_parser('build')
    r1.add_argument('arm', choices=('baseline', 'propagation'))
    r1.add_argument('output', type=Path)
    r1.add_argument('--profile', choices=('hold-last', 'auto-low'), default='hold-last')
    seed = commands.add_parser('seed')
    seed.add_argument('arm', choices=('baseline', 'propagation'))
    seed.add_argument('output', type=Path)
    seed.add_argument('--profile', choices=('hold-last', 'auto-low'), default='hold-last')
    pair = commands.add_parser('pair')
    pair.add_argument('output', type=Path)
    pair.add_argument('--matlab', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'small':
        save(args.output, check_small_domain())
        return 0
    if args.command == 'seed':
        receipt = check_r1_seed(args.arm, args.profile)
        save(args.output, receipt)
        return 0 if receipt['state'] == 'INITIAL_POINT_READY' else 1
    if args.command == 'pair':
        solve_r1_pair(args.output, args.matlab)
        return 0
    return 0 if check_r1(args.output, args.arm, args.profile)['state'] == 'CONSTRUCTION_COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
