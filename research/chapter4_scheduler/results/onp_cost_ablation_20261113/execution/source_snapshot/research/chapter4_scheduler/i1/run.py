"""Authorized five-slot initialization validation; no real ON/OFF search route."""
import argparse
from collections import Counter
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
OLD=REPO/'research/chapter4_scheduler/results/unseen_scaling_20261112/execution'
OUT=REPO/'research/chapter4_scheduler/results/i1_initialization_20261112'
PROTOCOL='chapter4-I1-first-five-initializers-v1'
ORDER=(('U02__n12','I1'),('U01__n12','I0'),('U01__n12','I1'),('U01__n6','I1'),('U02__n6','I1'))
BUDGETS={'method_s':300,'post_s':60,'method_slots':5,'post_slots_at_most':5,
         'method_process_watchdog_s':360,'post_process_watchdog_s':90,'I1_new_work_admission_s':180}
ADAPTER_CHANGES={'research/chapter4_scheduler/method.py','research/chapter4_scheduler/blocking/method.py',
                 'research/chapter4_scheduler/validation/lifecycle.py'}
read,save,sha,digest,now=shared.read,shared.save,shared.sha,shared.digest,shared.now


def slots(cases):
    index={c['case_id']:c for c in cases}
    if set(index)!={c for c,v in ORDER} or len(cases)!=4:
        raise ValueError('EXACT_FOUR_ORIGINAL_INPUTS_REQUIRED')
    return [{'id':f'{i:02d}_{case}_{version}','case_id':case,'arm':version,
             'root_id':index[case]['root_id'],'stages_per_scene':index[case]['stages_per_scene']}
            for i,(case,version) in enumerate(ORDER,1)]


def prepare(out,checks):
    if out.exists():raise FileExistsError(out)
    checked=read(checks)
    if not checked.get('passed') or checked.get('failures') or checked.get('errors'):
        raise ValueError('PASSING_SIMULATED_CHECKS_REQUIRED')
    old=read(OLD/'plan.json')
    changes={}
    for name,h in old['source_sha256'].items():
        current=sha(REPO/name)
        if current!=h:
            if name not in ADAPTER_CHANGES:raise ValueError('UNAUTHORIZED_OLD_SOURCE_CHANGE:'+name)
            changes[name]={'before':h,'after':current}
    if set(changes)!=ADAPTER_CHANGES:raise ValueError('EXPECTED_VERSION_HANDOFF_ADAPTERS_ONLY')
    for name,h in old['input_file_sha256'].items():
        if sha(OLD/name)!=h:raise ValueError('OLD_INPUT_DRIFT:'+name)
    cases=old['cases']
    run_slots=slots(cases)
    out.mkdir(parents=True)
    input_files={}
    for c in cases:
        # The initializer never receives or opens generation evidence/reference schedules.
        for key in ('config_path','instance_path'):
            relative=c[key]
            src,dst=OLD/'frozen_inputs'/relative,out/'frozen_inputs'/relative
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
            input_files[dst.relative_to(out).as_posix()]=sha(dst)
    paths={REPO/name for name in old['source_sha256']}
    paths.update((REPO/'research/chapter4_scheduler/i1').glob('*.py'))
    paths.add(REPO/'research/chapter4_scheduler/scaling/p3.py')
    sources={p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)}
    for name,h in sources.items():
        dst=out/'source_snapshot'/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,dst)
        assert sha(dst)==h
    shutil.copyfile(checks,out/'precheck.json')
    plan={'protocol':PROTOCOL,'created_utc':now(),
        'authorization':'User approved implementing I1, mock checks then exactly the five initialization slots in PROPOSAL_20261112; total300/admission180; no ON-I1/OFF-I1 pair, stage24 or SA.',
        'subject_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'observed_remote_before_code':{'unseen':'4c98f681ae499bd8f0cd081bcc99a0e9d8281f5b','other_research':'3baeae859d0370da183c108cd4f6de869db09fec'},
        'environment':shared.environment(),'thread_environment':shared.THREADS,'budgets':BUDGETS,
        'slots':run_slots,'cases':cases,'input_identities':old['input_identities'],
        'source_sha256':sources,'input_file_sha256':input_files,'adapter_changes':changes,
        'original_sources_byte_identical':len(old['source_sha256'])-len(changes),
        'proposal_sha256':sha(REPO/'research/chapter4_scheduler/i1/PROPOSAL_20261112.md'),
        'precheck_sha256':sha(out/'precheck.json'),'clock':old['clock'],'post':old['post'],'stops':old['stops'],
        'I1_policy':{'old_attempts':[None,0,1,2],'new_fallbacks':1,'priority':'ready min(copy_deadline), exact-unit count, -rank_u, id',
            'active_order_retained':True,'quality_stages':['shared-unit','execution-opp'],'omitted_stage':'one-start-delay',
            'admission_seconds':180,'admission_is_hard_phase_cap':False,'root_reset':False},
        'scope':'Initialization only. Shared I1 arm integration checked on mocks. Historical failures and reference diagnostic remain separate; no reference injection or input tuning.'}
    save(out/'plan.json',plan);save(out/'plan_identity.json',{'sha256':sha(out/'plan.json')})
    verify(out,plan)
    print({'prepared':True,'slots':len(run_slots),'sources':len(sources),'unchanged_original_sources':plan['original_sources_byte_identical']},flush=True)


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


