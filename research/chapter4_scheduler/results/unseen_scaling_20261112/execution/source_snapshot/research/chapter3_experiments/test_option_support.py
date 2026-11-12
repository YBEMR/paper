"""Finite Cartesian correctness and full thermal checks, never a solver run.

Fixture mode/start restrictions are declared only for these unit tests. Original
research inputs, physical platform parameters and the thermal kernel are read
without modification. Every legal complete candidate in each fixture is
evaluated on both sides; thermal comparisons do not use auxiliary vectors.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

import milp
import option_support as support
from inputs import expand_options, load_config
from run_milp_precheck import candidate_key, exact_row_residuals, select_fixture
from schedules import validate_schedule
from thermal import Budget, Exhausted

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = '052c0b01c9a840c2b5b6ff8018afcaf08654a24a'
FLAGS = dict(fix_late_options=True, aggregate_opp_locks=True,
    relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True,
    prefilter_deadlines=True, cumulative_precedence=True)
RECORDS = {'scope': 'bounded correctness fixtures; no research performance comparison',
    'maximum_complete_candidate_evaluations': 64, 'maximum_wall_s': 120,
    'maximum_fixture_cartesian_candidates': 96, 'thermal_calls': 0,
    'solver_calls': 0, 'original_R1_models': 0, 'fixtures': {}, 'checks': {}}
OUTPUT = None
START = None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), default=str).encode()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str); stream.write('\n')


def base():
    return json.loads((HERE/'results/base_long_diagnostic01/input_instance.json').read_text())


def physical_fixture(name):
    original = base(); ab, ac = [s['id'] for s in original['scenarios']]
    specs = {
        'chain': ({ab: ['A.pre', 'A.main']}, {'A.pre': [0, 5], 'A.main': [10, 15]},
            {'A.pre': [('CPU1', 'H'), ('CPU1', 'M')], 'A.main': [('NPU0', 'H')]}),
        'parallel': ({ab: ['A.pre', 'B.pre']}, {'A.pre': [0], 'B.pre': [0, 15]},
            {'A.pre': [('CPU1', 'H'), ('CPU1', 'M')], 'B.pre': [('CPU2', 'H'), ('CPU2', 'M')]}),
        'shared_modes': ({ab: ['A.pre'], ac: ['A.pre']}, {'A.pre': [0]},
            {'A.pre': [('CPU1', 'H'), ('CPU1', 'M'), ('CPU2', 'H')]}),
        'interaction': ({ab: ['A.pre', 'A.main'], ac: ['A.pre']},
            {'A.pre': [0, 5], 'A.main': [5]},
            {'A.pre': [('CPU1', 'H'), ('CPU2', 'H')], 'A.main': [('NPU0', 'H')]}),
    }
    selected, starts, modes = specs[name]
    case, declared = select_fixture(original, 'option_support_'+name, selected, starts)
    case['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
        'by_scene_stage_ms': declared}
    for shared, choices in modes.items():
        case['stage_modes'][shared] = [m for m in case['stage_modes'][shared]
            if (m['unit_id'], m['opp_id']) in choices]
    if name == 'shared_modes':
        stage = case['scenarios'][1]['stage_instances'][0]['id']
        declared[ac][stage] = ['15']
    if name == 'interaction':
        # Explicit test-only rational timings; both sides see identical values.
        for shared, values in case['stage_modes'].items():
            for mode in values:
                mode['duration_ms'] = ('3/2' if mode['unit_id']=='CPU1' else '8') if shared=='A.pre' else '2'
                mode['activity_energy_J'] = str(F(mode['activity_power_W'])*F(mode['duration_ms'])/1000)
        case['fixture_scope'] += '; hand-declared test durations3/2,8,2ms'
    return case


def candidates(case, options):
    groups = [(sc['id'], st['id']) for sc in case['scenarios'] for st in sc['stage_instances']]
    choices = [[o for o in options if (o['scenario_id'], o['stage_instance_id']) == group] for group in groups]
    for selected in product(*choices):
        candidate = {'scenes': {sc['id']: [] for sc in case['scenarios']}}
        for row in selected:
            candidate['scenes'][row['scenario_id']].append({'stage_id': row['stage_instance_id'],
                'unit': row['unit_id'], 'opp': row['opp_id'], 'start_ms': row['start_ms']})
        yield candidate


def legal_candidates(case, options):
    all_candidates = list(candidates(case, options))
    return all_candidates, {candidate_key(c): c for c in all_candidates
        if validate_schedule(case, c)['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED'}


def scientific_view(value):
    excluded = {'elapsed_s', 'completed_at_elapsed_s', 'formed_at_elapsed_s'}
    if isinstance(value, dict): return {k: scientific_view(v) for k, v in value.items() if k not in excluded}
    if isinstance(value, list): return [scientific_view(v) for v in value]
    return value


def evaluate(model, candidate, name, side, ordinal):
    if RECORDS['thermal_calls'] >= 64: raise AssertionError('FROZEN_THERMAL_CALL_CAP')
    remaining = 120-(time.monotonic()-START)
    if remaining <= 0: raise AssertionError('FROZEN_TEST_TIME_CAP')
    RECORDS['thermal_calls'] += 1
    receipt = milp.evaluate_model_candidate(model, candidate, None,
        Budget(seconds=min(10, remaining)))
    if OUTPUT is not None: save(OUTPUT/f'{name}_{ordinal:03d}_{side}_thermal.json', receipt)
    return receipt


def pure_instance(groups, edges=()):
    scenes = {}
    for sid, stage, shared in groups:
        scenes.setdefault(sid, {'id': sid, 'stage_instances': [], 'dependencies': []})['stage_instances'].append(
            {'id': stage, 'shared_stage_id': shared})
    for sid, before, after in edges: scenes[sid]['dependencies'].append([before, after])
    return {'id': 'fixture_pure_support', 'scenarios': list(scenes.values())}


def option(oid, sid, stage, unit, start, end):
    return {'option_id': oid, 'scenario_id': sid, 'stage_instance_id': stage,
        'unit_id': unit, 'start_ms': str(start), 'end_ms': str(end)}


def interaction_data():
    case = pure_instance([('a','s','S'), ('a','t','T'), ('b','s','S'), ('b','v','V')],
        [('a','s','t'), ('b','s','v')])
    options = [option('a1','a','s','CPU1',0,2), option('a2','a','s','CPU2',0,7),
        option('at','a','t','NPU0',2,3), option('b1','b','s','CPU1',10,12),
        option('b2','b','s','CPU2',0,7), option('bv7','b','v','GPU0',7,8),
        option('bv12','b','v','GPU0',12,13)]
    return case, options


class OptionSupportTests(unittest.TestCase):
    def test_bidirectional_equalities_and_fractional_times(self):
        case = pure_instance([('a','p','P'),('a','q','Q')], [('a','p','q')])
        opts = [option('p0','a','p','CPU1',0,'3/2'), option('p5','a','p','CPU1',5,'13/2'),
            option('q0','a','q','NPU0',0,1), option('qeq','a','q','NPU0','3/2','5/2'),
            option('q5','a','q','NPU0',5,6)]
        old = deepcopy((case, opts)); kept, proof = support.propagate_option_support(case, opts)
        self.assertEqual([o['option_id'] for o in kept], ['p0','qeq','q5'])
        self.assertEqual(set(proof['deletion_rule_counts']), {'predecessor_support','successor_support'})
        self.assertTrue(support.verify_option_support_report(case, opts, kept, proof)['passed'])
        self.assertEqual((case, opts), old)

    def test_dependency_shared_dependency_requires_multiple_snapshots(self):
        case, opts = interaction_data(); kept, proof = support.propagate_option_support(case, opts)
        self.assertEqual([o['option_id'] for o in kept], ['a1','at','b1','bv12'])
        self.assertGreaterEqual(len(proof['rounds']),4)
        self.assertEqual(proof['rounds'][-1]['deleted_count'],0)
        self.assertEqual(proof['logical_feasibility'],'NOT_PROVEN')
        self.assertTrue(support.verify_option_support_report(case, opts, kept, proof)['passed'])
        RECORDS['checks']['multi_round'] = proof

    def test_same_scene_copies_share_device_not_time(self):
        case = pure_instance([('a','copy1','S'),('a','copy2','S')])
        opts = [option('x','a','copy1','CPU1',0,1),option('y','a','copy1','CPU2',0,1),
            option('z','a','copy2','CPU1',15,17)]
        kept, proof = support.propagate_option_support(case, opts)
        self.assertEqual([o['option_id'] for o in kept],['x','z'])
        self.assertTrue(support.verify_option_support_report(case,opts,kept,proof)['passed'])

    def test_empty_domain_retains_occurrences_and_propagates(self):
        case = pure_instance([('a','p','P'),('a','q','Q'),('b','q','Q')],[('a','p','q')])
        opts = [option('p','a','p','CPU1',0,1),option('bq','b','q','CPU1',0,1)]
        kept, proof = support.propagate_option_support(case,opts)
        self.assertEqual(kept,[]); self.assertEqual(len(proof['empty_domains']),3)
        self.assertEqual(proof['logical_feasibility'],'INFEASIBLE_BY_EMPTY_OPTION_DOMAIN')
        self.assertEqual(len(case['scenarios'][0]['stage_instances']),2)
        self.assertTrue(support.verify_option_support_report(case,opts,kept,proof)['passed'])

    def test_bad_proofs_and_identity_drift_are_rejected(self):
        case, opts = interaction_data(); kept, proof = support.propagate_option_support(case, opts)
        changes = [lambda p:p['rounds'][0].update(round=2),
            lambda p:p['rounds'][0].update(before_domain_sha256='bad'),
            lambda p:p['rounds'][0]['deletions'][0].update(maximum_successor_start_ms='99'),
            lambda p:p['rounds'][0]['deletions'][0].update(rule='unproven_resource_pair'),
            lambda p:p['rounds'][0]['deletions'].clear(),
            lambda p:p['rounds'].pop(), lambda p:p.update(retained_options_sha256='bad')]
        for change in changes:
            wrong = deepcopy(proof); change(wrong)
            with self.subTest(change=repr(change)), self.assertRaises((ValueError,KeyError)):
                support.verify_option_support_report(case,opts,kept,wrong)
        wrong = deepcopy(opts); wrong[0]['end_ms']='3'
        with self.assertRaises(ValueError):support.verify_option_support_report(case,wrong,kept,proof)

    def test_fake_fixed_point_cannot_omit_deletions(self):
        case, opts = interaction_data(); _, proof = support.propagate_option_support(case,opts)
        wrong = deepcopy(proof); h=wrong['initial_domain_sha256']
        wrong.update(rounds=[{'round':1,'before_domain_sha256':h,'after_domain_sha256':h,
            'deletions':[],'deleted_count':0,'empty_domains_after':[]}],
            final_domain_sha256=h,retained_options_sha256=digest(opts),retained_option_count=len(opts),
            removed_option_count=0,round_count_including_fixed_point_check=1,deletion_rule_counts={})
        with self.assertRaises(ValueError):support.verify_option_support_report(case,opts,opts,wrong)

    def test_budget_exception_returns_no_success_or_mutation(self):
        case, opts = interaction_data(); original=deepcopy((case,opts))
        class Stop:
            calls=0
            def check(self):
                self.calls+=1
                if self.calls>=4:raise Exhausted('fixture_support_interrupted')
        with self.assertRaises(Exhausted):support.propagate_option_support(case,opts,Stop())
        self.assertEqual((case,opts),original)

    def test_malformed_catalog_rejected(self):
        case,opts=interaction_data()
        for change in [lambda o:o.append(deepcopy(o[0])),lambda o:o[0].update(start_ms=0.0),
            lambda o:o[0].update(end_ms='0'),lambda o:o[0].update(stage_instance_id='unknown')]:
            wrong=deepcopy(opts);change(wrong)
            with self.subTest(change=repr(change)),self.assertRaises((ValueError,TypeError)):
                support.propagate_option_support(case,wrong)

    def test_default_false_matches_old_head_and_boolean_guard(self):
        case=physical_fixture('chain');config=load_config()
        namespace={'__name__':'support_baseline_head','__file__':str(HERE/'milp.py')}
        old_source=subprocess.check_output(['git','show',REFERENCE+':research/chapter3_experiments/milp.py'],cwd=REPO)
        exec(compile(old_source,REFERENCE+':milp.py','exec'),namespace)
        baseline=namespace['build_model'](case,config,include_physics=False,budget=Budget(seconds=30),**FLAGS)
        current=milp.build_model(case,config,include_physics=False,budget=Budget(seconds=30),**FLAGS)
        explicit=milp.build_model(case,config,include_physics=False,budget=Budget(seconds=30),propagate_support=False,**FLAGS)
        for model in (current,explicit):
            for key in ('names','rows','options','option_vars','shared','scenes','c','lb','ub','bounds','integer','logical_binary','formulation'):
                self.assertEqual(getattr(model,key),getattr(baseline,key),key)
            left,right=baseline.as_solver_dict(),model.as_solver_dict()
            for key in ('c','b','beq','lb','ub','intcon'):self.assertEqual(left[key].tobytes(),right[key].tobytes(),key)
            for key in ('A','Aeq'):
                a,b=left[key].tocsr(),right[key].tocsr();self.assertEqual(a.shape,b.shape)
                for field in ('data','indices','indptr'):self.assertEqual(getattr(a,field).tobytes(),getattr(b,field).tobytes())
        with patch.object(milp,'Model') as constructor:
            for value in (0,1,None,'false',np.bool_(False),[]):
                with self.subTest(value=repr(value)),self.assertRaises(ValueError):
                    milp.build_model(case,config,propagate_support=value)
            constructor.assert_not_called()
        RECORDS['checks']['default_false']={'old_head':REFERENCE,'old_source_sha256':hashlib.sha256(old_source).hexdigest(),'solver_arrays_and_structure_equal':True,'research_models':0}

    def test_all_cartesian_legal_schedules_and_full_thermal_projections(self):
        total_cartesian=0;total_legal=0
        for name in ('chain','parallel','shared_modes','interaction'):
            case=physical_fixture(name);config=load_config();saved=deepcopy(case)
            opts=expand_options(case,config)
            kept,proof=support.propagate_option_support(case,opts)
            self.assertEqual(case,saved)
            all_before,before=legal_candidates(case,opts);all_after,after=legal_candidates(case,kept)
            self.assertTrue(before);self.assertEqual(set(before),set(after));total_cartesian+=len(all_before);total_legal+=len(before)
            self.assertLessEqual(len(all_before),32)
            physical=name=='chain'
            old=milp.build_model(case,config,include_physics=physical,budget=Budget(seconds=60),propagate_support=False,**FLAGS)
            new=milp.build_model(case,config,include_physics=physical,budget=Budget(seconds=60),propagate_support=True,**FLAGS)
            self.assertEqual(old.instance,new.instance);self.assertEqual(old.instance,case)
            self.assertEqual([o['option_id']for o in new.options],[o['option_id']for o in kept])
            self.assertTrue(support.verify_option_support_report(case,opts,kept,proof)['passed'])
            if name=='interaction':self.assertGreater(proof['removed_option_count'],0)
            if name=='parallel':self.assertEqual(len(kept),len(opts))  # no resource-pair support
            if name=='shared_modes':
                self.assertTrue(any(len({row['opp']for rows in c['scenes'].values()for row in rows})>1 for c in before.values()))
                self.assertTrue(any(len({row['start_ms']for rows in c['scenes'].values()for row in rows})>1 for c in before.values()))
            candidates_record=[]
            for ordinal,(key,candidate) in enumerate(sorted(before.items()),1):
                left=evaluate(old,candidate,name,'OFF',ordinal);right=evaluate(new,candidate,name,'ON',ordinal)
                self.assertEqual(scientific_view(left),scientific_view(right))
                self.assertEqual(left['state'],'SAFE')
                self.assertEqual(len(left['scenes']),len(case['scenarios']))
                self.assertTrue(all(F(v['covered_until_s'])==F(case['window_ms'])/1000 for v in left['scenes'].values()))
                row_residuals=[]
                if physical:
                    for model in (old,new):
                        vector=milp.lift_candidate(model,candidate);residuals=exact_row_residuals(model,vector)
                        maximum=max(residuals,default=F(0));self.assertLessEqual(maximum,F(2,100000000))
                        row_residuals.append(str(maximum))
                candidates_record.append({'candidate':candidate,'state':left['state'],'weighted_energy_J':left['weighted_energy_J'],
                    'peaks_by_scene':{sid:r['peaks_degC']for sid,r in left['scenes'].items()},'physical_row_max_residuals':row_residuals})
            RECORDS['fixtures'][name]={'input':case,'original_options':len(opts),'retained_options':len(kept),
                'cartesian_before':len(all_before),'cartesian_after':len(all_after),'complete_legal_schedules':len(before),
                'exact_legal_set_equal':True,'all_complete_thermal_scientific_fields_equal':True,'include_physics_models':physical,
                'models':[old.summary(),new.summary()],'deletion_proof':proof,'legal_candidates':candidates_record}
        self.assertLessEqual(total_cartesian,96)
        RECORDS['cartesian_candidates_total']=total_cartesian;RECORDS['legal_candidates_total']=total_legal

    def test_nonempty_support_does_not_claim_resource_feasibility(self):
        case=physical_fixture('parallel')
        for shared in case['stage_modes']:
            mode=deepcopy(next(m for m in base()['stage_modes'][shared]if m['unit_id']=='CPU1'and m['opp_id']=='H'))
            case['stage_modes'][shared]=[mode]
        for stages in case['start_domain']['by_scene_stage_ms'].values():
            for stage in stages:stages[stage]=['0']
        opts=expand_options(case,load_config());kept,proof=support.propagate_option_support(case,opts)
        self.assertEqual(kept,opts);self.assertEqual(proof['logical_feasibility'],'NOT_PROVEN')
        _,legal=legal_candidates(case,kept);self.assertFalse(legal)

    def test_empty_model_has_contradictory_onehot_and_does_not_drop_stage(self):
        case=physical_fixture('chain');sid=case['scenarios'][0]['id']
        for stage in case['scenarios'][0]['stage_instances']:
            case['start_domain']['by_scene_stage_ms'][sid][stage['id']]=['0']
        model=milp.build_model(case,load_config(),include_physics=False,budget=Budget(seconds=30),propagate_support=True,**FLAGS)
        self.assertEqual(len(model.instance['scenarios'][0]['stage_instances']),2)
        self.assertEqual(model.options,[])
        self.assertTrue(any(not row['coef']and row['rhs']<0 for row in model.rows if row['tag'].startswith('stage_unique')))


def main():
    global OUTPUT,START
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    OUTPUT=args.output.resolve();OUTPUT.mkdir(parents=True,exist_ok=False);START=time.monotonic();started=datetime.now(timezone.utc).isoformat()
    save(OUTPUT/'started.json',{'utc':started,'argv':sys.argv,'cwd':str(REPO),'caps':{k:RECORDS[k]for k in ['maximum_complete_candidate_evaluations','maximum_wall_s','maximum_fixture_cartesian_candidates']}})
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OptionSupportTests))
    RECORDS.update(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),wall_s=time.monotonic()-START,
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),
        source_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [HERE/'option_support.py',HERE/'milp.py',Path(__file__).resolve(),HERE/'schedules.py',HERE/'thermal.py']})
    save(OUTPUT/'results.json',RECORDS)
    raise SystemExit(0 if result.wasSuccessful()else 1)


if __name__=='__main__':main()
