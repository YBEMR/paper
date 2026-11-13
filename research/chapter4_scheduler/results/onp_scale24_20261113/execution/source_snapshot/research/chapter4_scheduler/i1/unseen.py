"""Six frozen HEFT-I1/OFF-I1/ON-I1 calls on two new parameter roots."""
import argparse
import csv
from fractions import Fraction as F
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

from research.chapter4_scheduler.scaling import run as shared

REPO=shared.REPO
OLD=REPO/'research/chapter4_scheduler/results/i1_paired_20261113'
OUT=REPO/'research/chapter4_scheduler/results/unseen_i1_20261113/execution'
PROTOCOL='chapter4-frozen-I1-two-new-roots-three-arms-v1'
CASES=('U03__n12','U04__n12')
ORDER=(('U03__n12','HEFT'),('U03__n12','OFF'),('U03__n12','ON'),('U04__n12','ON'),('U04__n12','OFF'),('U04__n12','HEFT'))
BUDGETS={'method_s':300,'post_s':60,'method_slots':6,'post_slots_at_most':6,
    'method_process_watchdog_s':360,'post_process_watchdog_s':90,'I1_new_work_admission_s':180}
read,save,sha,digest,now=shared.read,shared.save,shared.sha,shared.digest,shared.now
ORIGINAL_METRICS=shared.derived_metrics


def slots(cases):
    indexed={c['case_id']:c for c in cases}
    if set(indexed)!=set(CASES) or len(cases)!=2:raise ValueError('EXACT_TWO_12_STAGE_CASES_REQUIRED')
    return [{'id':f'{i:02d}_{case}_{arm}_I1','case_id':case,'arm':arm,
        'root_id':indexed[case]['root_id'],'stages_per_scene':indexed[case]['stages_per_scene']}
        for i,(case,arm) in enumerate(ORDER,1)]


