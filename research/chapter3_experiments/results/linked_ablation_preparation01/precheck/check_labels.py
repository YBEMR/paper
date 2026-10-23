"""K172: stdlib-only anchor-label and root-clock preparation checks.

AST extracts original label-filter/member and budget classes without module
imports. Receipt validation is explicitly stubbed: this is neither a SAFE
certificate nor an execution of the scientific planner/evaluator.
"""
import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import io
from itertools import product
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT=Path(__file__).resolve().parents[5]
BASE=ROOT/'research/chapter3_experiments'
READS={}
DETAILS=[]
GUARD={'scientific_import':0,'production_code_entry':0,'process_launch':0}
FAKE_TRANSPORT_CALLS=0


class GuardViolation(BaseException):
    pass


def audit(event,args):
    if event=='import' and args[0].split('.')[0] in {
        'numpy','scipy','milp','thermal','inputs','schedules','matlab_bridge',
        'neighborhood','linked_neighborhood','anchor_preelimination',
        'neighborhood_method','linked_method','scene_adapter','timing','partial_method'}:
        GUARD['scientific_import']+=1
        raise GuardViolation('forbidden scientific module import: '+args[0])
    if event=='subprocess.Popen' or event=='os.system' or event.startswith('os.spawn'):
        GUARD['process_launch']+=1
        raise GuardViolation('forbidden process launch: '+event)


def profile(frame,event,arg):
    if event=='call':
        filename=frame.f_code.co_filename.replace('\\','/')
        if '/research/chapter3_experiments/' in filename and '/results/' not in filename:
            GUARD['production_code_entry']+=1
            raise GuardViolation('forbidden production code entry: '+filename)


def read(path):
    raw=path.read_bytes()
    READS[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(raw).hexdigest()
    return raw.decode('utf-8-sig')


def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def extract(path,names,namespace,*,remove_filter_import=False):
    source=read(path)
    tree=ast.parse(source)
    nodes=[deepcopy(n) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    if {n.name for n in nodes}!=set(names):
        raise ValueError('AST definition missing: '+str(names))
    removed=[]
    if remove_filter_import:
        for node in nodes:
            imports=[n for n in node.body if isinstance(n,(ast.Import,ast.ImportFrom))]
            if len(imports)!=1 or not isinstance(imports[0],ast.ImportFrom) or imports[0].module!='linked_neighborhood':
                raise ValueError('unexpected filter import shape')
            removed=[ast.unparse(imports[0])]
            node.body=[n for n in node.body if n is not imports[0]]
    label='<K172_AST_'+path.name+'_'+','.join(sorted(names))+'>'
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),label,'exec'),namespace)
    DETAILS.append({'kind':'AST_extract','source':str(path.relative_to(ROOT)).replace('\\','/'),
        'definitions':sorted(names),'removed_imports':removed,'ordinary_module_import_performed':False})


class Clock:
    def __init__(self):self.now=0.0
    def __call__(self):return self.now
    def step(self,seconds):self.now+=float(seconds)


CLOCK=Clock()
KERNEL={'time':SimpleNamespace(monotonic=CLOCK)}
THERMAL={'time':SimpleNamespace(monotonic=CLOCK)}
BUDGET_NS={}
FILTER_NS={}
SOLVE_NS={}


