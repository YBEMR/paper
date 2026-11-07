"""K175 independent pure checks: exact labels and mocked lifecycle, no science.

Historical receipts are test data, never initialization for a real invocation.
MethodBudget and the unchanged idle-worker gate are compiled from their AST;
all optimizer/physical dependencies are explicit in-memory doubles.
"""
import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import types
import unittest
import uuid

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
OUT = BASE/'results/linked_release_integration01'
READS = {}
GUARD = {'scientific_import':0, 'process_or_network':0,
         'forbidden_production_entry':0}
ALLOWED = {'linked_release_policy.py', 'linked_release_method.py',
           'test_linked_release_pure.py'}
SCIENCE = {'numpy','scipy','matlab','milp','inputs','thermal','schedules',
    'scene_adapter','neighborhood','neighborhood_method','linked_neighborhood',
    'anchor_preelimination','initial_point','initial_schedule','matlab_bridge',
    'augmented_method','linked_neighborhood_adapter','neighborhood_adapter'}
TRACE = []


def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(obj):
    return sha(json.dumps(obj, sort_keys=True, ensure_ascii=False,
        separators=(',',':'), allow_nan=False).encode())
def read(path):
    path=Path(path); raw=path.read_bytes()
    READS[path.relative_to(ROOT).as_posix()]=sha(raw)
    return json.loads(raw)
def source(path):
    path=Path(path); raw=path.read_bytes()
    READS[path.relative_to(ROOT).as_posix()]=sha(raw)
    return raw.decode('utf-8-sig')
def load(path,name):
    path=Path(path); source(path)
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
def audit(event,args):
    if event=='import' and args[0].split('.')[0] in SCIENCE:
        GUARD['scientific_import']+=1
        raise RuntimeError('Scientific import forbidden: '+args[0])
    if event in {'subprocess.Popen','os.system','socket.connect','socket.getaddrinfo'} or event.startswith('os.spawn'):
        GUARD['process_or_network']+=1;raise RuntimeError('No process/network')
def profile(frame,event,arg):
    filename=frame.f_code.co_filename.replace('\\','/')
    if event=='call' and '/research/chapter3_experiments/' in filename and '/results/' not in filename and Path(filename).name not in ALLOWED:
        GUARD['forbidden_production_entry']+=1
        raise RuntimeError('Production scientific entry forbidden: '+filename)


class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now
    def tick(self,n=1.):self.now+=n


class Exhausted(Exception):pass
class BaseBudget:
    def __init__(self,seconds=60,panels=100000,refinements=20000,hook=None):
        self.seconds=seconds;self.panel_limit=panels;self.refinement_limit=refinements
        self.hook=hook;self.panels=0;self.refinements=0


def budget_class():
    tree=ast.parse(source(BASE/'timing.py'))
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MethodBudget')
    env={'Budget':BaseBudget,'Exhausted':Exhausted,'math':math,'time':time,
         'contextmanager':contextmanager}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<pure AST timing.MethodBudget>','exec'),env)
    return env['MethodBudget']


MethodBudget=budget_class()


def budget_identity(b):
    if not hasattr(b,'_scene_adapter_budget_identity'):
        b._scene_adapter_budget_identity={'token':uuid.uuid4().hex,'start':repr(b.start),
            'seconds':repr(b.seconds),'panel_limit':b.panel_limit,'refinement_limit':b.refinement_limit}
    return deepcopy(b._scene_adapter_budget_identity)


def opened(instance,mask,budget):
    scenes={s['id']:s for s in instance['scenarios']}
    if not isinstance(mask,dict) or set(mask)!=set(scenes):raise ValueError('scene mask')
    out={}
    for sid,scene in scenes.items():
        budget.check();values=mask[sid];expected={s['id'] for s in scene['stage_instances']}
        if not isinstance(values,list) or len(values)!=len(set(values)) or not values or not set(values)<expected:raise ValueError('stage mask')
        out[sid]=sorted(values)
    return out