def prepare(out,checks):
    from .new_inputs import fixed_plan
    if out.exists():raise FileExistsError(out)
    checked=read(checks)
    if not checked.get('passed') or checked.get('failures') or checked.get('errors'):
        raise ValueError('PASSING_MOCK_CHECKS_REQUIRED')
    old=read(OLD/'plan.json')
    if sha(OLD/'plan.json')!=read(OLD/'plan_identity.json')['sha256']:raise ValueError('OLD_PLAN_DRIFT')
    for name,h in old['source_sha256'].items():
        if sha(REPO/name)!=h or sha(OLD/'source_snapshot'/name)!=h:raise ValueError('FROZEN_SCIENCE_DRIFT:'+name)
    generated=out.parent/'input_generation'
    manifest=read(generated/'inputs_manifest.json')
    if read(generated/'input_plan.json')!=fixed_plan() or sha(generated/'input_plan.json')!=manifest['plan_sha256']:
        raise ValueError('INPUT_PLAN_DRIFT')
    cases=manifest['cases'];run_slots=slots(cases)
    expected={r['root_id']:r['seed'] for r in fixed_plan()['roots']}
    old_config=read(OLD/'frozen_inputs/U01__n12/config.json')
    identities={}
    for c in cases:
        if c['seed']!=expected[c['root_id']] or c['stages_per_scene']!=12:raise ValueError('FIXED_ROOT_DRIFT')
        for key in ('config','instance','generation_evidence'):
            if sha(shared.child(generated,c[key+'_path']))!=c[key+'_sha256']:raise ValueError('GENERATED_INPUT_DRIFT')
        config=read(generated/c['config_path']);instance=read(generated/c['instance_path'])
        if len(instance['scenarios'])!=2 or any(len(x['stage_instances'])!=12 for x in instance['scenarios']):raise ValueError('SCENE_OR_STAGE_DRIFT')
        if any(x['entry']['temperature_degC']!=['50']*4 or x['maximum_temperature_degC']!=['80']*4 or F(x['weight'])!=F(1,2) for x in instance['scenarios']):raise ValueError('CONDITIONS_DRIFT')
        if instance['platform']!=old_config['platform'] or config['accuracy_targets']!=old_config['accuracy_targets']:raise ValueError('MODEL_OR_PRECISION_DRIFT')
        identities[c['case_id']]={'config_sha256':digest(config),'instance_sha256':digest(instance)}
    out.mkdir(parents=True)
    inputs={}
    for c in cases:
        for key in ('config_path','instance_path'):
            name='frozen_inputs/'+c[key];dst=out/name;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(generated/c[key],dst);inputs[name]=sha(dst)
    sources=dict(old['source_sha256'])
    for name in ('new_inputs.py','unseen.py','test_unseen.py'):
        p=Path(__file__).parent/name;sources[p.relative_to(REPO).as_posix()]=sha(p)
    for name,h in sources.items():
        dst=out/'source_snapshot'/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,dst);assert sha(dst)==h
    shutil.copyfile(checks,out/'precheck.json')
    plan={'protocol':PROTOCOL,'created_utc':now(),
        'authorization':'User requested two new independent parameter roots,12 Stage/scene,2scenes,50C; exactly HEFT-I1/OFF-I1/ON-I1 each300s with full post. Frozen I1/ON, no replacement/tuning/I2/24/SA. Prior180s admission and60s post retained.',
        'subject_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'observed_remote_before_code':{'unseen':'6d67cf2538280c3fee4ab5b7879570b204bb6224','other_research':'223097d2749249552087cca42336dda3ab2dd49a'},
        'environment':shared.environment(),'thread_environment':shared.THREADS,'budgets':BUDGETS,
        'slots':run_slots,'cases':cases,'source_sha256':sources,'input_file_sha256':inputs,'input_identities':identities,
        'prior_frozen_sources_byte_identical':len(old['source_sha256']),'prior_plan_sha256':sha(OLD/'plan.json'),
        'generation_plan':read(generated/'input_plan.json'),'generation_manifest_sha256':sha(generated/'inputs_manifest.json'),
        'precheck_sha256':sha(out/'precheck.json'),'clock':old['clock'],'post':old['post'],'stops':old['stops'],'I1_policy':old['I1_policy'],
        'initialization':'All3 arms call the exact frozen run_heft_i1 independently. No imported candidate/cache/time reference. HEFT terminates after the same I1 quality pass; ON/OFF use the remaining original root.',
        'comparison':'Report all6 outcomes, observed energy differences, initial quality and sequence equality, gate/cost/failure reasons. Pure edge comparison requires matching initial histories. No retries to force equality.',
        'scope':'First use of the2 predeclared parameter roots after I1/ON freeze, within existing synthetic distributions and topology family; not external blind tasks or statistical stability evidence.'}
    save(out/'plan.json',plan);save(out/'plan_identity.json',{'sha256':sha(out/'plan.json')})
    verify(out,plan)
    print({'prepared':True,'slots':6,'unchanged_prior_sources':len(old['source_sha256'])},flush=True)


def verify(out,plan):
    if plan['protocol']!=PROTOCOL or plan['slots']!=slots(plan['cases']) or plan['budgets']!=BUDGETS:
        raise ValueError('SCOPE_OR_BUDGET_DRIFT')
    if sha(out/'plan.json')!=read(out/'plan_identity.json')['sha256']:raise ValueError('PLAN_DRIFT')
    if shared.environment()!=plan['environment']:raise ValueError('ENVIRONMENT_DRIFT')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()!=plan['subject_commit']:
        raise ValueError('SUBJECT_DRIFT')
    for name,h in plan['source_sha256'].items():
        if sha(REPO/name)!=h or sha(out/'source_snapshot'/name)!=h:raise ValueError('SOURCE_DRIFT:'+name)
    for name,h in plan['input_file_sha256'].items():
        if sha(out/name)!=h:raise ValueError('INPUT_DRIFT:'+name)
    if sha(out/'precheck.json')!=plan['precheck_sha256']:raise ValueError('CHECK_DRIFT')