def prepare_extractions():
    extract(ROOT/'research/v1_evaluator/interval.py',{'Budget','Exhausted'},KERNEL)
    THERMAL['_kernel']=SimpleNamespace(Budget=KERNEL['Budget'])
    extract(BASE/'thermal.py',{'Budget'},THERMAL)
    BUDGET_NS.update(Budget=THERMAL['Budget'],Exhausted=KERNEL['Exhausted'],
        math=math,time=SimpleNamespace(monotonic=CLOCK),contextmanager=contextmanager)
    extract(BASE/'timing.py',{'MethodBudget'},BUDGET_NS)
    FILTER_NS.update(_q=F,canonical_hash=canonical,_scenes=lambda i:{s['id']:s for s in i['scenarios']},
        hashlib=hashlib,Path=Path,__file__=str(BASE/'anchor_preelimination.py'),
        PROTOCOL='closed-anchor-original-resource-and-direct-edge-filter-v1')
    extract(BASE/'linked_neighborhood.py',{'_member'},FILTER_NS)
    # Stub validates fixture identity/shape only; no claim of matching SAFE receipts.
    def identity_stub(instance,condition,*,budget):
        budget.check()
        if condition.get('fixture_identity')!='K172-handwritten-labels-no-SAFE':
            raise ValueError('unexpected fixture condition')
        return condition
    FILTER_NS['validate_linked_condition']=identity_stub
    extract(BASE/'anchor_preelimination.py',{'filter_closed_anchor_options'},FILTER_NS,
        remove_filter_import=True)
    SOLVE_NS.update(Exhausted=KERNEL['Exhausted'],
        NUMERICAL_CONSISTENCY_CONFLICT='fixture_numerical_conflict',
        NUMERICAL_CONSISTENCY_UNRESOLVED='fixture_numerical_unresolved',
        _safe=lambda *_:False)
    extract(BASE/'partial_method.py',{'_solve_scene'},SOLVE_NS)


def make_budget(seconds=300):
    CLOCK.now=0.0
    return BUDGET_NS['MethodBudget'](seconds,clock=CLOCK)


def fixture(*,same_unit=False,closed='A.pre'):
    sid='S1'
    assigned={'A.pre':'CPU1','B.pre':'CPU1' if same_unit else 'CPU2','B.main':'NPU0'}
    durations={'A.pre':'2','B.pre':'3/2','B.main':'2'}
    starts={'A.pre':['0','3/2','2','5','15/2'],
        'B.pre':['0','3/2','2','7/2','5','15/2'],
        'B.main':['0','3/2','2','5','15/2','10']}
    units=[{'id':'CPU1','domain_id':'CPU'},{'id':'CPU2','domain_id':'CPU'},
           {'id':'NPU0','domain_id':'NPU'}]
    case={'platform':{'units':units,'domains':{'CPU':{'opps':['L','M','H']},'NPU':{'opps':['L','M','H']}}},
          'stage_modes':{},'scenarios':[{'id':sid,'stage_instances':[],'dependencies':[['B.pre','B.main']]}]}
    options=[]; warm={}; seed={}
    for name in assigned:
        unit=assigned[name];domain='NPU' if unit=='NPU0' else 'CPU'
        case['scenarios'][0]['stage_instances'].append({'id':name,'shared_stage_id':name,'request_id':name+'.request'})
        case['stage_modes'][name]=[]
        start='5' if name=='B.main' else '2' if same_unit and name=='B.pre' else '0'
        warm[name]={'unit':unit,'opp':'M','start_ms':start}
        seed[name]={'unit':unit,'opp':'H','start_ms':start}
        for opp in ('L','M','H'):
            mode={'shared_stage_id':name,'unit_id':unit,'opp_id':opp,'domain_id':domain,'duration_ms':durations[name]}
            case['stage_modes'][name].append(mode)
            values=[start] if name==closed and opp=='M' else [] if name==closed else starts[name]
            for time in values:
                row=dict(mode,scenario_id=sid,stage_instance_id=name,request_id=name+'.request',
                    option_id=f'{sid}::{name}@{unit}:{opp}:{time}',start_ms=str(F(time)),end_ms=str(F(time)+F(durations[name])))
                options.append(row)
    condition={'fixture_identity':'K172-handwritten-labels-no-SAFE',
        'condition_sha256':'fixture-condition-not-SAFE','warm_candidate_sha256':'fixture-warm-not-SAFE',
        'opened_by_scene':{sid:[name for name in assigned if name!=closed]},
        'seed_options_by_scene':{sid:seed},'warm_options_by_scene':{sid:warm}}
    return case,condition,options


def run_filter(data,*,options=None,budget=None,scene_ids=None):
    case,condition,original=data
    return FILTER_NS['filter_closed_anchor_options'](case,condition,original if options is None else options,
        budget=make_budget() if budget is None else budget,scene_ids=scene_ids)