def options(candidate):
    return {sid:{r['stage_id']:{'unit':r['unit'],'opp':r['opp'],'start_ms':str(F(r['start_ms']))} for r in rows}
            for sid,rows in candidate['scenes'].items()}


def fixture(case='base__R3'):
    folder=BASE/'results/linked_ablation_execution01/calls'/(case+'__C')
    instance=read(folder/'input_instance.json');result=read(folder/'result.json')
    condition=deepcopy(result['phases'][1]['condition'])
    return instance,condition


def bound_fixture(case='base__R3'):
    instance,c=fixture(case);clock=Clock();budget=MethodBudget(300,clock=clock)
    # This only binds archived immutable fixture labels to a fake test token.
    c['budget_identity']=budget_identity(budget)
    for key in ('seed_receipt','warm_receipt'):
        c[key]['identity']['budget']=deepcopy(c['budget_identity'])
        c[key]['receipt_sha256']=canonical({k:v for k,v in c[key].items() if k!='receipt_sha256'})
        c[key+'_sha256']=c[key]['receipt_sha256']
    clock.tick(max(c[k]['completed_at_elapsed_s'] for k in ('seed_receipt','warm_receipt'))+1)
    c['condition_sha256']=canonical({k:v for k,v in c.items() if k!='condition_sha256'})
    return instance,c,budget,clock


def validate_condition(instance,c,*,budget,shared_deployment=None):
    budget.check()
    if c['source_input_sha256']!=canonical(instance) or c['budget_identity']!=budget_identity(budget):raise ValueError('bound input/budget')
    if c['warm_candidate_sha256']!=canonical(c['warm_candidate']) or c['seed_candidate_sha256']!=canonical(c['seed_candidate']):raise ValueError('anchor/seed hash')
    if c['warm_options_by_scene']!=options(c['warm_candidate']) or c['seed_options_by_scene']!=options(c['seed_candidate']):raise ValueError('anchor/seed options')
    if c['opened_by_scene']!=opened(instance,c['opened_by_scene'],budget):raise ValueError('normalized mask')
    if c['condition_sha256']!=canonical({k:v for k,v in c.items() if k!='condition_sha256'}):raise ValueError('condition hash')
    if any(c['seed_options_by_scene'][s][k]['unit']!=r['unit'] for s,rows in c['warm_options_by_scene'].items() for k,r in rows.items()):raise ValueError('unit drift')
    return deepcopy(c)


def module(name,**attrs):
    value=types.ModuleType(name);value.__dict__.update(attrs);return value


@contextmanager
def installed(values):
    old={k:sys.modules.get(k) for k in values}
    sys.modules.update(values)
    try:yield
    finally:
        for k,v in old.items():
            if v is None:sys.modules.pop(k,None)
            else:sys.modules[k]=v


def extract(path,names,env):
    tree=ast.parse(source(path));nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    if {n.name for n in nodes}!=set(names):raise ValueError('Missing source AST')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pure AST '+Path(path).name+'>','exec'),env)
    return env


def idle_gate(result,session,latched=False):
    # Execute the unchanged production gate AST, not a handwritten substitute.
    tree=ast.parse(source(BASE/'neighborhood_method.py'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp)
        and any(isinstance(item,ast.Raise) and 'A failed or active worker cannot enter the second phase' in ast.unparse(item) for item in n.body))
    env={'result':result,'session':session,'_second_phase':{'latched':lambda:latched}}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<pure AST idle-worker gate>','exec'),env)