def dispatch(arm,loader,folder,budget,bindings):
    if arm not in ('HEFT','ON','OFF'):raise ValueError('ONLY_SIX_FROZEN_I1_CALLS')
    from .initializer import run_heft_i1
    from research.chapter4_scheduler.blocking.method import Bindings,execute_reconstruction
    bound=Bindings(run_heft_i1,bindings.evaluator,'REAL_I1')
    if arm=='HEFT':
        from research.chapter4_scheduler.validation.lifecycle import execute_heft
        return execute_heft(loader,folder,budget=budget,bindings=bound)
    return execute_reconstruction(loader,folder,budget=budget,seconds=budget.seconds,
        bindings=bound,allow_blocking_edges=arm=='ON')


def metrics(raw,arm):
    return ORIGINAL_METRICS(raw,'HEFT' if arm=='HEFT' else 'ON')


def worker(out,slot,post):
    with patch.object(shared,'verify',verify),patch.object(shared,'dispatch',dispatch),patch.object(shared,'derived_metrics',metrics):
        return shared.worker(out,slot,post)


def batch(out):
    plan = read(out / 'plan.json')
    verify(out, plan)
    save(out / 'batch_started.json', {'utc': now(), 'plan_sha256': sha(out / 'plan.json')})
    began, stop, rows = time.monotonic(), None, []
    env = dict(os.environ, **shared.THREADS, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    for slot in plan['slots']:
        row = {'slot': slot, 'status': 'NOT_RUN_TECHNICAL_STOP' if stop else 'STARTED', 'phases': []}
        rows.append(row)
        if stop:
            row['reason'] = stop
            continue
        folder = out / 'calls' / slot['id']
        folder.mkdir(parents=True, exist_ok=False)
        for phase, timeout in (('method', 360), ('post', 90)):
            if phase == 'post':
                result = read(folder / 'method_return.json')
                if not result.get('normal_stop') or not result.get('has_SAFE_archive'):
                    break
            verify(out, plan)
            save(folder / (phase + '_claim.json'), {'utc': now(), 'slot': slot,
                'plan_sha256': sha(out / 'plan.json'), 'no_retry': True})
            command = [sys.executable, '-B', '-m', 'research.chapter4_scheduler.i1.unseen',
                       'worker', '--out', str(out), '--slot', slot['id']] + (['--post'] if phase == 'post' else [])
            record = {'argv': command, 'cwd': str(REPO), 'started_utc': now(),
                      'thread_environment': shared.THREADS, 'watchdog_s': timeout, 'phase': phase}
            save(folder / (phase + '_command_started.json'), record)
            print({'START': slot['id'], 'phase': phase, 'utc': now()}, flush=True)
            started = time.monotonic()
            try:
                proc = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
                (folder / (phase + '_stdout.log')).write_text(proc.stdout, encoding='utf-8')
                (folder / (phase + '_stderr.log')).write_text(proc.stderr, encoding='utf-8')
                result = read(folder / (phase + '_return.json'))
                record.update(exit_code=proc.returncode, normal_stop=result.get('normal_stop'), watchdog_expired=False)
                if proc.returncode or result.get('error') or not result.get('normal_stop'):
                    stop = slot['id'] + ':' + phase + ':ABNORMAL_RETURN'
                print({'DONE': slot['id'], 'phase': phase, 'terminal': result.get('terminal'),
                       'safe': result.get('has_SAFE_archive'), 'error': result.get('error')}, flush=True)
            except BaseException as error:
                stop = slot['id'] + ':' + phase + ':' + type(error).__name__
                record.update(error={'type': type(error).__name__, 'reason': str(error)},
                              watchdog_expired=isinstance(error, subprocess.TimeoutExpired))
                if isinstance(error, subprocess.TimeoutExpired):
                    for label, value in (('stdout', error.stdout), ('stderr', error.stderr)):
                        (folder / (phase + '_partial_' + label + '.log')).write_bytes(value.encode('utf-8') if isinstance(value, str) else value or b'')
            record.update(wall_s=time.monotonic()-started, ended_utc=now())
            save(folder / (phase + '_command_return.json'), record)
            row['phases'].append(record)
            if stop:
                row.update(status='STOPPED_TECHNICAL', reason=stop)
                break
        if not stop:
            row['status'] = 'COMPLETED'
    try:
        verify(out, plan)
        intact = True
    except Exception as error:
        intact, stop = False, stop or repr(error)
    save(out / 'batch_return.json', {'protocol': PROTOCOL, 'wall_s': time.monotonic()-began, 'slots': rows,
        'stop_reason': stop, 'frozen_identity_unchanged': intact, 'retry_count': 0,
        'all_planned_method_slots_returned': all(r['status'] == 'COMPLETED' for r in rows)})
    report(out)
    return int(stop is not None)


def compare_pair(on,off,a,b):
    ia,ib=a.get('initial_safe_snapshot'),b.get('initial_safe_snapshot')
    initialized=bool(ia and ib)
    same_initial=initialized and ia['candidate']==ib['candidate']
    same_energy=initialized and ia['receipt']['weighted_energy_J']==ib['receipt']['weighted_energy_J']
    sequence=lambda r:[e['candidate_sha256'] for e in r.get('evaluations',[]) if e['phase']=='initialization']
    same_sequence=initialized and sequence(a)==sequence(b)
    valid=all(r['safe'] and r['post_passed'] and not r['error'] for r in (on,off))
    return {'same_initial_candidate':same_initial,'same_initial_energy_interval':same_energy,
        'same_initialization_sequence':same_sequence,'comparable_SAFE_pair':bool(valid and same_initial and same_energy and same_sequence),
        'both_final_SAFE_post_passed':valid,
        'observed_ON_vs_OFF_saving_percent':float((F(off['energy_upper_J'])-F(on['energy_upper_J']))/F(off['energy_upper_J'])*100) if valid else None,
        'strict_interval_improvement':F(on['energy_upper_J'])<F(off['energy_lower_J']) if valid else None,
        'same_final_candidate':a.get('safe_candidate')==b.get('safe_candidate') if valid else None}


def report(out):
    plan=read(out/'plan.json');rows=[];raws={}
    for slot in plan['slots']:
        folder=out/'calls'/slot['id']
        ret=read(folder/'method_return.json') if (folder/'method_return.json').exists() else {}
        post=read(folder/'post_return.json') if (folder/'post_return.json').exists() else {}
        raw=read(folder/'method/result.json') if (folder/'method/result.json').exists() else {}
        command=read(folder/'method_command_return.json') if (folder/'method_command_return.json').exists() else {}
        raws[slot['id']]=raw
        interval=ret.get('energy_interval_J');meta=raw.get('initialization') or {};m=ret.get('metrics',{})
        initial=(raw.get('initial_safe_snapshot') or {}).get('receipt',{}).get('weighted_energy_J')
        row={**slot,'initializer':'I1','terminal':ret.get('terminal','NOT_RETURNED'),'reason':ret.get('raw_reason'),
            'error':ret.get('error'),'failure_reason':ret.get('failure_reason'),
            'safe':ret.get('has_SAFE_archive',False),'post_passed':post.get('passed',False),
            'energy_lower_J':str(F(interval[0])) if interval else None,'energy_upper_J':str(F(interval[1])) if interval else None,
            'energy_upper_J_decimal':float(F(interval[1])) if interval else None,
            'initial_energy_lower_J':str(F(initial[0])) if initial else None,'initial_energy_upper_J':str(F(initial[1])) if initial else None,
            'saving_vs_own_initial_percent':float((F(initial[1])-F(interval[1]))/F(initial[1])*100) if initial and interval else None,
            'method_elapsed_s':ret.get('timing',{}).get('method_elapsed_s'),'process_wall_s':command.get('wall_s'),
            'worker_body_wall_s':ret.get('worker_body_wall_s'),'post_wall_s':post.get('worker_body_wall_s'),
            **{k:v for k,v in m.items() if not isinstance(v,(dict,list))},**ret.get('counts',{}),
            'first_SAFE_at_s':ret.get('first_SAFE_at_s'),'initialization_status':meta.get('status'),
            'initialization_stop_reason':meta.get('stop_reason'),'fallback_used':meta.get('fallback_used'),
            'admission_gate_triggered':meta.get('stop_reason')=='INIT_ADMISSION_LIMIT',
            'remaining_search_budget_s':300-m['initialization_completed_at_s'] if m.get('initialization_completed_at_s') is not None else None,
            'search_entered':any(p['phase']=='activity_saving_targets' for p in raw.get('timing',{}).get('phase_records',[])),
            'extra_edge_graph_attempts':sum(bool(d.get('extra_resource_edge')) for d in raw.get('reconstruction_attempts',[])),
            'extra_edge_proposals':sum(bool(p.get('additional_reversed_edges')) for p in raw.get('graph_proposals',[])),
            'extra_edge_accepts':sum(bool(p.get('additional_reversed_edges')) and p['strict_accepted'] for p in raw.get('graph_proposals',[]))}
        if raw:
            assert raw['initialization_version']=='I1'
            if slot['arm']!='HEFT':assert raw['blocking_edge_adjustment_enabled']==(slot['arm']=='ON')
            if slot['arm']=='OFF':assert row['extra_edge_graph_attempts']==row['extra_edge_proposals']==row['extra_edge_accepts']==0
        rows.append(row)
    pairs=[]
    for case in CASES:
        arms={r['arm']:r for r in rows if r['case_id']==case};on,off=arms['ON'],arms['OFF']
        pairs.append({'case_id':case,**compare_pair(on,off,raws[on['id']],raws[off['id']])})
    triples=[]
    for case in CASES:
        arms={r['arm']:r for r in rows if r['case_id']==case};h=arms['HEFT']
        hr=raws[h['id']];initials=[raws[r['id']].get('initial_safe_snapshot') for r in arms.values()]
        same_initial=all(initials) and all(x['candidate']==initials[0]['candidate'] and x['receipt']['weighted_energy_J']==initials[0]['receipt']['weighted_energy_J'] for x in initials)
        seq=lambda r:[e['candidate_sha256'] for e in r.get('evaluations',[]) if e['phase']=='initialization']
        same_sequence=all(initials) and all(seq(raws[r['id']])==seq(hr) for r in arms.values())
        entry={'case_id':case,'all3_same_initial_candidate_and_energy':bool(same_initial),'all3_same_initial_sequence':bool(same_sequence)}
        for arm in ('OFF','ON'):
            r=arms[arm];valid=all(x['safe'] and x['post_passed'] and not x['error'] for x in (r,h))
            entry[arm+'_vs_HEFT_saving_percent']=float((F(h['energy_upper_J'])-F(r['energy_upper_J']))/F(h['energy_upper_J'])*100) if valid else None
            entry[arm+'_vs_HEFT_strict_interval_improvement']=F(r['energy_upper_J'])<F(h['energy_lower_J']) if valid else None
        triples.append(entry)
    result={'protocol':PROTOCOL,'subject_commit':plan['subject_commit'],'rows':rows,'comparisons':pairs,
        'three_arm_comparisons':triples,'all_results_retained':True,'SAFE_post_successes':sum(r['safe'] and r['post_passed'] for r in rows)}
    save(out/'summary.json',result)
    with (out/'metrics.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('generate','prepare','batch','worker','report'))
    p.add_argument('--out',type=Path,default=OUT);p.add_argument('--slot');p.add_argument('--post',action='store_true')
    p.add_argument('--checks',type=Path)
    a=p.parse_args();out=a.out.resolve()
    if a.action=='generate':
        from .new_inputs import build_inputs
        result=build_inputs(out.parent/'input_generation');print(result['counters']);return 0
    if a.action=='prepare':
        if a.checks is None:p.error('prepare requires mock checks')
        prepare(out,a.checks);return 0
    if a.action=='worker':return worker(out,a.slot,a.post)
    if a.action=='batch':return batch(out)
    report(out);return 0


if __name__=='__main__':raise SystemExit(main())