def dispatch(version,loader,folder,budget,bindings):
    if version not in ('I0','I1'):raise ValueError('ONLY_FIVE_INITIALIZER_SLOTS_AUTHORIZED')
    from research.chapter4_scheduler.validation.lifecycle import execute_heft
    from research.chapter4_scheduler.method import Bindings
    if version=='I1':
        from .initializer import run_heft_i1
        bindings=Bindings(run_heft_i1,bindings.evaluator,'REAL_I1')
    return execute_heft(loader,folder,bindings=bindings,budget=budget)


def worker(out,slot,post):
    # Same original root, input loading, evaluator journal and complete post receipt.
    with patch.object(shared,'verify',verify),patch.object(shared,'dispatch',dispatch):
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
            command = [sys.executable, '-B', '-m', 'research.chapter4_scheduler.i1.run',
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


def report(out):
    plan=read(out/'plan.json');rows=[]
    for slot in plan['slots']:
        folder=out/'calls'/slot['id']
        ret=read(folder/'method_return.json') if (folder/'method_return.json').exists() else {}
        raw=read(folder/'method/result.json') if (folder/'method/result.json').exists() else {}
        post=read(folder/'post_return.json') if (folder/'post_return.json').exists() else {}
        interval=ret.get('energy_interval_J');meta=raw.get('initialization') or {}
        m=ret.get('metrics',{});count=ret.get('counts',{})
        physical=[e for e in raw.get('evaluations',[]) if not e.get('cache_hit')]
        first=next((e for e in physical if e.get('accepted_safe')),None)
        command=read(folder/'method_command_return.json') if (folder/'method_command_return.json').exists() else {}
        rows.append({**slot,'terminal':ret.get('terminal','NOT_RETURNED'),'reason':ret.get('raw_reason'),
            'error':ret.get('error'),'safe':ret.get('has_SAFE_archive',False),'post_passed':post.get('passed',False),
            'energy_lower_J':str(F(interval[0])) if interval else None,'energy_upper_J':str(F(interval[1])) if interval else None,
            'energy_upper_J_decimal':float(F(interval[1])) if interval else None,
            'first_SAFE_at_s':first['receipt']['completed_at_elapsed_s'] if first else None,
            'first_SAFE_energy_upper_J':first['receipt']['weighted_energy_J'][1] if first else None,
            'method_elapsed_s':raw.get('timing',{}).get('method_elapsed_s'),'process_wall_s':command.get('wall_s'),
            'worker_body_wall_s':ret.get('worker_body_wall_s'),
            **{k:v for k,v in m.items() if not isinstance(v,(dict,list))},**count,
            'initialization_status':meta.get('status'),'initialization_stop_reason':meta.get('stop_reason'),
            'fallback_used':meta.get('fallback_used',False),'active_priority':meta.get('active_priority','original'),
            'construction_attempts':len(meta.get('construction_attempts',[])),
            'local_construct_attempts':len(meta.get('local_attempts',[])),'local_accepted':meta.get('local_accepted'),
            'admission_gate_triggered':meta.get('stop_reason')=='INIT_ADMISSION_LIMIT',
            'remaining_at_handoff_s':300-m['initialization_completed_at_s'] if m.get('initialization_completed_at_s') is not None else None})
    pair={r['arm']:r for r in rows if r['case_id']=='U01__n12'}
    valid=all(r['safe'] and r['post_passed'] and not r['error'] for r in pair.values())
    old,new=pair['I0'],pair['I1']
    comparison={'case_id':'U01__n12','comparable_SAFE_pair':valid,
        'I1_energy_increase_percent':float((F(new['energy_upper_J'])-F(old['energy_upper_J']))/F(old['energy_upper_J'])*100) if valid else None,
        'I1_minus_I0_method_seconds':new['method_elapsed_s']-old['method_elapsed_s'] if valid else None,
        'I1_minus_I0_full_evaluations':new['evaluation_attempts']-old['evaluation_attempts'] if valid else None}
    result={'protocol':PROTOCOL,'subject_commit':plan['subject_commit'],'rows':rows,'comparison':comparison,
        'all_results_retained':True,'SAFE_post_successes':sum(r['safe'] and r['post_passed'] for r in rows)}
    save(out/'summary.json',result)
    with (out/'metrics.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','batch','worker','report'))
    p.add_argument('--out',type=Path,default=OUT);p.add_argument('--slot');p.add_argument('--post',action='store_true')
    p.add_argument('--checks',type=Path)
    a=p.parse_args();out=a.out.resolve()
    if a.action=='prepare':
        if a.checks is None:p.error('prepare requires mock checks')
        prepare(out,a.checks);return 0
    if a.action=='worker':return worker(out,a.slot,a.post)
    if a.action=='batch':return batch(out)
    report(out);return 0


if __name__=='__main__':raise SystemExit(main())