def domain_rows(instance,condition,sid,budget):
    helper=load(BASE/'results/bound_build_replay01/domain/extract_domains.py','k175_labels_'+uuid.uuid4().hex)
    raw=helper.original_options(instance,sid,condition['shared_deployment'])
    rows,_=helper.neighborhood_options(instance,condition,raw,2)
    rows=[r for r in rows if F(r['end_ms'])<=F(r['request_deadline_ms'])]
    env={'canonical_hash':canonical,'_scenes':lambda i:{s['id']:s for s in i['scenarios']},'_q':F,
        'hashlib':hashlib,'Path':Path,'__file__':str(BASE/'anchor_preelimination.py'),
        'PROTOCOL':'closed-anchor-original-resource-and-direct-edge-filter-v1'}
    fn=extract(BASE/'anchor_preelimination.py',{'filter_closed_anchor_options'},env)['filter_closed_anchor_options']
    ln=module('linked_neighborhood',validate_linked_condition=validate_condition,
        _member=lambda c,s,k,u,o,t:u==c['seed_options_by_scene'][s][k]['unit'] and
        (k in c['opened_by_scene'][s] or (o==c['warm_options_by_scene'][s][k]['opp'] and F(t)==F(c['warm_options_by_scene'][s][k]['start_ms']))))
    with installed({'linked_neighborhood':ln}):return fn(instance,condition,rows,budget=budget,scene_ids=[sid])


class PolicyTests(unittest.TestCase):
    def setUp(self):self.policy=load(BASE/'linked_release_policy.py','k175_policy_'+uuid.uuid4().hex)

    def test_historical_R1_R3_rule_and_domain_inclusion(self):
        records=[]
        for case in ('base__R1','base__R3'):
            i,c,b,clock=bound_fixture(case);before=deepcopy(c)
            with installed({'scene_adapter':module('scene_adapter',canonical_hash=canonical,_budget_identity=budget_identity),
                            'linked_neighborhood':module('linked_neighborhood',validate_linked_condition=validate_condition)}):
                answer=self.policy.select_release(i,c,budget=b)
            self.assertEqual(c,before)
            for sid,mask in answer['opened_by_scene'].items():
                expected=set(c['opened_by_scene'][sid])
                if case=='base__R3' and sid=='AB_offset_0ms':expected.add('AB_offset_0ms::B_r1::B.main')
                self.assertEqual(set(mask),expected)
                n=deepcopy(c);n['opened_by_scene']=deepcopy(answer['opened_by_scene']);n['condition_sha256']=canonical({k:v for k,v in n.items() if k!='condition_sha256'})
                old,os=domain_rows(i,c,sid,b);new,ns=domain_rows(i,n,sid,b)
                ident=lambda r:(r['stage_instance_id'],r['unit_id'],r['opp_id'],r['start_ms'])
                self.assertLessEqual(set(map(ident,old)),set(map(ident,new)))
                expected_counts={('base__R1','AB_offset_0ms'):(216,216),('base__R1','AC_offset_0ms'):(213,213),
                    ('base__R3','AB_offset_0ms'):(227,339),('base__R3','AC_offset_0ms'):(240,240)}
                self.assertEqual((len(old),len(new)),expected_counts[case,sid])
                anchors=[a['stage_id'] for a in ns['anchors_by_scene'][sid]]
                if case=='base__R3' and sid=='AB_offset_0ms':
                    self.assertNotIn('AB_offset_0ms::B_r1::B.main',anchors)
                    added=set(map(ident,new))-set(map(ident,old))
                    counts={stage:sum(label[0]==stage for label in added) for stage in c['warm_options_by_scene'][sid]}
                    self.assertEqual({stage:n for stage,n in counts.items() if n},
                        {'AB_offset_0ms::B_r1::B.main':52,
                         'AB_offset_0ms::A_r1::A.main':39,
                         'AB_offset_0ms::B_r1::B.pre':21})
                # Every exact S1 choice remains admitted after refiltering.
                for stage,row in c['warm_options_by_scene'][sid].items():
                    self.assertIn((stage,row['unit'],row['opp'],str(F(row['start_ms']))),set(map(ident,new)))
                records.append({'case':case,'scene':sid,'old_count':len(old),'new_count':len(new),
                    'old_subset_new':True,'remaining_closed':anchors,'new_labels_sha256':canonical(sorted(map(ident,new)))})
        TRACE.append({'historical_domain_replay':records})

    def test_wrong_input_anchor_receipt_budget_mask_rejected(self):
        for kind in ('input','anchor','receipt','budget','mask'):
            i,c,b,clock=bound_fixture()
            if kind=='input':i['window_ms']='401'
            elif kind=='anchor':c['warm_candidate_sha256']='0'*64
            elif kind=='receipt':c['warm_receipt_sha256']='1'*64
            elif kind=='budget':c['budget_identity']['token']='not-this-budget'
            else:c['opened_by_scene']['AB_offset_0ms'].append('not-a-stage')
            with self.subTest(kind=kind):
                with installed({'scene_adapter':module('scene_adapter',canonical_hash=canonical,_budget_identity=budget_identity),
                    'linked_neighborhood':module('linked_neighborhood',validate_linked_condition=validate_condition)}):
                    with self.assertRaises((ValueError,KeyError,TypeError)):self.policy.select_release(i,c,budget=b)

    def test_expiry_raises_without_partial_selection(self):
        i,c,b,clock=bound_fixture();clock.tick(300)
        with self.assertRaises(Exhausted):self.policy.select_release(i,c,budget=b)


