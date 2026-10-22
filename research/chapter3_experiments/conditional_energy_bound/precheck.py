"""K170 independent algebra/receipt prechecks; no scheduling or heat execution.

Small enumerations contain mode labels only. Their explicit energy ledgers
are algebra fixtures, not simulated schedules or fabricated thermal receipts.
P0 references, if accepted, come only from unchanged archived result/post files.
"""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import io
from itertools import product
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[3]
EXP = REPO / 'research/chapter3_experiments'
sys.path.insert(0, str(EXP))
from conditional_energy_bound.bounds import (prepare, BoundError,
    pruning_decision, compare_exact_bound)


OUT = None
READ_HASHES = {}
DETAILS = []


def read(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    if path.is_relative_to(REPO):
        READ_HASHES[str(path.relative_to(REPO)).replace('\\', '/')] = hashlib.sha256(data).hexdigest()
    return json.loads(data.decode('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def original(sample, method='whole_milp', filename='input_instance.json'):
    found = [EXP/'results'/batch/'calls'/f'base__R{sample}'/method/filename
             for batch in ('p0_execution01', 'p0_resume01')]
    found = [path for path in found if path.is_file()]
    if len(found) != 1:
        raise AssertionError('Original P0 file must occur once: ' + str(found))
    return found[0]


def toy(*, chain=False, zero_weight=False):
    """Manual integer modes; zero leakage isolates shared-OPP union accounting."""
    p = deepcopy(read(original(1))['platform'])
    p['external_common_power_W'] = '0'
    p['heat_capacity_J_per_K'] = ['100']*4
    p['conductance_W_per_K'] = [[str(int(i == j)) for j in range(4)] for i in range(4)]
    for did, domain in p['domains'].items():
        domain['baseline_W'] = {opp: ('0' if opp == 'L' or did != 'CPU'
                                      else '1' if opp == 'M' else '2') for opp in domain['opps']}
        domain['local_temperature_slope_W_per_K'] = {opp: '0' for opp in domain['opps']}
    modes = {}
    for shared in ('A', 'B'):
        modes[shared] = []
        for unit in ('CPU1', 'CPU2'):
            for opp in ('L', 'H'):
                point = p['domains']['CPU']['opps'][opp]
                modes[shared].append(dict(shared_stage_id=shared, unit_id=unit,
                    domain_id='CPU', power_group_id='CPU', thermal_node_id=unit,
                    opp_id=opp, frequency_GHz=point['frequency_GHz'], voltage_V=point['voltage_V'],
                    duration_ms='20' if opp == 'L' else '10',
                    activity_power_W='1' if opp == 'L' else '2'))
    scenes = []
    for sid, keys in (('S1', ('A', 'B')), ('S2', ('A',))):
        copies = [dict(id=sid+'.'+key, shared_stage_id=key, request_id=sid+'.r') for key in keys]
        scenes.append(dict(id=sid, weight=('1' if sid == 'S1' else '0') if zero_weight else '1/2',
            stage_instances=copies,
            dependencies=[['S1.A', 'S1.B']] if chain and sid == 'S1' else [],
            requests=[dict(id=sid+'.r', release_ms='0', deadline_ms='400',
                           stage_instance_ids=[copy['id'] for copy in copies])],
            entry={'temperature_degC':['50']*4, 'unfinished_work': [],
                   'domain_opp': {did:'L' for did in p['domains']}},
            maximum_temperature_degC=['80']*4))
    return {'schema_version':'chapter3-input-v0.1',
            'id':'handwritten_mode_ledger_fixture', 'window_ms':'400', 'start_grid_ms':'5',
            'response_variant':'H', 'platform':p, 'stage_modes':modes, 'scenarios':scenes,
            'execution_rules':deepcopy(read(original(1))['execution_rules'])}


def assignments(instance):
    """32 complete labels with shared A unit; never creates starts or intervals."""
    for a1, b1, a2 in product(instance['stage_modes']['A'], instance['stage_modes']['B'],
                               instance['stage_modes']['A']):
        if a1['unit_id'] == a2['unit_id']:
            yield {'S1':{'S1.A':a1, 'S1.B':b1}, 'S2':{'S2.A':a2}}


def complete_condition(assignment):
    return {'by_scene': {sid:{copy:{'unit':mode['unit_id'], 'opp':mode['opp_id']}
                                   for copy,mode in copies.items()}
                         for sid,copies in assignment.items()}}


def compatible(assignment, partial):
    shared = partial.get('shared_units', {})
    for sid, copies in assignment.items():
        for copy, mode in copies.items():
            if mode['shared_stage_id'] in shared and mode['unit_id'] != shared[mode['shared_stage_id']]:
                return False
            required = partial.get('by_scene', {}).get(sid, {}).get(copy, {})
            if any(mode['unit_id' if key=='unit' else 'opp_id'] != value for key,value in required.items()):
                return False
    return True


def ledger(instance, assignment, *, chain=False):
    """Exact simple-mode ledger; lambda=0, base_L=0, no thermal claim.

    In the chain fixture H parts cannot overlap. In the independent fixture,
    same-H jobs on distinct cores have union equal to max(core H workload).
    L parts have zero baseline and may be placed separately within the ample
    abstract window; only these proven union measures are used, not a timeline.
    """
    total = F(0)
    pieces = {}
    for scene in instance['scenarios']:
        sid = scene['id']; modes = list(assignment[sid].values())
        direct = sum(F(m['duration_ms'])*F(m['activity_power_W'])/1000 for m in modes)
        loads = {unit:sum(F(m['duration_ms'])/1000 for m in modes
                         if m['unit_id']==unit and m['opp_id']=='H') for unit in ('CPU1','CPU2')}
        union = sum(loads.values()) if chain and sid=='S1' else max(loads.values())
        baseline = 2*union
        pieces[sid] = {'direct_J':str(direct), 'H_union_s':str(union),
                       'H_baseline_J':str(baseline), 'temperature_J':'0'}
        total += F(scene['weight'])*(direct+baseline)
    return total, pieces


class AlgebraTests(unittest.TestCase):
    def test_original_P0_C17_root_bounds_reproduce_exactly(self):
        facts = read(EXP/'results/mainline_mechanism_audit01/c17/facts.json')
        for index, expected in enumerate(facts['cases'], 1):
            with self.subTest(sample=index):
                bound = prepare(read(original(index))).bound()
                self.assertEqual(bound['status'], 'BOUND')
                self.assertEqual(F(bound['lower_bound_J']), F(expected['shared_consistent_proposed_LB_J']['exact']))
                self.assertEqual(F(bound['legacy_conditioned_lower_bound_J']), F(expected['old_L0_J']['exact']))
                DETAILS.append({'kind':'P0_root_reproduction','sample':index,
                                'lower_bound_J':bound['lower_bound_J'],
                                'not_a_new_thermal_or_search_result':True})

    def test_complete_mode_ledgers_cover_capacity_and_DAG_without_double_charge(self):
        for chain in (False, True):
            instance = toy(chain=chain); context = prepare(instance)
            count = 0
            for assignment in assignments(instance):
                bound = context.bound(complete_condition(assignment))
                upper, pieces = ledger(instance, assignment, chain=chain)
                self.assertLessEqual(F(bound['lower_bound_J']), upper,
                    (chain, complete_condition(assignment), bound, pieces))
                count += 1
            self.assertEqual(count, 32)
            DETAILS.append({'kind':'finite_mode_ledgers','chain':chain,
                            'mode_assignments':count,'no_starts_or_temperature_trajectory':True})

    def test_partial_relaxations_are_monotone_and_below_every_compatible_ledger(self):
        instance = toy(chain=True); context = prepare(instance)
        conditions = [{}, {'shared_units':{'A':'CPU1'}},
            {'shared_units':{'A':'CPU1'}, 'by_scene':{'S1':{'S1.A':{'opp':'H'}}}},
            {'shared_units':{'A':'CPU1'}, 'by_scene':{'S1':{
                'S1.A':{'opp':'H'}, 'S1.B':{'unit':'CPU2','opp':'H'}}}},
            {'shared_units':{'A':'CPU1'}, 'by_scene':{'S1':{
                'S1.A':{'opp':'H'}, 'S1.B':{'unit':'CPU2','opp':'H'}},
                'S2':{'S2.A':{'opp':'L'}}}}]
        previous = None
        for partial in conditions:
            bound = context.bound(partial); value = F(bound['lower_bound_J'])
            if previous is not None:
                self.assertGreaterEqual(value, previous)
            compatible_count = 0
            for assignment in assignments(instance):
                if compatible(assignment, partial):
                    self.assertLessEqual(value, ledger(instance, assignment, chain=True)[0])
                    compatible_count += 1
            self.assertGreater(compatible_count, 0)
            previous = value

    def test_shared_unit_does_not_force_shared_OPP(self):
        context = prepare(toy())
        condition = {'shared_units':{'A':'CPU1'}, 'by_scene':{
            'S1':{'S1.A':{'opp':'H'}}, 'S2':{'S2.A':{'opp':'L'}}}}
        self.assertEqual(context.bound(condition)['status'], 'BOUND')
        with self.assertRaises(BoundError):
            context.bound({'by_scene':{'S1':{'S1.A':{'unit':'CPU1'}},
                                      'S2':{'S2.A':{'unit':'CPU2'}}}})
        # Repetition within one scene is the same shared-deployment contract,
        # even without another distinct scene carrying that identity.
        repeated = toy()
        repeated['scenarios'] = [repeated['scenarios'][0]]
        scene = repeated['scenarios'][0]
        scene['weight'] = '1'
        scene['stage_instances'].append({'id':'S1.A2','shared_stage_id':'A','request_id':'S1.r2'})
        scene['requests'].append({'id':'S1.r2','release_ms':'0','deadline_ms':'400',
                                   'stage_instance_ids':['S1.A2']})
        repeated_context = prepare(repeated)
        self.assertEqual(repeated_context.bound({'shared_units':{'A':'CPU1'},'by_scene':{
            'S1':{'S1.A':{'opp':'H'},'S1.A2':{'opp':'L'}}}})['status'], 'BOUND')
        with self.assertRaises(BoundError):
            repeated_context.bound({'by_scene':{'S1':{
                'S1.A':{'unit':'CPU1'},'S1.A2':{'unit':'CPU2'}}}})

    def test_zero_weight_scene_remains_legal_support_and_shared_constraint(self):
        context = prepare(toy(zero_weight=True))
        self.assertEqual(context.bound()['status'], 'BOUND')
        with self.assertRaises(BoundError):
            context.bound({'by_scene':{'S2':{'S2.A':{'unit':'GPU0'}}}})
        with self.assertRaises(BoundError):
            context.bound({'by_scene':{'S1':{'S1.A':{'unit':'CPU1'}},
                                      'S2':{'S2.A':{'unit':'CPU2'}}}})

    def test_unknown_unsupported_or_contradictory_conditions_fail_closed(self):
        context = prepare(toy())
        bad = [{'TYPO':{}}, {'shared_units':{'missing':'CPU1'}},
               {'by_scene':{'missing':{}}}, {'by_scene':{'S1':{'missing':{}}}},
               {'by_scene':{'S1':{'S1.A':{'opp':'ULTRA'}}}},
               {'by_scene':{'S1':{'S1.A':{'unit':'GPU0'}}}},
               {'by_scene':{'S1':{'S1.A':{'start_ms':'0'}}}},
               {'shared_units':{'A':'CPU1'},'by_scene':{'S2':{'S2.A':{'unit':'CPU2'}}}}]
        for condition in bad:
            with self.subTest(condition=condition), self.assertRaises(BoundError):
                context.bound(condition)
        for field in ('shared_deployment_scope', 'scenario_entry'):
            changed = toy()
            changed['execution_rules'][field] = 'unsupported_scope_or_entry'
            with self.subTest(rule=field), self.assertRaises(BoundError):
                prepare(changed)

    def test_exact_comparison_ties_and_tiny_differences_never_authorize_pruning(self):
        bound = prepare(toy(chain=True)).bound({'by_scene':{
            'S1':{'S1.A':{'opp':'H'}, 'S1.B':{'opp':'H'}},
            'S2':{'S2.A':{'opp':'H'}}}})
        value = F(bound['lower_bound_J']); epsilon = F(1,10**90)
        for upper, expected in ((value,'TIE'), (value+epsilon,'LOWER'), (value-epsilon,'HIGHER')):
            compared = compare_exact_bound(bound, str(upper), bound['input_sha256'])
            self.assertEqual(compared['comparison'], expected)
            self.assertFalse(compared['pruning_authorized'])
            self.assertEqual(F(compared['difference_J']), value-upper)
        for upper, identity in ((float(value),bound['input_sha256']),
                                (True,bound['input_sha256']), ('-1',bound['input_sha256']),
                                (str(value),'0'*64)):
            with self.subTest(upper=upper), self.assertRaises(BoundError):
                compare_exact_bound(bound, upper, identity)

    def test_no_upper_or_plain_dictionary_cannot_prune(self):
        bound = prepare(toy()).bound()
        decision = pruning_decision(bound)
        self.assertFalse(decision['prune'])
        self.assertEqual(decision['decision'], 'NO_CERTIFIED_UPPER_BOUND')
        with self.assertRaises(BoundError):
            pruning_decision(dict(bound))
        tampered = prepare(toy()).bound()
        tampered['lower_bound_J'] = '999'
        with self.assertRaises(BoundError):
            pruning_decision(tampered)
        with self.assertRaises(BoundError):
            pruning_decision(bound, {'state':'SAFE','input_sha256':bound['input_sha256'],
                                     'upper_bound_J':'0','complete':True})

    def test_real_P0_reference_is_input_bound_and_prunes_only_an_expensive_condition(self):
        instance = read(original(1)); context = prepare(instance)
        path = original(1, 'anchor_linked4', 'result.json')
        post = path.parent/'postcheck.json'
        # Both files are original P0 evidence; no synthetic SAFE or thermal U.
        READ_HASHES[str(post.relative_to(REPO)).replace('\\','/')] = sha(post)
        READ_HASHES[str(path.relative_to(REPO)).replace('\\','/')] = sha(path)
        reference = context.reference_from_archive(path, post)
        self.assertFalse(pruning_decision(context.bound(), reference)['prune'])
        condition = {'by_scene':{scene['id']:{stage['id']:{'unit':'NPU0','opp':'H'}
            for stage in scene['stage_instances'] if stage['shared_stage_id']=='A.main'}
            for scene in instance['scenarios']}}
        expensive = context.bound(condition)
        decision = pruning_decision(expensive, reference)
        self.assertTrue(decision['prune'], decision)
        self.assertEqual(decision['decision'], 'PRUNE_ENERGY')
        self.assertFalse(decision['original_domain_infeasible'])
        self.assertTrue(decision['posthoc'])
        DETAILS.append({'kind':'actual_archive_comparison','condition':condition,
                        'conditional_bound_J':expensive['lower_bound_J'],
                        'decision':decision,'no_search_prune_executed':True})
        other = deepcopy(instance); other['id'] += '_different_input'
        with self.assertRaises(BoundError):
            prepare(other).reference_from_archive(path, post)
        # A copied or invented result outside the original archive is refused.
        fake = OUT/'fake_archived_safe.json'
        fake.write_text('{"state":"SAFE","complete":true}',encoding='utf8')
        with self.assertRaises(BoundError):
            context.reference_from_archive(fake, post)
        # Negative receipt-only injections never overwrite archive files or
        # invent an accepted thermal certificate. They must be rejected.
        original_read_bytes = Path.read_bytes
        for changed in ('incomplete_scene', 'formed_at_cutoff'):
            def injected_read_bytes(file):
                data = original_read_bytes(file)
                target = post if changed == 'incomplete_scene' else path
                if file.resolve() == target.resolve():
                    value = json.loads(data.decode('utf-8-sig'))
                    if changed == 'incomplete_scene':
                        value['scenes'][next(iter(value['scenes']))]['complete'] = False
                    elif value.get('committed_safe_snapshot'):
                        value['committed_safe_snapshot']['committed_at_s'] = 300
                    else:
                        value['evaluation']['completed_at_elapsed_s'] = 300
                    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf8')
                return data
            with self.subTest(negative_receipt=changed), \
                 patch.object(Path, 'read_bytes', injected_read_bytes), \
                 self.assertRaises(BoundError):
                context.reference_from_archive(path, post)


class GuardViolation(KeyboardInterrupt):
    pass


def run(out):
    global OUT
    OUT = Path(out).resolve(); OUT.mkdir(parents=True, exist_ok=False)
    source = [Path(__file__), Path(__file__).with_name('bounds.py')]
    before = {str(p.relative_to(REPO)).replace('\\','/'):sha(p) for p in source}
    counts = {'scientific_import':0,'scientific_code_entry':0,'process_launch':0}
    prohibited_imports = {'numpy','scipy','milp','thermal','matlab_bridge','milp_coefficients',
                         'initial_point','initial_schedule','scene_adapter','inputs','partial_bounds'}
    loaded = [name for name in sys.modules if name.split('.')[0] in prohibited_imports]
    functions = {'milp.py':{'build_model','Model.__init__','evaluate_model_candidate'},
        'thermal.py':{'evaluate_candidate','evaluate_piecewise'},
        'matlab_bridge.py':{'MatlabSession.__init__','MatlabSession.solve'},
        'initial_point.py':{'prepare_initial_witness','complete_initial_point','_propose_vector'},
        'inputs.py':{'build_instance','expand_options'},
        'augmented_payload.py':{'build_augmented_payload'},
        'augmented_method.py':{'build_live_augmented_payload'},
        'subprocess.py':{'Popen.__init__','run','check_output'}}
    active = {'value':True}

    def stop(kind, message):
        counts[kind] += 1
        raise GuardViolation(message)

    def audit(event,args):
        if not active['value']:
            return
        if event=='import' and str(args[0]).split('.')[0] in prohibited_imports:
            stop('scientific_import',str(args[0]))
        if event in ('subprocess.Popen','os.system','os.startfile','os.posix_spawn'):
            stop('process_launch',event)

    def profile(frame,event,arg):
        if event=='call':
            filename=Path(frame.f_code.co_filename).name
            name=getattr(frame.f_code,'co_qualname',frame.f_code.co_name)
            if name in functions.get(filename,set()) or frame.f_code.co_name in functions.get(filename,set()):
                stop('scientific_code_entry',filename+':'+name)

    previous=sys.getprofile();sys.addaudithook(audit);log=io.StringIO()
    try:
        sys.setprofile(profile)
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(AlgebraTests)
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    except GuardViolation as error:
        result=unittest.TestResult();result.errors.append(('guard',str(error)))
        log.write('\nGUARD_ABORT: '+str(error)+'\n')
    finally:
        sys.setprofile(previous);active['value']=False
    after={name:sha(REPO/name) for name in before}
    files_after={name:sha(REPO/name) for name in READ_HASHES}
    checks={'protocol':'K170-conditional-bound-algebra-only-precheck-v1',
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'test_successful':result.wasSuccessful(),'source_before_sha256':before,
        'source_after_sha256':after,'source_unchanged':before==after,
        'original_files_before_sha256':READ_HASHES,'original_files_after_sha256':files_after,
        'original_files_unchanged':READ_HASHES==files_after,
        'guard':{'blocked_attempts':counts,'all_attempts_zero':not any(counts.values()),
                 'scientific_modules_loaded':loaded,'model_or_schedule_builds':0,
                 'solver_calls':0,'thermal_or_candidate_evaluations':0,'research_calls':0},
        'details':DETAILS,
        'scope':'Finite mode-label algebra, exact ledgers and genuine existing receipt checks only; no new schedule, heat or search; no method-speed or optimality claim'}
    checks['passed']=(checks['test_successful'] and checks['source_unchanged']
        and checks['original_files_unchanged'] and not loaded
        and checks['guard']['all_attempts_zero'])
    (OUT/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    (OUT/'unittest.txt').write_text(log.getvalue(),encoding='utf8')
    print(json.dumps({'passed':checks['passed'],'tests':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),
        'guard_zero':checks['guard']['all_attempts_zero'],'checks':str(OUT/'checks.json')}))
    return 0 if checks['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(run(parser.parse_args().out))