def key(row):
    return (row['scenario_id'],row['stage_instance_id'],row['unit_id'],row['opp_id'],F(row['start_ms']))


def legal_tuple(case,rows):
    """Whole-label assignment oracle, separate from closed-anchor rules."""
    by_scene={s['id']:s for s in case['scenarios']}
    for sid,scene in by_scene.items():
        selected=[r for r in rows if r['scenario_id']==sid]
        selected_by_id={r['stage_instance_id']:r for r in selected}
        for i,left in enumerate(selected):
            for right in selected[i+1:]:
                together=(F(left['start_ms'])<F(right['end_ms']) and F(right['start_ms'])<F(left['end_ms']))
                if together and left['unit_id']==right['unit_id']:return False
                if together and left['domain_id']==right['domain_id'] and left['opp_id']!=right['opp_id']:return False
        for before,after in scene['dependencies']:
            if F(selected_by_id[before]['end_ms'])>F(selected_by_id[after]['start_ms']):return False
    return True


class PreparationChecks(unittest.TestCase):
    def test_half_open_fractional_unit_and_domain_boundaries(self):
        data=fixture();kept,_=run_filter(data);keys={key(r) for r in kept}
        k=lambda stage,opp,start:('S1',stage,'CPU2' if stage=='B.pre' else 'NPU0',opp,F(start))
        self.assertIn(k('B.pre','M','0'),keys)
        self.assertNotIn(k('B.pre','H','0'),keys)
        self.assertNotIn(k('B.pre','L','3/2'),keys)
        self.assertIn(k('B.pre','L','2'),keys)
        self.assertIn(k('B.main','H','0'),keys)
        self.assertTrue(any(F(r['end_ms']).denominator!=1 for r in kept))
        same=fixture(same_unit=True);kept,_=run_filter(same)
        starts={F(r['start_ms']) for r in kept if r['stage_instance_id']=='B.pre'}
        self.assertNotIn(F(0),starts);self.assertNotIn(F('3/2'),starts);self.assertIn(F(2),starts)

    def test_direct_predecessor_and_successor_equalities(self):
        for closed in ('B.main','B.pre'):
            with self.subTest(closed=closed):
                data=fixture(closed=closed);kept,_=run_filter(data)
                if closed=='B.main':
                    self.assertTrue(any(r['stage_instance_id']=='B.pre' and F(r['end_ms'])==5 for r in kept))
                    self.assertFalse(any(r['stage_instance_id']=='B.pre' and F(r['end_ms'])>5 for r in kept))
                else:
                    self.assertTrue(any(r['stage_instance_id']=='B.main' and F(r['start_ms'])==F('3/2') for r in kept))
                    self.assertFalse(any(r['stage_instance_id']=='B.main' and F(r['start_ms'])==0 for r in kept))

    def test_original_legal_cartesian_labels_unchanged_and_warm_retained(self):
        totals=[]
        for settings in ({},{'same_unit':True},{'closed':'B.main'},{'closed':'B.pre'}):
            data=fixture(**settings);case,condition,original=data;before=deepcopy(data)
            kept,stats=run_filter(data);retained={key(r) for r in kept}
            dimensions=[[r for r in original if r['stage_instance_id']==s['id']]
                        for s in case['scenarios'][0]['stage_instances']]
            old_legal=set();new_legal=set();seen=0
            for choice in product(*dimensions):
                seen+=1
                if legal_tuple(case,choice):
                    identity=tuple(key(r) for r in choice);old_legal.add(identity)
                    if all(key(r) in retained for r in choice):new_legal.add(identity)
            self.assertTrue(old_legal);self.assertEqual(old_legal,new_legal);self.assertEqual(before,data)
            for stage,warm in condition['warm_options_by_scene']['S1'].items():
                self.assertIn(('S1',stage,warm['unit'],warm['opp'],F(warm['start_ms'])),retained)
            self.assertTrue(stats['complete']);self.assertGreater(stats['removed'],0)
            # An opened warm row must not become a mandatory anchor.
            if not settings:
                self.assertTrue(any(r['stage_instance_id']=='B.main' and r['opp_id']=='M' and F(r['start_ms'])==0 for r in kept))
            totals.append({'settings':settings,'assignments':seen,'legal_before':len(old_legal),'legal_after':len(new_legal)})
        DETAILS.append({'kind':'handwritten_Cartesian_label_equivalence','fixtures':totals,
            'schedule_or_candidate_objects_generated':False,'thermal_status':'NOT_EVALUATED'})

    def test_missing_anchor_empty_open_malformed_rows_and_order(self):
        data=fixture();case,condition,original=data
        kept,stats=run_filter(data)
        original_ids={id(r):i for i,r in enumerate(original)}
        self.assertEqual([original_ids[id(r)] for r in kept],sorted(original_ids[id(r)] for r in kept))
        with self.assertRaises(ValueError):run_filter(data,options=[r for r in original if r['stage_instance_id']!='A.pre'])
        kept,stats=run_filter(data,options=[r for r in original if r['stage_instance_id']!='B.pre'])
        self.assertIn({'scenario_id':'S1','stage_instance_id':'B.pre'},stats['empty_open_stage_option_sets'])
        for field,value in [('end_ms','999'),('duration_ms','999'),('domain_id','NPU'),('stage_instance_id','unknown')]:
            changed=deepcopy(original);changed[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):run_filter(data,options=changed)
        with self.assertRaises(ValueError):run_filter(data,scene_ids=['unknown'])

    def test_same_root_clock_A_150_and_BC_60_caps_without_replenishment(self):
        for arm,slices,overheads in [('A',[150,150],[20,10]),('B',[60,60,60,60],[20,10,15,10]),('C',[60,60,60,60],[20,10,15,10])]:
            root=make_budget();identity=id(root);records=[];absolute=root.deadline
            for index,(cap,overhead) in enumerate(zip(slices,overheads)):
                CLOCK.step(overhead)
                if root.remaining==0:break
                if arm!='A' and index>=2:
                    cap=min(cap,root.remaining/(len(slices)-index))
                slice_end=min(root.deadline,CLOCK()+cap)
                # Simulate export/record overhead after the scene slice begins.
                CLOCK.step(3)
                maximum=max(0,min(slice_end-CLOCK(),root.remaining))
                records.append({'root_id_same':id(root)==identity,'cap':cap,'solver_MaxTime':maximum,
                    'root_remaining':root.remaining,'deadline':root.deadline})
                self.assertLessEqual(maximum,root.remaining);self.assertEqual(root.deadline,absolute)
                CLOCK.step(maximum)
            self.assertTrue(all(r['root_id_same'] for r in records));self.assertEqual(root.deadline,300)
            self.assertLessEqual(sum(r['solver_MaxTime'] for r in records),300)
            DETAILS.append({'kind':'root_clock_simulation','arm':arm,'records':records,
                'not_production_dispatch':True})

    def test_cutoff_keeps_prior_fixture_evidence_and_rejects_late_new_labels(self):
        root=make_budget();initial=root.deadline
        CLOCK.step(299)
        # Lifecycle-only dictionary, explicitly no physical SAFE/U certificate.
        saved={'fixture_witness':'already_formed','formed_at_s':root.elapsed}
        with root.phase('fixture_transport'):
            CLOCK.step(2)
        self.assertEqual(saved['formed_at_s'],299)
        self.assertEqual(root.deadline,initial)
        with self.assertRaises(KERNEL['Exhausted']):root.check()
        self.assertEqual(saved,{'fixture_witness':'already_formed','formed_at_s':299})
        before=deepcopy(fixture())
        with self.assertRaises(KERNEL['Exhausted']):run_filter(before,budget=root)
        self.assertEqual(root.remaining,0)
        DETAILS.append({'kind':'normal_cutoff_lifecycle_fixture','prior_fixture_evidence_retained':True,
            'new_filter_after_cutoff_rejected':True,'new_SAFE_or_U_claim':False})

    def test_original_scene_solve_passes_real_caps_to_fake_transport(self):
        global FAKE_TRANSPORT_CALLS
        records=[]
        def unexpected(*args,**kwargs):
            raise AssertionError('science/candidate branch must not run in no-x fixture')
        class FakeModel:
            def as_solver_dict(self):
                CLOCK.step(2)
                return {'fixture_dictionary_only':True}
        class FakeRecorder:
            pending=None
            def __init__(self,prior=False):
                self.calls=0
                self.best=({'candidate':{'fixture_only_prior':'not_a_research_candidate'},
                    'evaluation':{'safe_upper_bound_J':'FIXTURE_ONLY_NOT_A_PHYSICAL_U'}} if prior else None)
            def poll(self,*args):raise AssertionError('no actual callbacks')
            def begin_request(self):self.calls+=1
            def summary(self):return {'fixture_only':True,'requests':self.calls}
        class FakeSession:
            def __init__(self,advance=1):self.requests=[];self.advance=advance
            def solve(self,payload,**kwargs):
                global FAKE_TRANSPORT_CALLS
                FAKE_TRANSPORT_CALLS+=1
                self.requests.append(dict(kwargs))
                if payload!={'fixture_dictionary_only':True}:raise AssertionError('not a hand fixture payload')
                CLOCK.step(self.advance)
                return {'status':'SOLVED','budget_valid':True,'x':[],'exitflag':0}
        for arm,elapsed,cap,expected in [('A',20,150,148),('A-root-short',220,150,78),
                                         ('B',20,60,58),('C',20,60,58)]:
            root=make_budget();CLOCK.step(elapsed);original_deadline=root.deadline
            session=FakeSession();recorder=FakeRecorder()
            result=SOLVE_NS['_solve_scene'](FakeModel(),session,{},root,recorder,
                feedback_adder=unexpected,witness_validator=unexpected,max_rounds=50,scene_slice_s=cap)
            self.assertEqual(len(session.requests),1)
            request=session.requests[0]
            self.assertIs(request['budget'],root)
            self.assertEqual(request['solver_max_time_s'],expected)
            self.assertLessEqual(request['solver_max_time_s'],request['remaining_s'])
            self.assertEqual(root.deadline,original_deadline)
            self.assertEqual(result['reason'],'NO_INTEGER_CANDIDATE')
            self.assertTrue(result['request_settled']);self.assertIsNone(session.event_consumer)
            if arm=='A':self.assertGreater(request['solver_max_time_s'],60)
            records.append({'arm':arm,'requested_cap':cap,'root_at_entry':300-elapsed,
                'received_solver_MaxTime':request['solver_max_time_s'],'fake_transport_calls':len(session.requests),
                'same_root_object':True,'no_restart_after_no_x':True,'root_deadline':root.deadline})
        # At a real extracted root cutoff, prior lifecycle fixture evidence is
        # copied without invoking an evaluator; no late replacement is formed.
        root=make_budget();CLOCK.step(290);session=FakeSession(advance=8);recorder=FakeRecorder(prior=True)
        result=SOLVE_NS['_solve_scene'](FakeModel(),session,{},root,recorder,
            feedback_adder=unexpected,witness_validator=unexpected,max_rounds=50,scene_slice_s=150)
        self.assertEqual(len(session.requests),1)
        self.assertEqual(session.requests[0]['solver_max_time_s'],8)
        self.assertIs(session.requests[0]['budget'],root)
        self.assertEqual(root.deadline,300)
        self.assertEqual(result['reason'],'wall_time_limit')
        self.assertEqual(result['safe_upper_bound_J'],'FIXTURE_ONLY_NOT_A_PHYSICAL_U')
        self.assertEqual(result['safe_candidate'],{'fixture_only_prior':'not_a_research_candidate'})
        self.assertFalse(result['worker_reusable'])
        self.assertIsNone(session.event_consumer)
        DETAILS.append({'kind':'original_AST_scene_solve_fake_transport','records':records,
            'cutoff_prior_fixture_retained':True,'cutoff_fake_requests':1,
            'ordinary_partial_method_import':False,'fake_transport_calls_are_not_research_solves':True,
            'no_physical_SAFE_or_U':True})

    def test_original_flags_and_archived_R1_R3_fresh_closed_warm_contract(self):
        source=ast.parse(read(BASE/'milp.py'))
        build=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='build_model')
        defaults=dict(zip([a.arg for a in build.args.kwonlyargs],build.args.kw_defaults))
        self.assertIs(ast.literal_eval(defaults['preeliminate_closed_anchors']),False)
        archived=[]
        for n in (1,3):
            folder=BASE/'results'/('p0_execution01' if n==1 else 'p0_resume01')/'calls'/f'base__R{n}'/'anchor_linked4'
            result=json.loads(read(folder/'result.json'))
            first,second=result['phases'];c1,c2=first['condition'],second['condition']
            self.assertEqual(c1['seed_candidate'],c2['seed_candidate'])
            self.assertEqual(c1['seed_candidate_sha256'],c2['seed_candidate_sha256'])
            self.assertEqual(len(result['seed_attempts']),1)
            self.assertEqual(result['seed_attempts'][0]['construction']['candidate'],c1['seed_candidate'])
            self.assertFalse(result['candidate_and_cache_shared_between_calls'])
            self.assertEqual(result['timing']['limit_s'],300)
            self.assertEqual(c2['warm_candidate_sha256'],result['linked_record_contract']['closed_anchor_candidate_sha256'])
            self.assertEqual(canonical(c2['warm_candidate']),c2['warm_candidate_sha256'])
            closed=[]
            for sid,rows in c2['warm_options_by_scene'].items():
                for stage,warm in rows.items():
                    self.assertEqual(warm['unit'],c2['seed_options_by_scene'][sid][stage]['unit'])
                    if stage not in c2['opened_by_scene'][sid]:
                        closed.append({'scene_id':sid,'stage_id':stage,**warm})
                self.assertEqual(len(c2['opened_by_scene'][sid]),4)
                self.assertEqual(len(c1['opened_by_scene'][sid]),2)
            archived.append({'case_id':f'base__R{n}','fresh_seed_sha256':c1['seed_candidate_sha256'],
                'warm_full_candidate_sha256':c2['warm_candidate_sha256'],
                'warm_committed_at_s':result['linked_record_contract']['closed_anchor_committed_at_s'],
                'closed_rows':closed,'original_input_read_only':True,
                'future_ablation_requires_fresh_seed_per_call':True})
        DETAILS.append({'kind':'archived_R1_R3_contract','records':archived,
            'scope':'old record identities only, not future equal outcome or free warm initialization'})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if args.out.exists():raise FileExistsError('refuse overwrite: '+str(args.out))
    args.out.mkdir(parents=True,exist_ok=False)
    read(Path(__file__))
    # Old test files are read for provenance only; never imported or executed.
    read(BASE/'test_anchor_preelimination.py');read(BASE/'test_linked_neighborhood.py')
    sys.addaudithook(audit);sys.setprofile(profile)
    try:
        prepare_extractions()
        stream=io.StringIO()
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(PreparationChecks))
    finally:sys.setprofile(None)
    after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in READS}
    report={'protocol':'K172-anchor-label-and-root-clock-AST-only-precheck-v1',
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'guard':{**GUARD,'all_zero':not any(GUARD.values()),'builds':0,'solves':0,
            'thermal_evaluations':0,'formal_candidate_generation':0,'research_calls':0},
        'source_and_archive_before_sha256':READS,'source_and_archive_after_sha256':after,
        'sources_and_original_archives_unchanged':READS==after,'details':DETAILS,
        'fake_transport_calls':FAKE_TRANSPORT_CALLS,
        'scope':'Handwritten finite labels, AST-extracted label rules/budget classes and original R1/R3 identities only; receipt identity stub; no matrix equivalence, SAFE/U or speed claim',
        'passed':result.wasSuccessful() and not any(GUARD.values()) and READS==after}
    (args.out/'unittest.txt').write_text(stream.getvalue(),encoding='utf-8')
    (args.out/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('passed','tests_run','failures','errors','guard')},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