class LifecycleHarness:
    def __init__(self,**options_):
        self.options=options_;self.instance,self.base=fixture('base__R3')
        self.clock=Clock();self.budget=MethodBudget(300,clock=self.clock)
        self.calls=[];self.conditions=[];self.selections=[];self.events=[];self.saved={}
        self.session=types.SimpleNamespace(closed=False,request_blocked=False,event_consumer=None)
        self.seed=deepcopy(self.base['seed_candidate']);self.seed_receipt=deepcopy(self.base['seed_receipt'])
        self.warm=deepcopy(self.base['warm_candidate']);self.warm_receipt=deepcopy(self.base['warm_receipt'])
        for receipt in (self.seed_receipt,self.warm_receipt):
            receipt['identity']['budget']=budget_identity(self.budget)
            receipt['completed_at_elapsed_s']=1.
            receipt['receipt_sha256']=canonical({k:v for k,v in receipt.items() if k!='receipt_sha256'})

    def factory(self,instance,deployment,seed_candidate,seed_receipt,mask,*,warm_candidate,warm_receipt,budget,accuracy):
        self.assert_budget(budget);self.clock.tick();self.events.append('condition')
        c=deepcopy(self.base);c.update(source_input_sha256=canonical(instance),shared_deployment=deepcopy(deployment),
            seed_candidate=deepcopy(seed_candidate),seed_receipt=deepcopy(seed_receipt),warm_candidate=deepcopy(warm_candidate),warm_receipt=deepcopy(warm_receipt),
            seed_candidate_sha256=canonical(seed_candidate),warm_candidate_sha256=canonical(warm_candidate),
            seed_receipt_sha256=seed_receipt['receipt_sha256'],warm_receipt_sha256=warm_receipt['receipt_sha256'],
            seed_options_by_scene=options(seed_candidate),warm_options_by_scene=options(warm_candidate),
            opened_by_scene=opened(instance,mask,budget),budget_identity=budget_identity(budget),accuracy=deepcopy(accuracy))
        c['condition_sha256']=canonical({k:v for k,v in c.items() if k!='condition_sha256'})
        if self.options.get('wrong_final_anchor') and self.selections:
            # A well-hashed alternate anchor must still be rejected by the
            # adapter's final S1 binding, even if a custom factory returns it.
            sid=next(iter(c['warm_candidate']['scenes']))
            c['warm_candidate']['scenes'][sid][0]['start_ms']='5'
            c['warm_candidate_sha256']=canonical(c['warm_candidate'])
            c['warm_options_by_scene']=options(c['warm_candidate'])
            c['warm_receipt']['safe_candidate']=deepcopy(c['warm_candidate'])
            c['warm_receipt']['receipt_sha256']=canonical({k:v for k,v in c['warm_receipt'].items() if k!='receipt_sha256'})
            c['warm_receipt_sha256']=c['warm_receipt']['receipt_sha256']
            c['condition_sha256']=canonical({k:v for k,v in c.items() if k!='condition_sha256'})
        self.conditions.append(deepcopy(c))
        return c

    def assert_budget(self,budget):
        if budget is not self.budget:raise AssertionError('reset/root budget mismatch')

    def selector(self,instance,c,*,budget):
        self.assert_budget(budget);self.events.append('select');self.selections.append(deepcopy(c))
        self.clock.tick(self.options.get('selector_s',3))
        if self.options.get('expire_select'):self.clock.tick(300)
        budget.check()
        real=load(BASE/'linked_release_policy.py','k175_policy_lifecycle_'+uuid.uuid4().hex)
        answer=real.select_release(instance,c,budget=budget)
        bad=self.options.get('tamper_selection')
        if bad=='mask':answer['opened_by_scene']['AB_offset_0ms'].remove('AB_offset_0ms::A_r1::A.main')
        elif bad=='receipt':answer['receipt']['S1_candidate_sha256']='bad'
        return answer

    def n1(self,loader,workdir,**kw):
        self.calls.append(kw);b=kw['budget'];self.assert_budget(b);config,instance=loader(b)
        self.clock.tick(7);observer=kw['on_global_update']
        result={'state':'SAFE','safe_candidate':deepcopy(self.seed),'safe_upper_bound_J':'10',
            'aggregation':deepcopy(self.seed_receipt),'timing':{},'phases':[],
            'search_failure_latched':False,'committed_safe_snapshot':None}
        def commit(phase,candidate,receipt,energy):
            result.update(safe_candidate=deepcopy(candidate),safe_upper_bound_J=energy,aggregation=deepcopy(receipt))
            snapshot={'phase_index':phase,'safe_candidate':deepcopy(candidate),'safe_upper_bound_J':energy,
                'aggregation':deepcopy(receipt),'committed_at_s':b.elapsed}
            result['committed_safe_snapshot']=snapshot
            observer(result,{'phase_index':phase,'safe_upper_bound_J':energy})
        if not self.options.get('missing_s1'):commit(0,self.seed,self.seed_receipt,'10')
        self.clock.tick(11)
        if not self.options.get('missing_s1'):commit(1,self.warm,self.warm_receipt,'8')
        else:result.update(state='UNRESOLVED',safe_candidate=None,safe_upper_bound_J=None,aggregation=None)
        second=kw['_second_phase']
        try:
            if self.options.get('active_worker'):self.session.event_consumer=object()
            idle_gate(result,self.session)
            self.events.append('opened')
            mask=second['opened'](instance,b)
            self.events.append('final_condition')
            seed_argument=deepcopy(self.seed)
            if self.options.get('wrong_final_seed'):
                seed_argument['scenes'][next(iter(seed_argument['scenes']))][0]['start_ms']='5'
            c=second['condition_factory'](instance,self.base['shared_deployment'],seed_argument,self.seed_receipt,mask,
                budget=b,accuracy=self.base['accuracy'])
            self.conditions.append(deepcopy(c))
            if self.options.get('twice'):second['opened'](instance,b)
            result['phases'].append({'phase_index':2,'name':'all_stage_opp_start','condition':c})
        except Exhausted:
            result['reason']='wall_time_limit'
        except Exception as error:
            result['reason']='INVALID_INPUT_OR_INTERFACE';result['error']=str(error)
        result['timing']=b.summary()
        return result

    def run(self):
        harness=self
        class Context:
            def __init__(self,session_factory):self.failed=False;self.recorder_factory=lambda *a,**k:None
            def summary(self):return {'fake_context':True}
        class Session:
            def __init__(self,native,context):self.native=native
        noop=lambda *a,**k:None
        linked=module('linked_neighborhood',PROTOCOL=self.base['protocol'],_opened=opened,
            make_linked_condition=self.factory,validate_linked_condition=validate_condition,check_linked_candidate=noop)
        values={'timing':module('timing',MethodBudget=MethodBudget),
            'thermal':module('thermal',_accuracy=lambda x:deepcopy(x),Exhausted=Exhausted),
            'augmented_method':module('augmented_method',AugmentedMethodContext=Context,AugmentedSession=Session),
            'linked_neighborhood':linked,
            'linked_neighborhood_adapter':module('linked_neighborhood_adapter',PROTOCOL='fake-evaluation',evaluate_linked_scene=noop),
            'matlab_bridge':module('matlab_bridge',MatlabSession=lambda *a,**k:self.session),
            'neighborhood':module('neighborhood',make_n1_condition=noop),
            'neighborhood_adapter':module('neighborhood_adapter',evaluate_n1_scene=noop),
            'neighborhood_method':module('neighborhood_method',execute_n1_neighborhood=self.n1),
            'scene_adapter':module('scene_adapter',canonical_hash=canonical,_budget_identity=budget_identity),
            'scene_method':module('scene_method',_save=lambda p,x:self.saved.__setitem__(str(p),deepcopy(x))),
            'milp':module('milp',build_model=lambda *a,**k:None),
            'linked_release_policy':module('linked_release_policy',select_release=self.selector,
                validate_selection=load(BASE/'linked_release_policy.py','k175_validate_'+uuid.uuid4().hex).validate_selection)}
        with installed(values):
            entry=load(BASE/'linked_release_method.py','k175_lifecycle_'+uuid.uuid4().hex)
            self.entry=entry
            self.result=entry.execute_linked_conditional_release(lambda budget:({'accuracy_targets':deepcopy(self.base['accuracy'])},deepcopy(self.instance)),
                OUT/'.pure_unused',shared_deployment=deepcopy(self.base['shared_deployment']),
                opened_by_scene=read(BASE/'results/linked_ablation_execution01/calls/base__R3__C/result.json')['condition']['opened_by_scene'],
                linked_opened_by_scene=deepcopy(self.base['opened_by_scene']),budget=self.budget,
                clock=self.clock,seconds=300)
        return self.result


