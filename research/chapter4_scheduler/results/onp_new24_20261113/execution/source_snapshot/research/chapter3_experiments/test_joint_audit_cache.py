"""Independent cache boundary checks and old/new ON small-domain comparison.

No full R1 model or solver is executed. The physical fixture is frozen by the
unchanged joint-state suite; additional old-ON evaluations reuse its new-ON
receipts, keeping the complete validation batch below 64 thermal calls.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
BASE='fe6216afcd0e8d94742adbc0ff62d70651dd60ba'
REFERENCE_SHA='43e259d03ce5c65e38a9fb1148fdd45acfecb3b4fb132e1f6d14ea34963e65b4'
now=lambda:datetime.now(timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())


def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,default=str);stream.write('\n')


def freeze(output,legacy,reuse=None):
    output.mkdir(parents=True,exist_ok=False)
    baseline=subprocess.check_output(['git','show',BASE+':research/chapter3_experiments/milp.py'],
        cwd='/workspace/paper_publish_autol_lp_20261111')
    assert hashlib.sha256(baseline).hexdigest()==REFERENCE_SHA
    (output/'baseline_milp.py.txt').write_bytes(baseline)
    paths=[HERE/'milp.py',HERE/'joint_state_support.py',HERE/'test_joint_state_support.py',
           HERE/'test_option_support_structural.py',Path(__file__).resolve()]
    reuse_record=None
    if reuse is not None:
        reuse=reuse.resolve();old_plan=read(reuse/'plan.json')
        prior_fixture=Path(old_plan['legacy_joint_output'])
        assert sha(legacy/'fixture.json')==sha(prior_fixture/'fixture.json')
        assert sha(legacy/'config.json')==sha(prior_fixture/'config.json')
        assert sha(reuse/'baseline_milp.py.txt')==REFERENCE_SHA
        receipts=list(reuse.glob('physical_*_OLD_ON.json'));assert len(receipts)==12
        reuse_record=dict(directory=str(reuse),baseline_commit=BASE,
            baseline_source_sha256=REFERENCE_SHA,fixture_sha256=sha(legacy/'fixture.json'),
            config_sha256=sha(legacy/'config.json'),receipt_sha256={p.name:sha(p) for p in receipts})
    save(output/'plan.json',dict(frozen_utc=now(),baseline_commit=BASE,
        baseline_milp_sha256=REFERENCE_SHA,legacy_joint_output=str(legacy.resolve()),
        source_sha256={str(p.relative_to(REPO)):sha(p) for p in paths},
        maximum_extra_thermal_calls=0 if reuse_record else 12,maximum_whole_batch_thermal_calls=64,
        physical_calls_from_legacy_suite=24,expected_whole_batch_thermal_calls=24 if reuse_record else 36,
        reused_baseline_physical=reuse_record,
        total_batch_budget_s=240,per_thermal_call_s=10,full_R1_builds=0,solver_calls=0,
        synthetic_mutation_scope='Audit-only copies/callables; no research input or physical fixture altered'))


def audit_science(value):
    keys=['state','checked_rows','gate_fixed_value','maximum_residual','minimum_slack','exact_binary64_box']
    return dict(states_checked=value['states_checked'],rows_checked=value['rows_checked'],
        states=[{key:r[key] for key in keys if key in r} for r in value.get('states',[])])


def run(output):
    plan=read(output/'plan.json')
    for name,digest in plan['source_sha256'].items():assert sha(REPO/name)==digest,name
    import milp,joint_state_support
    import scipy.optimize as optimize
    import test_joint_state_support as fixture
    from thermal import Budget
    def forbidden(*args,**kwargs):raise AssertionError('PROHIBITED_SOLVER_CALL')
    optimize.linprog=forbidden;optimize.milp=forbidden
    start=time.monotonic();started=now();deadline=float(os.environ.get('PRUNING_OPT_VALIDATION_DEADLINE',start+240))
    budget=Budget(seconds=max(0,deadline-start))
    legacy=Path(plan['legacy_joint_output']);prior=read(legacy/'results.json')
    assert prior['passed'] and prior['thermal_calls']==24
    case=read(legacy/'fixture.json');config=read(legacy/'config.json')
    flags=read(fixture.ARCH/'plan.json')['baseline_flags'];flags['propagate_support']=True
    namespace={'__name__':'gate_audit_baseline','__file__':str(output/'baseline_milp.py.txt')}
    baseline=(output/'baseline_milp.py.txt').read_bytes();assert hashlib.sha256(baseline).hexdigest()==REFERENCE_SHA
    exec(compile(baseline,str(output/'baseline_milp.py.txt'),'exec'),namespace)
    record=dict(started_utc=started,extra_thermal_calls=0,fixture_model_builds=0,full_R1_builds=0,
                solver_calls=0,checks={},audit_snapshots={})

    class Tests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.models=[]
            for build in [namespace['build_model'],milp.build_model]:
                budget.check();record['fixture_model_builds']+=1
                cls.models.append(build(case,config,budget=budget,prune_joint_states=True,**flags))
            cls.old,cls.new=cls.models
            selected=None
            for sid,meta in cls.new.scenes.items():
                for interval,states in enumerate(meta['candidate_states']):
                    deleted=[state for state in states if state not in set(meta['states'][interval])]
                    if deleted:
                        selected=(meta['theta'][interval]+meta['q'][interval],meta['theta'][interval+1],
                                  meta['energy'][interval],deleted,meta['events'][interval+1]-meta['events'][interval])
                        break
                if selected:break
            assert selected is not None
            cls.args=selected

        def fresh(self):
            model=self.new
            return SimpleNamespace(instance=deepcopy(model.instance),input_sha256=model.input_sha256,
                budget=budget,names=list(model.names),bounds=list(model.bounds),lb=list(model.lb),ub=list(model.ub),
                coefficients=model.coefficients,preprocessing={'joint_state_pruning':{}})

        def audit(self,model,args=None):
            budget.check();return milp._audit_joint_state_gate_off(model,*(self.args if args is None else args))

        def test_01_old_new_entire_numeric_model_equal(self):
            for attr in ['names','bounds','c','lb','ub','integer','logical_binary','options','rows']:
                self.assertEqual(getattr(self.old,attr),getattr(self.new,attr),attr)
            for sid in self.old.scenes:
                for key in ['events','states','candidate_states']:
                    self.assertEqual(self.old.scenes[sid][key],self.new.scenes[sid][key],(sid,key))
            self.assertEqual(self.old.energy_bound_certificates,self.new.energy_bound_certificates)
            old_removed={sid:[r['states'] for r in sc['interval_reports']]
                for sid,sc in self.old.preprocessing['joint_state_pruning']['scenes'].items()}
            new_removed={sid:[r['states'] for r in sc['interval_reports']]
                for sid,sc in self.new.preprocessing['joint_state_pruning']['scenes'].items()}
            self.assertEqual(old_removed,new_removed)
            record['checks']['entire_numeric_model_and_state_certificates_equal']=True

        def test_02_old_on_complete_physical_receipts_match_existing_new_on(self):
            complete=read(legacy/'complete_candidate_sets.json');before=[];after=[];projections=0
            for ordinal,item in enumerate(complete['candidates']):
                candidate=item['candidate'];legal,selected=fixture.independent_legal(case,candidate)
                self.assertEqual(legal,item['independent_legal'])
                if not legal:continue
                before.append(fixture.identity(candidate))
                for sid,meta in self.old.scenes.items():
                    for interval,left in enumerate(meta['events'][:-1]):
                        state=fixture.independent_state(case,selected,sid,left);projections+=1
                        self.assertIn(state,self.old.scenes[sid]['states'][interval]);self.assertIn(state,self.new.scenes[sid]['states'][interval])
                after.append(fixture.identity(candidate));budget.check()
                reuse=plan.get('reused_baseline_physical')
                if reuse:
                    p=Path(reuse['directory'])/f'physical_{ordinal:03d}_OLD_ON.json'
                    self.assertEqual(sha(p),reuse['receipt_sha256'][p.name]);value=read(p)
                else:
                    self.assertLess(record['extra_thermal_calls'],12);record['extra_thermal_calls']+=1
                    value=namespace['evaluate_model_candidate'](self.old,candidate,None,Budget(seconds=min(10,max(0,deadline-time.monotonic()))))
                saved=read(legacy/f'physical_{ordinal:03d}_ON.json')
                self.assertEqual(value['state'],'SAFE');self.assertEqual(fixture.scientific(value),fixture.scientific(saved))
                if not reuse:save(output/f'physical_{ordinal:03d}_OLD_ON.json',value)
            self.assertEqual(before,after);self.assertEqual(len(before),12);self.assertEqual(projections,228)
            record['checks']['complete_legal_sets_and_physical_fields_equal']=True
            record.update(legal_before=len(before),legal_after=len(after),state_projections=projections,
                          total_batch_thermal_calls=prior['thermal_calls']+record['extra_thermal_calls'],
                          reused_baseline_physical_receipts=12 if plan.get('reused_baseline_physical') else 0)

        def test_03_miss_hit_clear_and_baseline_exact_slack(self):
            model=self.fresh();self.assertFalse(hasattr(model,'_joint_state_gate_audit_cache'))
            old=namespace['_audit_joint_state_gate_off'](model,*self.args)
            real=joint_state_support.verify_gate_off_rows;calls=[]
            def counted(*args,**kwargs):calls.append(1);return real(*args,**kwargs)
            with patch.object(joint_state_support,'verify_gate_off_rows',counted):
                first=self.audit(model);n=len(calls);self.assertGreater(n,0)
                second=self.audit(model);self.assertEqual(len(calls),n)
                self.assertEqual(audit_science(old),audit_science(first));self.assertEqual(audit_science(old),audit_science(second))
                self.assertTrue(all(r['certificate_cache_hit'] for r in second['states']))
                milp._clear_joint_state_gate_audit_cache(model,reason='independent_validation')
                third=self.audit(model);self.assertGreater(len(calls),n);self.assertEqual(audit_science(old),audit_science(third))
            record['checks']['strict_miss_hit_clear_equal_baseline']=True
            record['audit_snapshots']['miss_hit_clear']=model._joint_state_gate_audit_cache['stats']

        def test_04_box_coefficient_input_and_source_change_recertify(self):
            model=self.fresh();self.audit(model);oldmiss=model._joint_state_gate_audit_cache['stats']['misses']
            source=self.args[0][0];lo,hi=model.bounds[source];newhi=math.nextafter(model.ub[source],math.inf)
            model.ub[source]=newhi;model.bounds[source]=(lo,F.from_float(newhi))
            self.audit(model);self.assertGreater(model._joint_state_gate_audit_cache['stats']['misses'],oldmiss)
            model.input_sha256='audit-only-synthetic-input-identity'
            self.audit(model);self.assertGreater(model._joint_state_gate_audit_cache['stats']['identity_invalidations'],0)
            invalidations=model._joint_state_gate_audit_cache['stats']['identity_invalidations']
            model.instance=deepcopy(model.instance);model.instance['id']+=':audit-only-metadata-copy'
            self.audit(model)
            self.assertGreater(model._joint_state_gate_audit_cache['stats']['identity_invalidations'],invalidations)
            real=model.coefficients.get
            variation={'constant':0}
            def changed(state,duration):
                coeff=deepcopy(real(state,duration));coeff['energy'][-1]=coeff['energy'][-1]+milp.I.rational(F(variation['constant'],10**9));return coeff
            with patch.object(model.coefficients,'get',changed):
                self.audit(model);oldmiss=model._joint_state_gate_audit_cache['stats']['misses']
                variation['constant']=1
                self.audit(model)
                self.assertGreater(model._joint_state_gate_audit_cache['stats']['misses'],oldmiss)
            def fail(*args,**kwargs):raise ValueError('audit-only changed runtime verifier')
            with patch.object(joint_state_support,'verify_gate_off_rows',fail):
                with self.assertRaisesRegex(ValueError,'changed runtime verifier'):self.audit(model)
            record['checks']['key_changes_recertify_and_runtime_change_cannot_reuse_hit']=True

        def test_05_capacity_clear_forces_recertification(self):
            model=self.fresh();real=model.coefficients.get;calls=[];verify=joint_state_support.verify_gate_off_rows
            def counted(*args,**kwargs):calls.append(1);return verify(*args,**kwargs)
            with patch.object(milp,'_GATE_AUDIT_CACHE_LIMIT',1),patch.object(joint_state_support,'verify_gate_off_rows',counted):
                self.audit(model);n=len(calls)
                def changed(state,duration):
                    coeff=deepcopy(real(state,duration));coeff['energy'][-1]=coeff['energy'][-1]+milp.I.rational(F(1,10**8));return coeff
                with patch.object(model.coefficients,'get',changed):self.audit(model)
                self.audit(model);self.assertGreater(len(calls),n+1)
                self.assertGreater(model._joint_state_gate_audit_cache['stats']['clears'],0)
            record['checks']['capacity_clear_recertifies']=True

        def test_06_actual_kernel_context_rebinding_and_mutation_invalidate(self):
            import thermal
            model=self.fresh();self.audit(model)
            for name in ['UP','DOWN']:
                before=model._joint_state_gate_audit_cache['stats']['identity_invalidations']
                replacement=getattr(thermal._kernel,name).copy()
                with patch.object(thermal._kernel,name,replacement):self.audit(model)
                self.assertGreater(model._joint_state_gate_audit_cache['stats']['identity_invalidations'],before,name)
                self.audit(model)
            before=model._joint_state_gate_audit_cache['stats']['identity_invalidations']
            original=thermal._kernel.UP.prec
            try:
                thermal._kernel.UP.prec=original+1
                self.audit(model)
            finally:thermal._kernel.UP.prec=original
            self.assertGreater(model._joint_state_gate_audit_cache['stats']['identity_invalidations'],before)
            record['checks']['actual_kernel_context_rebinding_and_precision_mutation_invalidate']=True

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    for name,digest in plan['source_sha256'].items():assert sha(REPO/name)==digest,name
    record.update(ended_utc=now(),wall_s=time.monotonic()-start,tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),
        physical_evaluation_note='Same original evaluator implementation; independent structure/state and original/new binary64 row audit',
        synthetic_changes_scope='Only audit-only object copies or patched callables; no research/physical input changes')
    save(output/'results.json',record);print(json.dumps(record,indent=2,default=str))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--legacy',type=Path);parser.add_argument('--reuse-baseline',type=Path);args=parser.parse_args()
    if args.action=='freeze':freeze(args.output,args.legacy,args.reuse_baseline)
    else:raise SystemExit(run(args.output))
