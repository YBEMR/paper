"""Necessary exact algebra, execution and evidence-boundary checks; no thermal run."""
from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
import hashlib
import json

import certificate as c
a = c.a


def run():
    checks, evidence = [], {}
    def ck(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
    def budget_at(name, error=None):
        def hook(point):
            if point == name:
                raise error if error is not None else a.v2.Exhausted('injected:' + point)
        return a.v2.Budget(seconds=20, hook=hook)

    b = c.expected_bundle(); scope = a.joint.safety_input(b); sem = b['candidate']['semantics']
    proof = c.verify_pulse(scope, sem)
    evidence['pulse'] = proof
    ck('approved_fixed_scope_certifies', proof['status'] == 'sustained_safe')
    t = proof.get('thermal_certificate', {})
    ck('CPU_exact_bound', F(t['CPU_temperature_upper_C']) == F(25)+F(3255,206))
    ck('NPU_exact_bound', F(t['NPU_temperature_upper_C']) == F(9996419,125829))
    ck('strict_limits', F(t['CPU_temperature_upper_C']) < 41 and F(t['NPU_temperature_upper_C']) < F(79445,1000))
    ck('pulse_and_gap', F(t['maximum_pulse_s']) == F(1,1000) and F(t['minimum_start_gap_s']) == F(13,800))
    ck('CPU_activity_envelope', F(t['CPU_activity_rho_W']) == F(15,32) and F(t['CPU_activity_burst_J']) == F(1,40))
    ck('all_four_initial_blocks', len(scope['initial_states']) == 4 and len({(s['actual_mode'],s['held_opps']['C0']) for s in scope['initial_states']}) == 4)
    ck('deadline_both_edges', all(F(e['slack_us']) == 6750 for e in proof['deadline']['edge_checks']))

    mutations = [
        ('activity', lambda x: x['fixed_plans']['A']['stages'][1].update(activity_increment_W=2)),
        ('duration', lambda x: x['fixed_plans']['A']['stages'][1].update(duration_us=1250)),
        ('offset', lambda x: x['fixed_plans']['A']['stages'][1].update(offset_us=250)),
        ('period', lambda x: x['fixed_plans']['A'].update(period_us=21000)),
        ('switch_interval', lambda x: x['fixed_plans']['A'].update(minimum_switch_interval_us=41000)),
        ('thermal_capacity', lambda x: x['platform']['C_J_per_K'].__setitem__(1,F(1,40000))),
        ('thermal_coupling', lambda x: x['platform'].update(G_W_per_K=[[F(105,1000),F(-4,1000)],[F(-4,1000),F(20,1000)]])),
        ('leak', lambda x: x['platform']['opps']['N0']['H'].update(leak_W_per_K=F(3,1000))),
        ('idle', lambda x: x['platform']['opps']['C0']['L'].update(base_W=F(16,100))),
        ('limit', lambda x: x['platform']['temperature_limit_C'].__setitem__(1,79)),
        ('initial_temperature', lambda x: x['initial_states'][0].update(temperature_box_C=[[30,36],[30,35]])),
        ('missing_initial_block', lambda x: x['initial_states'].pop()),
        ('extra_initial_block', lambda x: x['initial_states'].append(deepcopy(x['initial_states'][0]))),
        ('initial_phase', lambda x: x['initial_states'][0].update(phase_us=1)),
        ('unfinished_work', lambda x: x['initial_states'][0].update(unfinished_work=[{'stage':'A0'}])),
        ('float', lambda x: x['platform']['C_J_per_K'].__setitem__(0,0.02)),
    ]
    for name, mutate in mutations:
        x=deepcopy(scope); mutate(x)
        r=c.verify_pulse(x,sem)
        ck('reject_changed_'+name,r['status'] in ['unresolved','input_invalid'] and 'thermal_certificate' not in r)
    changed=deepcopy(sem); changed['extra_preparation_us']=1
    ck('reject_changed_preparation',c.verify_pulse(scope,changed)['status']!='sustained_safe')
    changed=deepcopy(scope); changed['certificate_box_C']=[[25,60],[25,60]]
    ck('proof_does_not_expand_or_use_box',c.verify_pulse(changed,sem)['status']=='sustained_safe')
    for point in ['pulse_start','pulse_scope_checked','pulse_bounds_ready','before_pulse_commit']:
        r=c.verify_pulse(scope,sem,budget_at(point))
        ck('timeout_'+point,r['status']=='unresolved' and 'thermal_certificate' not in r and r['budget_status']=='exhausted')
    r=c.verify_pulse(scope,sem,budget_at('pulse_bounds_ready',MemoryError('fixture')))
    ck('resource_no_certificate',r['status']=='unresolved' and 'thermal_certificate' not in r)
    with patch.object(c,'INPUT_SHA','0'*64):
        r=c.verify_pulse(scope,sem)
    ck('changed_input_hash_not_certified',r['status']=='unresolved')

    # Explicit exact phases around releases, stage ends and drain completion.
    # These are execution fixtures, not another F1/F2 energy/thermal experiment.
    execution=[]
    phases=[F(0),F(1,4),F(1000),F(2000),F(3500),F(3750),F(19999)+F(3,4)]
    for initial in ['A','B']:
        for phase in phases:
            times=[F(40000)+phase,F(80000)+phase,F(160000)+phase]
            modes=['B','A','B'] if initial=='A' else ['A','B','A']
            tr=dict(id='execution_fixture',initial_mode=initial,initial_release_us=0,
                    initial_temperature_C=[30,30],initial_opps={'C0':'H','N0':'H'},
                    initial_unfinished_work=[],switch_requests=[dict(time_us=t,to_mode=m) for t,m in zip(times,modes)],
                    window_us=times[-1]+34000)
            budget=a.v2.Budget(seconds=20)
            rows,req,releases,failure=a.v1.expand(b['candidate'],tr,budget)
            ck(f'phase_{initial}_{phase}_deadline_delay',failure is None and all(0<=r['base_us']-r['release_us']<=3750 for r in req))
            pulses=[r for r in rows if r['unit']=='N0']
            ck(f'phase_{initial}_{phase}_pulse_spacing',all(z['start_us']-r['start_us']>=16250 for r,z in zip(pulses,pulses[1:])))
            segments=a.v1.power_segments(b['candidate'],tr,rows,F(tr['window_us']),budget)
            windows=[(F(0),F(40000)),(times[0]-4000,times[0]+4000),
                     (times[1]-F(1,4),times[1]+7500),(times[2],times[2]+34000)]
            ok=True
            for lo,hi in windows:
                energy=sum((F(s['activity_increment_W'])*max(F(0),min(hi,s['end_us'])-max(lo,s['start_us']))/1000000
                            for s in rows if s['unit']=='C0'),F(0))
                ok &= energy <= F(15,32)*(hi-lo)/1000000+F(1,40)
                nrelease=sum(lo<=r['release_us']<=hi for r in releases)
                ok &= nrelease <= 3+75*(hi-lo)/1000000
            ck(f'phase_{initial}_{phase}_window_envelope',ok)
            execution.append(dict(initial_mode=initial,phase_us=str(phase),
                                  maximum_delay_us=str(max(r['base_us']-r['release_us'] for r in req)),
                                  minimum_NPU_start_gap_us=str(min((z['start_us']-r['start_us'] for r,z in zip(pulses,pulses[1:])),default=F(0))),
                                  checked_power_segments=len(segments)))
    evidence['execution_fixtures']=execution
    for initial in ['A','B']:
        tr=deepcopy(b['evaluation']['paths'][0]['trace'])
        tr.update(initial_mode=initial,switch_requests=[],window_us=F(1000000)+14000)
        rows,req,_,failure=a.v1.expand(b['candidate'],tr,a.v2.Budget(seconds=20))
        ck('long_dwell_'+initial,failure is None and all(r['base_us']==r['release_us'] for r in req))

    # Old box remains usable; pulse supplements only unresolved outcomes.
    combined=c.evaluate_safety_bundle(b)
    evidence['combined_receipt']=combined
    ck('new_interface_safety_only',combined['status']=='certified_safety_only' and combined['certified_candidate_energy']['status']=='unavailable')
    ck('old_box_still_unresolved',combined['safety_receipt']['result']['basic_result']['status']=='unresolved')
    ck('binding_has_new_sources','pulse_sources' in combined['safety_receipt']['binding'])
    cpu=c.a.bundle(c.a.load(),'a_c','b_c')
    old=c.evaluate_safety_bundle(cpu)
    ck('old_CPU_box_pass_preserved',old['status']=='certified_safety_only' and old['safety_receipt']['result']['thermal_certificate']['status']=='pass' and 'basic_result' not in old['safety_receipt']['result'])
    late=c.evaluate_safety_bundle(b,budget_at('safety_receiver'))
    ck('late_safe_not_accepted',late['status']=='unresolved' and 'safety_receipt' not in late)
    late=c.evaluate_safety_bundle(b,budget_at('before_safety_receiver_commit'))
    ck('late_receiver_commit_not_accepted',late['status']=='unresolved' and 'safety_receipt' not in late)
    witnessed=dict(status='violation',input_status='valid',witness={'real_violation':True,'kind':'injected_receipt_not_physical_counterexample'})
    with patch.object(a.v2,'verify',return_value=witnessed):
        r=c.evaluate_safety_bundle(b,budget_at('safety_receiver'))
    ck('committed_violation_survives_timeout',r['status']=='candidate_violation' and r['safety_receipt']['result']['witness']['real_violation'])
    # R1: bind the exact reviewed dependencies and the sealed review/gate bytes.
    hashes=c.identities()
    gate=dict(passed=True,checks=[dict(passed=True)],hashes=hashes)
    text='K33_REVIEW: PASS\nK33_HASHES_SHA256: '+c.hashes_digest(hashes)+'\nfixture_only\n'
    def rejects(fn):
        try:fn()
        except (a.v1.Invalid,ValueError,KeyError,TypeError):return True
        return False
    c.check_gate(gate,text)
    ck('matching_review_version_accepts',True)
    ck('PASS_without_version_rejected',rejects(lambda:c.check_gate(gate,'K33_REVIEW: PASS\nold review\n')))
    ck('old_review_new_sources_rejected',rejects(lambda:c.check_gate(gate,'K33_REVIEW: PASS\nK33_HASHES_SHA256: '+'0'*64)))
    stale=deepcopy(gate);stale['hashes']['stale']='1'
    ck('stale_precheck_rejected',rejects(lambda:c.check_gate(stale,text)))
    ck('REVISE_rejected',rejects(lambda:c.check_gate(gate,text.replace('PASS','REVISE'))))
    bad=deepcopy(gate);bad['checks'][0]['passed']=False
    ck('failed_check_even_if_flag_true_rejected',rejects(lambda:c.check_gate(bad,text)))
    raw=json.dumps(gate).encode();rb=text.encode()
    ready=dict(hashes=hashes,gate_sha256=hashlib.sha256(raw).hexdigest(),review_sha256=hashlib.sha256(rb).hexdigest())
    c.check_ready(ready,raw,rb)
    ck('sealed_gate_review_accepts',True)
    ck('review_file_edit_rejected',rejects(lambda:c.check_ready(ready,raw,rb+b'changed')))
    ck('gate_file_edit_rejected',rejects(lambda:c.check_ready(ready,raw+b' ',rb)))
    stale=deepcopy(ready);stale['hashes']['stale']='1'
    ck('sealed_old_sources_rejected',rejects(lambda:c.check_ready(stale,raw,rb)))
    return dict(passed=all(z['passed'] for z in checks),checks=checks,evidence=evidence,
                hashes=c.identities(),scope='K33 necessary prechecks only; no trajectory propagation or energy rerun')