class LifecycleTests(unittest.TestCase):
    def test_freeze_select_condition_same_S1_once_and_root_budget(self):
        h=LifecycleHarness();r=h.run()
        self.assertEqual(len(h.calls),1);self.assertEqual(len(h.selections),1)
        self.assertEqual(h.events.count('select'),1)
        baseline=h.selections[0];final=r['phases'][0]['condition']
        for key in ('seed_candidate_sha256','seed_receipt_sha256','warm_candidate_sha256','warm_receipt_sha256','budget_identity','shared_deployment','accuracy'):
            self.assertEqual(baseline[key],final[key],key)
        self.assertEqual(final['warm_candidate'],h.warm)
        self.assertEqual(set(final['opened_by_scene']['AB_offset_0ms'])-set(h.base['opened_by_scene']['AB_offset_0ms']),{'AB_offset_0ms::B_r1::B.main'})
        self.assertEqual(h.budget.deadline,300);self.assertEqual(h.budget.start,0)
        self.assertGreaterEqual(h.budget.elapsed,21)
        self.assertTrue(any('release' in x['phase'] for x in h.budget.records))
        TRACE.append({'lifecycle':'same_S1_once','events':h.events,'elapsed':h.budget.elapsed,
            'phases':h.budget.records,'root_deadline':h.budget.deadline})

    def test_expired_selection_keeps_committed_safe_and_no_second_condition(self):
        h=LifecycleHarness(expire_select=True);r=h.run()
        self.assertEqual(r['state'],'SAFE');self.assertEqual(r['safe_candidate'],h.warm)
        self.assertEqual(r['safe_upper_bound_J'],'8');self.assertEqual(r['reason'],'wall_time_limit')
        self.assertEqual(len(r['phases']),0)
        self.assertEqual(h.events.count('condition'),1)

    def test_active_worker_never_runs_selector(self):
        h=LifecycleHarness(active_worker=True);r=h.run()
        self.assertEqual(len(h.selections),0);self.assertEqual(r['safe_upper_bound_J'],'8')
        self.assertIn('active worker',r['error'])

    def test_missing_first_pass_S1_never_runs_selector(self):
        h=LifecycleHarness(missing_s1=True);r=h.run()
        self.assertEqual(len(h.selections),0);self.assertIsNone(r['safe_upper_bound_J'])
        self.assertNotIn(2,[p['phase_index'] for p in r['phases']])

    def test_one_time_selection_reentry_rejected(self):
        h=LifecycleHarness(twice=True);r=h.run()
        self.assertEqual(len(h.selections),1);self.assertEqual(r['reason'],'INVALID_INPUT_OR_INTERFACE')

    def test_tampered_mask_or_receipt_rejected_and_safe_preserved(self):
        for bad in ('mask','receipt'):
            with self.subTest(tamper=bad):
                h=LifecycleHarness(tamper_selection=bad);r=h.run()
                self.assertEqual(r['safe_upper_bound_J'],'8');self.assertEqual(r['reason'],'INVALID_INPUT_OR_INTERFACE')
                self.assertEqual(len(r['phases']),0)

    def test_wrong_final_seed_or_anchor_rejected_preserving_safe_S1(self):
        for bad in ('wrong_final_seed','wrong_final_anchor'):
            with self.subTest(tamper=bad):
                h=LifecycleHarness(**{bad:True});r=h.run()
                self.assertEqual(len(h.selections),1)
                self.assertEqual(r['state'],'SAFE');self.assertEqual(r['safe_upper_bound_J'],'8')
                self.assertEqual(r['safe_candidate'],h.warm)
                self.assertEqual(r['reason'],'INVALID_INPUT_OR_INTERFACE')
                self.assertEqual(len(r['phases']),0)

    def test_original_C_and_shared_lifecycle_source_unchanged(self):
        manifest=read(BASE/'results/linked_ablation_execution01/declaration.json')['source_sha256']
        names=('linked_method.py','linked_neighborhood.py','anchor_preelimination.py','neighborhood_method.py','timing.py')
        for name in names:
            rel=(BASE/name).relative_to(ROOT).as_posix()
            self.assertEqual(sha((BASE/name).read_bytes()),manifest[rel],name)


def main(out):
    out=Path(out)
    if out.exists():raise FileExistsError('Append-only check run')
    out.mkdir(parents=True);started=time.perf_counter()
    sys.addaudithook(audit);sys.setprofile(profile)
    try:
        with (out/'unittest.txt').open('w',encoding='utf8') as stream:
            suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (PolicyTests,LifecycleTests)])
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    finally:sys.setprofile(None)
    source(Path(__file__))
    stable=all(sha((ROOT/p).read_bytes())==h for p,h in READS.items())
    payload={'passed':result.wasSuccessful() and stable and all(v==0 for v in GUARD.values()),
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'guard':GUARD,'source_sha256':READS,'source_unchanged':stable,
        'research_calls':0,'matlab_calls':0,'models':0,'thermal_calls':0,'full_candidate_evaluations':0,
        'new_U':False,'elapsed_s':time.perf_counter()-started,
        'scope':'exact label replay + real new adapter with fake N1/worker and AST MethodBudget/idle gate; no real search',
        'trace':TRACE}
    (out/'checks.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in payload.items() if k not in {'source_sha256','trace'}},ensure_ascii=False))
    if not payload['passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
