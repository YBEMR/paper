"""Bounded complete-domain/state/physical checks for certified state pruning.

The physical fixture keeps every original R1 Stage, both scenarios and original
physical data. Only its declared mode/start subdomain is small. No solver runs.
Use freeze before run; no retry or automatic full-R1 build is provided.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import argparse
import hashlib
from itertools import product
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ARCH = REPO/'research/chapter3_support_autol_lp_20261111/autol_build/rev02'
SOURCES = [HERE/'milp.py', HERE/'joint_state_support.py', HERE/'option_support.py',
           HERE/'thermal.py', HERE/'schedules.py', Path(__file__).resolve()]
now = lambda: datetime.now(timezone.utc).isoformat()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')


def make_fixture():
    original = read(ARCH/'input_instance.json')
    case = deepcopy(original)
    seed = read(REPO/'research/chapter3_native_log_review_20261111/github_verified_run01/raw/local_records/r1_pair_run01/off/method/result.json')['safe_candidate']
    choices, starts = {}, {}
    for scene in original['scenarios']:
        sid = scene['id']; stages = {s['id']:s for s in scene['stage_instances']}
        starts[sid] = {}
        for row in seed['scenes'][sid]:
            shared = stages[row['stage_id']]['shared_stage_id']
            selected = (row['unit'], row['opp'])
            if shared in choices: assert choices[shared] == selected
            choices[shared] = selected
            starts[sid][row['stage_id']] = (['10','15'] if shared=='A.main'
                else ['40','45'] if shared=='A.post' else [row['start_ms']])
    for shared, modes in case['stage_modes'].items():
        allowed = {choices[shared]}
        if shared=='C.post': allowed.add(('CPU1','L'))
        case['stage_modes'][shared] = [m for m in modes if (m['unit_id'],m['opp_id']) in allowed]
    case['id'] = 'fixture_certified_joint_full12_small_domain'
    case['fixture_scope'] = 'All original 12 Stage executions and physical data; mode/start restrictions for exhaustive validation only'
    case['start_domain'] = {'version':1,'kind':'explicit_grid_subset','by_scene_stage_ms':starts}
    # No scientific scalar, stage/dependency, scenario or entry is changed.
    for key in original:
        if key not in ('id','stage_modes'): assert original[key] == case[key], key
    for shared, modes in case['stage_modes'].items():
        assert all(m in original['stage_modes'][shared] for m in modes)
    return case, read(ARCH/'input_config.json')


def assignments(case):
    dimensions=[]
    for scene in case['scenarios']:
        sid=scene['id']
        for stage in scene['stage_instances']:
            modes=case['stage_modes'][stage['shared_stage_id']]
            choices=[]
            for mode in modes:
                for start in case['start_domain']['by_scene_stage_ms'][sid][stage['id']]:
                    choices.append((sid,dict(stage_id=stage['id'],unit=mode['unit_id'],opp=mode['opp_id'],start_ms=start)))
            dimensions.append(choices)
    for selected in product(*dimensions):
        candidate={'scenes':{s['id']:[] for s in case['scenarios']}}
        for sid,row in selected: candidate['scenes'][sid].append(row)
        yield candidate


def identity(candidate):
    return json.dumps(candidate, sort_keys=True, separators=(',',':'))


def independent_legal(case, candidate):
    """Full direct exact legality; does not call production support/checkers."""
    units={u['id']:u for u in case['platform']['units']}; deployment={}; out={}
    for scene in case['scenarios']:
        sid=scene['id']; stages={s['id']:s for s in scene['stage_instances']}
        supplied=candidate['scenes'][sid]
        if len(supplied)!=len(stages) or {r['stage_id'] for r in supplied}!=set(stages):return False,{}
        requests={r['id']:r for r in scene['requests']}; selected={}
        for row in supplied:
            stage=stages[row['stage_id']]; shared=stage['shared_stage_id']
            modes=[m for m in case['stage_modes'][shared] if (m['unit_id'],m['opp_id'])==(row['unit'],row['opp'])]
            if len(modes)!=1:return False,{}
            mode=modes[0]; start=F(row['start_ms']); end=start+F(mode['duration_ms']); request=requests[stage['request_id']]
            if F(mode['duration_ms'])<=0 or start<F(request['release_ms']) or end>min(F(request['deadline_ms']),F(case['window_ms'])):return False,{}
            if (start/F(case['start_grid_ms'])).denominator!=1:return False,{}
            if row['start_ms'] not in case['start_domain']['by_scene_stage_ms'][sid][row['stage_id']]:return False,{}
            if shared in deployment and deployment[shared]!=row['unit']:return False,{}
            deployment[shared]=row['unit']; selected[row['stage_id']]=dict(row,start=start,end=end)
        if any(selected[a]['end']>selected[b]['start'] for a,b in scene['dependencies']):return False,{}
        rows=list(selected.values())
        for i,a in enumerate(rows):
            for b in rows[i+1:]:
                if max(a['start'],b['start'])>=min(a['end'],b['end']):continue
                if a['unit']==b['unit']:return False,{}
                if units[a['unit']]['domain_id']==units[b['unit']]['domain_id'] and a['opp']!=b['opp']:return False,{}
        out[sid]=rows
    return True,out


def independent_state(case, selected, sid, left):
    units={u['id']:u for u in case['platform']['units']}
    active=[r for r in selected[sid] if r['start']/1000<=left<r['end']/1000]
    result=[]
    for domain in case['platform']['domains']:
        opps={r['opp'] for r in active if units[r['unit']]['domain_id']==domain}
        assert len(opps)<=1
        result.append(next(iter(opps)) if opps else 'L')
    return tuple(result)


def scientific(value):
    if isinstance(value,dict):return {k:scientific(v) for k,v in value.items() if k not in {'elapsed_s','completed_at_elapsed_s','formed_at_elapsed_s'}}
    if isinstance(value,list):return [scientific(v) for v in value]
    return value


def canonical_row(model,row):
    return (row['tag'],tuple(sorted((model.names[i],a) for i,a in row['coef'].items())),
        row['rhs'],row.get('rounding_allowance'),tuple(row.get('rhs_interval',())),row.get('big_M'))


def freeze(output):
    output.mkdir(parents=True,exist_ok=False)
    case,config=make_fixture(); save(output/'fixture.json',case);save(output/'config.json',config)
    population=list(assignments(case)); assert len(population)==32
    save(output/'plan.json',dict(frozen_utc=now(),reference_commit='9d972848adee5db8351d8f3be9638319bf0331d3',
        source_sha256={str(p.relative_to(REPO)):sha(p) for p in SOURCES},
        fixture_sha256=sha(output/'fixture.json'),config_sha256=sha(output/'config.json'),
        fixture_cartesian=32,maximum_cartesian=96,maximum_thermal_calls=64,total_budget_s=240,per_thermal_call_s=10,
        full_original_R1_builds=0,full_original_R1_solver_calls=0,retry=False,
        physical_data_changed=False,fixture_only_mode_and_start_restrictions=True))


def run(output):
    global RECORD, MODELS, CASE, CONFIG, BUDGET, START, OUT
    OUT=output; plan=read(output/'plan.json')
    for name,dig in plan['source_sha256'].items():assert sha(REPO/name)==dig,name
    assert sha(output/'fixture.json')==plan['fixture_sha256'] and sha(output/'config.json')==plan['config_sha256']
    import milp, joint_state_support
    from thermal import Budget
    import scipy.optimize as opt
    def forbidden(*a,**kw):raise AssertionError('PROHIBITED_SOLVER_CALL')
    opt.linprog=forbidden;opt.milp=forbidden
    CASE=read(output/'fixture.json');CONFIG=read(output/'config.json');START=time.monotonic();BUDGET=Budget(seconds=240)
    RECORD=dict(started_utc=now(),thermal_calls=0,model_builds=0,solver_calls=0,fixtures={})
    flags=read(ARCH/'plan.json')['baseline_flags']; flags['propagate_support']=True
    class Tests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            global MODELS
            MODELS=[]
            for side in (False,True):
                BUDGET.check();RECORD['model_builds']+=1
                MODELS.append(milp.build_model(CASE,CONFIG,budget=BUDGET,prune_joint_states=side,**flags))
            save(OUT/'model_summaries.json',[m.summary() for m in MODELS])
            save(OUT/'pruning_report.json',MODELS[1].preprocessing['joint_state_pruning'])

        def test_01_same_options_events_boxes_and_surviving_physical_rows(self):
            old,new=MODELS; self.assertEqual(old.options,new.options);self.assertEqual(old.instance,new.instance)
            for sid in old.scenes:self.assertEqual(old.scenes[sid]['events'],new.scenes[sid]['events'])
            oldbounds={n:(old.lb[i],old.ub[i]) for i,n in enumerate(old.names)}
            for i,n in enumerate(new.names):self.assertEqual((new.lb[i],new.ub[i]),oldbounds[n],n)
            oldphysical=Counter(canonical_row(old,r) for r in old.rows if r['tag'].split('/')[0] in ['thermal_propagation','complete_energy'])
            newphysical=Counter(canonical_row(new,r) for r in new.rows if r['tag'].split('/')[0] in ['thermal_propagation','complete_energy'])
            self.assertTrue(newphysical);self.assertFalse(newphysical-oldphysical)
            self.assertLess(sum(newphysical.values()),sum(oldphysical.values()))
            RECORD['same_surviving_physical_rows']=True;RECORD['same_original_boxes']=True

        def test_02_complete_sets_states_and_physical_receipts(self):
            old,new=MODELS;all_candidates=list(assignments(CASE));self.assertEqual(len(all_candidates),32)
            before=[];after=[];receipts=[];full=[];projections=0
            for ordinal,candidate in enumerate(all_candidates):
                BUDGET.check();legal,selected=independent_legal(CASE,candidate)
                item=dict(candidate=candidate,independent_legal=legal)
                if not legal:full.append(item);continue
                key=identity(candidate);before.append(key);admitted=True
                for sid,meta in old.scenes.items():
                    for l,left in enumerate(meta['events'][:-1]):
                        state=independent_state(CASE,selected,sid,left);projections+=1
                        self.assertIn(state,meta['states'][l]);admitted &= state in new.scenes[sid]['states'][l]
                self.assertTrue(admitted);after.append(key)
                values=[]
                for side,model in zip(['OFF','ON'],MODELS):
                    BUDGET.check();self.assertLess(RECORD['thermal_calls'],64);RECORD['thermal_calls']+=1
                    remaining=240-(time.monotonic()-START);self.assertGreater(remaining,0)
                    value=milp.evaluate_model_candidate(model,candidate,None,Budget(seconds=min(10,remaining)))
                    save(OUT/f'physical_{ordinal:03d}_{side}.json',value);values.append(value)
                self.assertEqual(scientific(values[0]),scientific(values[1]))
                self.assertEqual(values[0]['state'],'SAFE')
                self.assertTrue(all(F(v['covered_until_s'])==F(2,5) for v in values[0]['scenes'].values()))
                item.update(retained_state_projection=admitted,physical_state=values[0]['state'],
                    weighted_energy_J=values[0]['weighted_energy_J']);full.append(item)
            self.assertTrue(before);self.assertEqual(before,after)
            save(OUT/'complete_candidate_sets.json',dict(candidates=full,legal_before=before,legal_after=after))
            RECORD.update(cartesian=32,legal_before=len(before),legal_after=len(after),state_projections=projections,
                complete_legal_sets_equal=True,all_physical_scientific_fields_equal=True)

        def test_03_default_off_and_input_guards(self):
            with patch.object(milp,'Model') as constructor:
                for bad in [0,1,None,'false',[]]:
                    with self.assertRaises(ValueError):milp.build_model(CASE,CONFIG,prune_joint_states=bad)
                constructor.assert_not_called()
            oldcase=deepcopy(CASE);oldconfig=deepcopy(CONFIG)
            for x in [oldcase,oldconfig]:
                x['execution_rules']['idle_holds_last_opp']=True
                x['execution_rules'].pop('idle_policy');x['execution_rules'].pop('idle_delay_ms')
            with self.assertRaises(ValueError):milp.build_model(oldcase,oldconfig,prune_joint_states=True,budget=BUDGET)
            # Compare current default-off with the exact frozen pre-feature code.
            namespace={'__name__':'pruning_pre_feature','__file__':str(HERE/'milp.py')}
            source=(ARCH/'frozen/research/chapter3_experiments/milp.py').read_bytes();exec(compile(source,'frozen_milp.py','exec'),namespace)
            models=[]
            for build in [namespace['build_model'],milp.build_model]:
                RECORD['model_builds']+=1;models.append(build(CASE,CONFIG,budget=BUDGET,include_physics=False,**flags))
            for attr in ['names','rows','bounds','c','lb','ub','integer','options']:
                self.assertEqual(getattr(models[0],attr),getattr(models[1],attr),attr)
            RECORD['default_off_matches_frozen']=True

        def test_04_gate_zero_rejects_any_exact_positive_violation(self):
            rows=[dict(coef={0:1.,1:2.},rhs=1.,tag='test')]
            value=joint_state_support.verify_gate_off_rows(rows,[0.,0.],[1.,1.],1)
            self.assertTrue(value)
            rows[0]['rhs']=float.fromhex('0x1.fffffffffffffp-1')
            with self.assertRaises(ValueError):joint_state_support.verify_gate_off_rows(rows,[0.,0.],[1.,1.],1)
            RECORD['gate_off_exact_negative_case_rejected']=True

        def test_05_caps_numeric_path_and_onehot_fail_closed(self):
            scene=dict(id='pure',dependencies=[['p','q']])
            op=lambda stage,unit,domain:dict(stage_instance_id=stage,unit_id=unit,domain_id=domain,opp_id='H')
            p,q=op('p','CPU1','CPU'),op('q','GPU0','GPU')
            groups={'p':[(p,0)],'q':[(q,1)]}
            rows=[dict(coef={0:1.},rhs=1.),dict(coef={0:-1.},rhs=-1.),
                  dict(coef={1:1.},rhs=1.),dict(coef={1:-1.},rhs=-1.),
                  dict(coef={0:2.,1:-1.},rhs=0.)]
            def context(data):return joint_state_support.SceneSupport(scene,groups,{'p':(0,1),'q':(2,3)},
                {('p','q'):4},data,[0,1],[(F(0),F(1))]*2,budget=BUDGET)
            states=[('H','H'),('L','L')]; active=[(p,0),(q,1)]
            kept,proof=joint_state_support.filter_interval(context(rows),active,['CPU','GPU'],states,0,cap=0)
            self.assertEqual(kept,states);self.assertEqual(proof['status_counts'],{'UNKNOWN_CAP':2})
            ctx=context(rows);kept,proof=joint_state_support.filter_interval(ctx,active,['CPU','GPU'],states,0)
            self.assertEqual(kept,[('L','L')]);self.assertEqual(proof['deleted_count'],1)
            path=next(iter(ctx.report['certificate_catalogue'].values()))
            self.assertEqual(F(path['strict_margin']),1);self.assertTrue(path['exceeds_path_row_tolerance'])
            weak=deepcopy(rows);weak[-1]['rhs']=1.
            kept,proof=joint_state_support.filter_interval(context(weak),active,['CPU','GPU'],states,0)
            self.assertEqual(kept,states)
            tampered=deepcopy(rows);tampered[0]['rhs']=float.fromhex('0x1.0000000000001p+0')
            with self.assertRaises(ValueError):context(tampered)
            tiny=deepcopy(rows);tiny[-1]['rhs']=1.-2**-40
            ctx=context(tiny);kept,_=joint_state_support.filter_interval(ctx,active,['CPU','GPU'],states,0)
            self.assertEqual(kept,[('L','L')])
            self.assertFalse(next(iter(ctx.report['certificate_catalogue'].values()))['exceeds_path_row_tolerance'])
            RECORD['pure_numeric_cases']={'caps_keep_unknown':True,'zero_margin_kept':True,
                'tampered_onehot_rejected':True,'tiny_positive_exact_margin_distinct_from_solver_tolerance':True}

        def test_06_original_gate_zero_and_new_energy_cuts_exact_audit(self):
            old,new=MODELS
            retained={name for name in new.names if name.startswith('w:')}
            deleted={i for i,name in enumerate(old.names) if name.startswith('w:') and name not in retained}
            gate_checks=[]
            for i,row in enumerate(old.rows):
                if row['tag'].split('/')[0] not in ['thermal_propagation','complete_energy']:continue
                gates=set(row['coef'])&deleted
                if not gates:continue
                self.assertEqual(len(gates),1);gate=next(iter(gates));maximum=F(0)
                for j,a in row['coef'].items():
                    if j!=gate:maximum+=F.from_float(a)*F.from_float(old.ub[j] if a>=0 else old.lb[j])
                margin=F.from_float(row['rhs'])-maximum
                self.assertGreaterEqual(margin,0)
                gate_checks.append(dict(row=i,gate=old.names[gate],margin=str(margin)))
            self.assertEqual(len(gate_checks),10*len(deleted));self.assertTrue(gate_checks)
            cut_checks=[]
            for cert in new.energy_bound_certificates:
                gates=cert['gates'];cut=new.rows[cert['cut_row']]
                self.assertEqual(len(cert['source_rows']),len(gates))
                for index,sign in zip(cert['onehot_rows'],[1.,-1.]):
                    self.assertEqual(new.rows[index]['coef'],{g:sign for g in gates})
                    self.assertEqual(new.rows[index]['rhs'],sign)
                self.assertEqual(set(gates),{new.scenes[cert['scene']]['joint'][cert['interval'],s]
                    for s in new.scenes[cert['scene']]['states'][cert['interval']]})
                for gate,source in zip(gates,cert['source_rows']):
                    row=new.rows[source];self.assertEqual(row['tag'],'complete_energy/lower')
                    # With the chosen gate=1, compare cut residual against its
                    # source lower-energy residual over the exact binary64 box.
                    diff=F.from_float(cut['coef'].get(gate,0.))-F.from_float(cut['rhs'])
                    diff-=F.from_float(row['coef'].get(gate,0.))-F.from_float(row['rhs'])
                    for j in cert['sources']:
                        a=F.from_float(cut['coef'].get(j,0.))-F.from_float(row['coef'].get(j,0.))
                        diff+=a*F.from_float(new.ub[j] if a>=0 else new.lb[j])
                    self.assertLessEqual(diff,0)
                    cut_checks.append(dict(scene=cert['scene'],interval=cert['interval'],
                        gate=new.names[gate],cut_row=cert['cut_row'],source_row=source,maximum_difference=str(diff)))
            save(OUT/'exact_gate_zero_and_energy_cuts.json',dict(gate_rows=gate_checks,cut_checks=cut_checks))
            RECORD['deleted_gate_zero_rows_checked']=len(gate_checks)
            RECORD['new_energy_cut_active_state_checks']=len(cut_checks)

        def test_07_production_gate_off_failure_never_returns_model(self):
            RECORD['model_builds']+=1
            with patch.object(joint_state_support,'verify_gate_off_rows',side_effect=ValueError('deliberate strict audit failure')):
                with self.assertRaisesRegex(ValueError,'deliberate strict audit failure'):
                    milp.build_model(CASE,CONFIG,budget=BUDGET,prune_joint_states=True,**flags)
            RECORD['production_audit_failure_closed']=True

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    for name,dig in plan['source_sha256'].items():assert sha(REPO/name)==dig,name
    RECORD.update(ended_utc=now(),wall_s=time.monotonic()-START,passed=result.wasSuccessful(),
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        source_hashes_unchanged=True,full_original_R1_model_builds=0,full_original_R1_solver_calls=0)
    save(output/'results.json',RECORD);print(json.dumps(RECORD,indent=2));return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    if args.action=='freeze':freeze(args.output)
    else:raise SystemExit(run(args.output))
