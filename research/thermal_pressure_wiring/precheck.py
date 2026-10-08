"""K.30 wiring fixtures and injected boundary cases; not a TP-1 study run."""
from copy import deepcopy
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
import argparse
import itertools
import traceback
import wiring as w
a=w.a


def fixture():
    b=a.bundle(a.load(),'a_c','b_c');b['id']='wiring_fixture_not_TP1_candidate'
    for mode,p in b['candidate']['fixed_plans'].items():
        p.update(period_us=4000,relative_deadline_us=3000,minimum_switch_interval_us=8000)
        p['stages']=[dict(id=mode+'0',predecessors=[],offset_us=0,unit='C0',opp='L',duration_us=1000,activity_increment_W=1)]
    for path,cut in zip(b['evaluation']['paths'],[8000,9000]):
        path['trace']['switch_requests'][0]['time_us']=cut;path['trace']['window_us']=16000
    c=a.joint.safety_input(b);_,possible=a.v2.domain_info(c);units,choices=a.v2.fragment_options(c,possible)
    b['safety']['fragment_superset']=[dict(held_opps={u:v[0] for u,v in zip(units,k)},activity_W={u:v[1] for u,v in zip(units,k)}) for k in itertools.product(*choices)]
    return b


def run(dest):
    dest.mkdir(parents=True,exist_ok=False);checks=[];artifacts={};before=w.identities();b=fixture()
    def check(name,ok,detail=None):checks.append(dict(name=name,passed=bool(ok),detail=detail))
    def section(name,fn):
        try:fn()
        except Exception:check(name,False,traceback.format_exc())
    def expired_at(name):
        def hook(actual):
            if actual==name:raise a.v1.Exhausted('injected_'+name)
        return a.v2.Budget(seconds=20,hook=hook)
    def actual():
        r=w.evaluate_bundle(b);artifacts['fixture_full']=r
        check('full_certified',r['status']=='certified_candidate',r.get('reason'))
        check('new_code_bound','wired_sources' in r['binding'])
        check('old_globals_unchanged',a.v1.evaluate_trace.__globals__['thermal'] is a.v1.thermal and a.joint.evaluate_bundle.__globals__['v1'] is a.v1)
        for path in b['evaluation']['paths']:
            tid=path['trace']['id'];cut=path['trace']['switch_requests'][0]['time_us']
            pre=w.local_score(b,'A_prefix',path=path)
            ref=w.local_score(b,'B_reference',horizon_us=16000-cut)
            artifacts[tid+'_prefix']=pre;artifacts[tid+'_reference']=ref
            check(tid+'_local_safe',pre['status']==ref['status']=='safe_reference')
            check(tid+'_prefix_not_U1',pre['role']=='local_reference_only_not_U1_or_sustained_certificate' and 'certified_candidate_energy' not in pre)
            attr=w.attribution(pre,ref,r,tid);artifacts[tid+'_attribution']=attr
            check(tid+'_energy_identity',attr['status']=='consistent',attr)
            bad=deepcopy(pre);bad['binding']={'wrong':True}
            check(tid+'_identity_mismatch',w.attribution(bad,ref,r,tid)['status']=='identity_mismatch')
            bad=deepcopy(pre);bad['boundary']['held_opps']['C0']='H'
            check(tid+'_boundary_mismatch',w.attribution(bad,ref,r,tid)['status']=='nonthermal_boundary_mismatch')
        path=a.single_mode_path(b,'B');path['trace']['window_us']=16000
        pr=w.evaluate_probe(b,path);artifacts['B_probe']=pr
        check('B_probe_correct_entry',pr['status']=='finite_safe' and pr['membership'][0]['matching_entry_blocks']!=[0])
        check('probe_no_U1','certified_candidate_energy' not in pr and pr['scope']=='finite_counterexample_probe_not_U1')
        # Continuous physical segment split in reference attribution includes idle tail.
        trace=r['finite_path_energy']['traces']['F1']
        check('complete_window_preserved',F(trace['thermal']['covered_until_us'])==16000)
        check('energy_two_paths_weighted',r['finite_path_energy']['aggregate']['status']=='valid')
        artscore=w.combine_scores([artifacts['F1_prefix'],artifacts['F2_prefix']],[F(1,2),F(1,2)])
        check('local_weighted_score',artscore['status']=='available')
        bad=deepcopy(artifacts['F2_prefix']);bad['binding']={'different_candidate':True}
        check('mixed_candidate_scores_rejected',w.combine_scores([artifacts['F1_prefix'],bad],[F(1,2),F(1,2)])['status']=='identity_mismatch')
        check('mixed_score_roles_rejected',w.combine_scores([artifacts['F1_prefix'],artifacts['F1_reference']],[F(1,2),F(1,2)])['status']=='identity_mismatch')
    def injected():
        safe=deepcopy(artifacts['fixture_full']['finite_path_energy']['traces']['F1'])
        violated=deepcopy(safe);violated.update(rankable_energy=False)
        violated['thermal'].update(status='violation',complete=False,known_violations=[dict(node='NPU',lower_temperature_C='81',limit_C='80',witness_time_s='0')])
        path=a.single_mode_path(b,'B');path['trace']['window_us']=16000
        probe=w.clone(w.evaluate_probe,evaluate_trace=lambda *args:deepcopy(violated))
        r=probe(b,path,expired_at('probe_returned'));artifacts['injected_probe_late']=r
        check('late_probe_retains_violation',r['status']=='violation' and r['known_violations'] and 'result' not in r)
        safeprobe=w.clone(w.evaluate_probe,evaluate_trace=lambda *args:deepcopy(safe))
        r=safeprobe(b,path,expired_at('probe_returned'))
        check('late_safe_probe_no_energy',r['status']=='unresolved' and 'result' not in r)
        bad=deepcopy(path);bad['entry_state']['actual_mode']='A'
        r=safeprobe(b,bad)
        check('wrong_entry_rejected',r['status']=='invalid')
        # Force an internal thermal receipt, then interrupt the local receiver.
        fake_s=SimpleNamespace(thermal=lambda *args:deepcopy(violated['thermal']))
        local=w.clone(w.local_score,s=fake_s)
        r=local(b,'A_prefix',path=b['evaluation']['paths'][0],budget=expired_at('local_thermal_returned'))
        check('local_late_violation_preserved',r['status']=='reference_violation' and 'score_J' not in r and 'diagnostic_energy_J' not in r)
        for status in ['reference_violation','unresolved','invalid']:
            check('unscored_'+status,w.combine_scores([{'status':status},artifacts['F1_prefix']],[F(1,2),F(1,2)])['status']=='unavailable')
        # Same joint control flow, synthetic receipts explicitly identified.
        v1=SimpleNamespace(**dict(vars(a.v1),evaluate_trace=lambda *args:deepcopy(violated)))
        joint=w.clone(w._joint,v1=v1)
        r=joint(b,expired_at('path_returned'));artifacts['injected_joint_conflict']=r
        check('joint_late_committed_conflict',r['status']=='evidence_conflict' and r['path_violation_receipts'] and r['certified_candidate_energy']['status']=='unavailable')
        unfinished=deepcopy(safe);unfinished['rankable_energy']=False;unfinished['thermal']=dict(status='unresolved',complete=False,known_violations=[])
        v1=SimpleNamespace(**dict(vars(a.v1),evaluate_trace=lambda *args:deepcopy(unfinished)))
        joint=w.clone(w._joint,v1=v1)
        r=joint(b,a.v2.Budget(seconds=20))
        check('unfinished_path_not_aggregated',r['certified_candidate_energy']['status']=='unavailable')
        v1=SimpleNamespace(**dict(vars(a.v1),evaluate_trace=lambda *args:deepcopy(safe)))
        for point in ['energy_ready','before_assembly','before_commit']:
            r=w.clone(w._joint,v1=v1)(b,expired_at(point))
            check('budget_'+point,r['certified_candidate_energy']['status']=='unavailable')
        narrow=deepcopy(b);narrow['safety']['certificate_box_C']=[[25,35],[25,35]]
        r=w.clone(w._joint,v1=v1)(narrow,a.v2.Budget(seconds=20))
        check('finite_safe_certificate_unresolved',r['status']=='unresolved' and r['certified_candidate_energy']['status']=='unavailable')
        old=deepcopy(b);old['safety']['witness_requests']=[{'time_us':8000,'to_mode':'B'}]
        try:w.evaluate_bundle(old)
        except ValueError:check('legacy_first_entry_replay_blocked',True)
        else:check('legacy_first_entry_replay_blocked',False)
        b0=expired_at('local_start');r=w.local_score(b,'A_prefix',path=b['evaluation']['paths'][0],budget=b0)
        check('caller_budget_no_restart',r.get('budget_status')=='exhausted' and 'score_J' not in r)
    for name,fn in [('actual_fixture',actual),('injected_boundaries',injected)]:section(name,fn)
    check('sources_unchanged',w.identities()==before)
    out=dict(stage='K.30',scope='synthetic wiring fixture; injected records are not physical evidence',passed=all(c['passed'] for c in checks),checks=checks,fixture=b,artifacts=artifacts,hashes=before,formal_diagnostic_runs=0)
    a.old.write(dest/'result.json',out)
    print(sum(c['passed'] for c in checks),len(checks))
    for c in checks:
        if not c['passed']:print(c['name'],c['detail'])
    return out['passed']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args();raise SystemExit(0 if run(Path(args.out)) else 1)
