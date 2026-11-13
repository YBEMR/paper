"""Exactly eight serial development-regression arms, frozen after correctness.

U03/U04 are development roots, not unseen generalization. No new roots, retries,
I2, scale expansion or SA. Reuse the old I1 loader/evaluator/post lifecycle.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
from fractions import Fraction as F
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

from ..scaling import run as shared

REPO=shared.REPO
OLD=REPO/'research/chapter4_scheduler/results/scale24_i1_20261113/execution'
OUT=REPO/'research/chapter4_scheduler/results/onp_cost_ablation_20261113/execution'
PROTOCOL='ON-P-fixed-structural-prefilter-four-arm-development-v1'
ORDER=(('U03__n24','ON'),('U03__n24','ON_P'),('U03__n24','OFF_P'),('U03__n24','OFF'),
       ('U04__n24','OFF'),('U04__n24','OFF_P'),('U04__n24','ON_P'),('U04__n24','ON'))
BUDGETS={'method_s':300,'post_s':60,'method_slots':8,'post_slots_at_most':8,
    'method_process_watchdog_s':360,'post_process_watchdog_s':90,'I1_new_work_admission_s':180}
read,save,sha,digest,now=shared.read,shared.save,shared.sha,shared.digest,shared.now


def slots(cases):
    lookup={c['case_id']:c for c in cases}
    if set(lookup)!={'U03__n24','U04__n24'} or len(cases)!=2:raise ValueError('EXACT_DEVELOPMENT_ROOTS_REQUIRED')
    return [{'id':f'{j:02d}_{case}_{arm}_I1','case_id':case,'root_id':lookup[case]['root_id'],
        'stages_per_scene':24,'arm':arm} for j,(case,arm) in enumerate(ORDER,1)]


def prepare(out,checks):
    if out.exists():raise FileExistsError(out)
    old=read(OLD/'plan.json');checked=read(checks)
    if not checked.get('passed') or checked.get('failures') or checked.get('errors'):raise ValueError('CORRECTNESS_MUST_PASS')
    sources=checked['source_sha256']
    for name,h in sources.items():
        if sha(REPO/name)!=h:raise ValueError('CHECKED_SOURCE_DRIFT:'+name)
    for name,h in old['source_sha256'].items():
        if sources.get(name)!=h:raise ValueError('FROZEN_I1_ON_OFF_DRIFT:'+name)
    for name,h in old['input_file_sha256'].items():
        if sha(OLD/name)!=h:raise ValueError('INPUT_DRIFT:'+name)
    out.mkdir(parents=True)
    for name,h in old['input_file_sha256'].items():
        dst=out/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OLD/name,dst)
    for name,h in sources.items():
        dst=out/'source_snapshot'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,dst)
    shutil.copyfile(checks,out/'precheck.json')
    plan={'protocol':PROTOCOL,'created_utc':now(),'subject_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'authorization':'User chose four arms, eight calls after correctness: U03/U04 24 Stage, ON/ON-P/OFF/OFF-P, each300s and full post. New roots deferred.',
        'environment':shared.environment(),'thread_environment':shared.THREADS,'budgets':BUDGETS,
        'cases':old['cases'],'slots':slots(old['cases']),'source_sha256':sources,
        'input_file_sha256':old['input_file_sha256'],'input_identities':old['input_identities'],
        'precheck_sha256':sha(out/'precheck.json'),'clock':old['clock'],'post':old['post'],'I1_policy':old['I1_policy'],
        'stops':old['stops'],'prior_plan_sha256':sha(OLD/'plan.json'),
        'scope':'Development/cause regression only. Not unseen generalization. Current code and hypotheses fixed before8 runs.',
        'comparison':'Each arm independently calls identical I1,180s admission,300s root. Report initial candidate/energy/sequence equality; unequal initial outputs prohibit pure final-energy mechanism attribution. No retries to force equality.',
        'instrumentation':'Same reconstruct wrapper in all4 arms counts calls/returns/exceptions/wall time. P-only setup/check phases and rejection counters included in root. No per-edge base reuse or other optimization.',
        'frozen_rules':'Target/pair/mode/template iteration, extra-edge order, full candidate hash tie break, SAFE evaluator and strict acceptance unchanged.'}
    save(out/'plan.json',plan);save(out/'plan_identity.json',{'sha256':sha(out/'plan.json')});verify(out,plan)
    print({'prepared':True,'slots':8,'sources':len(sources)},flush=True)


def verify(out,plan):
    if plan['protocol']!=PROTOCOL or plan['budgets']!=BUDGETS or plan['slots']!=slots(plan['cases']):raise ValueError('SCOPE_DRIFT')
    if sha(out/'plan.json')!=read(out/'plan_identity.json')['sha256']:raise ValueError('PLAN_DRIFT')
    if shared.environment()!=plan['environment']:raise ValueError('ENVIRONMENT_DRIFT')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()!=plan['subject_commit']:raise ValueError('SUBJECT_DRIFT')
    for n,h in plan['source_sha256'].items():
        if sha(REPO/n)!=h or sha(out/'source_snapshot'/n)!=h:raise ValueError('SOURCE_DRIFT:'+n)
    for n,h in plan['input_file_sha256'].items():
        if sha(out/n)!=h:raise ValueError('INPUT_DRIFT:'+n)
    if sha(out/'precheck.json')!=plan['precheck_sha256']:raise ValueError('CHECK_DRIFT')


def dispatch(arm,loader,folder,budget,bindings):
    if arm not in ('ON','ON_P','OFF','OFF_P'):raise ValueError('ONLY_FOUR_FROZEN_ARMS')
    from ..i1.initializer import run_heft_i1
    from ..blocking import core,method as old
    from .method import execute_reconstruction as filtered
    bound=old.Bindings(run_heft_i1,bindings.evaluator,'REAL_I1')
    stats=Counter();reconstruct=core.reconstruct
    def measured(*args,**kwargs):
        kind='extra' if kwargs.get('extra_resource_edge') is not None else 'base'
        stats[kind+'_started']+=1;began=budget.clock()
        try:
            p=reconstruct(*args,**kwargs);stats[kind+'_returned']+=1
            stats[kind+'_legal']+=p['state']=='COMPLETE_LEGAL_CANDIDATE';return p
        except BaseException:
            stats[kind+'_exceptions']+=1;raise
        finally:stats[kind+'_call_wall_s']+=budget.clock()-began
    # Single-process serial scope; all four arms use this exact observer.
    core.reconstruct=measured
    try:
        fn=filtered if arm.endswith('_P') else old.execute_reconstruction
        result=fn(loader,folder,budget=budget,seconds=budget.seconds,bindings=bound,
            allow_blocking_edges=arm.startswith('ON'))
        save(Path(folder)/'construction_statistics.json',dict(stats))
        return result
    finally:core.reconstruct=reconstruct


ORIGINAL_METRICS=shared.derived_metrics
def metrics(raw,arm):
    return ORIGINAL_METRICS(raw,'ON')


def worker(out,slot,post):
    with patch.object(shared,'verify',verify),patch.object(shared,'dispatch',dispatch),patch.object(shared,'derived_metrics',metrics):
        return shared.worker(out,slot,post)


def report(out):
    plan=read(out/'plan.json');rows=[];raws={}
    for slot in plan['slots']:
        folder=out/'calls'/slot['id']
        get=lambda n:read(folder/n) if (folder/n).exists() else {}
        ret,post,raw=get('method_return.json'),get('post_return.json'),get('method/result.json')
        raws[slot['id']]=raw
        interval=ret.get('energy_interval_J');initial=(raw.get('initial_safe_snapshot') or {}).get('receipt',{}).get('weighted_energy_J')
        phases=raw.get('timing',{}).get('phases_exclusive_s',{});m=ret.get('metrics',{})
        meta=raw.get('initialization') or {};counts=get('method/prefilter.json').get('counts',{})
        constructors=get('method/construction_statistics.json')
        row={**slot,'safe':ret.get('has_SAFE_archive',False),'post_passed':post.get('passed',False),
            'terminal':ret.get('terminal','NOT_RETURNED'),'reason':ret.get('raw_reason'),
            'failure_reason':ret.get('failure_reason'),'error':ret.get('error'),
            'energy_lower_J':str(F(interval[0])) if interval else None,'energy_upper_J':str(F(interval[1])) if interval else None,
            'energy_J':float(F(interval[1])) if interval else None,'initial_energy_J':float(F(initial[1])) if initial else None,
            'method_elapsed_s':ret.get('timing',{}).get('method_elapsed_s'),
            **{k:v for k,v in m.items() if not isinstance(v,(dict,list))},**ret.get('counts',{}),
            'init_admission_gate_hit':meta.get('stop_reason')=='INIT_ADMISSION_LIMIT',
            'prefilter_setup_s':phases.get('structural_prefilter_setup',0),
            'prefilter_check_s':phases.get('structural_prefilter_check',0),
            'prefilter_total_s':sum(phases.get(k,0) for k in ('structural_prefilter_setup','structural_prefilter_check')),
            'actual_base_calls':constructors.get('base_started',0),'actual_extra_calls':constructors.get('extra_started',0),
            'base_call_wall_s':constructors.get('base_call_wall_s',0),'extra_call_wall_s':constructors.get('extra_call_wall_s',0),
            'construction_calls_interrupted':constructors.get('base_exceptions',0)+constructors.get('extra_exceptions',0),
            'base_pruned':counts.get('base_pruned',0),'extra_pruned_individually':counts.get('extra_pruned',0),
            'base_considered':counts.get('base_considered',constructors.get('base_started',0)),
            'extra_considered_after_base_pass':counts.get('extra_considered',constructors.get('extra_started',0)),
            'extra_edge_accepts':sum(bool(p.get('additional_reversed_edges')) and p['strict_accepted'] for p in raw.get('graph_proposals',[])),
            'prefilter_rule_version':get('method/prefilter.json').get('rule_version'),
            'post_wall_s':post.get('worker_body_wall_s')}
        if raw:
            assert raw['initialization_version']=='I1'
            assert raw['blocking_edge_adjustment_enabled']==slot['arm'].startswith('ON')
            if slot['arm'].startswith('OFF'):assert row['actual_extra_calls']==row['extra_edge_accepts']==0
        rows.append(row)
    pairs=[]
    for case in ('U03__n24','U04__n24'):
        arms={r['arm']:r for r in rows if r['case_id']==case}
        for a,b in (('ON_P','ON'),('OFF_P','OFF'),('ON','OFF'),('ON_P','OFF_P')):
            x,y=arms[a],arms[b];rx,ry=raws[x['id']],raws[y['id']]
            ix,iy=rx.get('initial_safe_snapshot'),ry.get('initial_safe_snapshot')
            same=bool(ix and iy and ix['candidate']==iy['candidate'] and ix['receipt']['weighted_energy_J']==iy['receipt']['weighted_energy_J'])
            seq=lambda r:[e['candidate_sha256'] for e in r.get('evaluations',[]) if e['phase']=='initialization']
            safe=all(r['safe'] and r['post_passed'] and not r['error'] for r in (x,y))
            pairs.append({'case_id':case,'numerator_arm':a,'reference_arm':b,
                'same_initial_candidate_and_energy':same,'same_initialization_sequence':seq(rx)==seq(ry),
                'both_SAFE_post':safe,'pure_initial_state_pair':bool(safe and same and seq(rx)==seq(ry)),
                'observed_energy_saving_percent':float((F(y['energy_upper_J'])-F(x['energy_upper_J']))/F(y['energy_upper_J'])*100) if safe else None})
    result={'protocol':PROTOCOL,'subject_commit':plan['subject_commit'],'rows':rows,'comparisons':pairs,
        'all_results_retained':True,'SAFE_post_successes':sum(r['safe'] and r['post_passed'] for r in rows)}
    save(out/'summary.json',result)
    with (out/'metrics.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','batch','worker','report'))
    p.add_argument('--out',type=Path,default=OUT);p.add_argument('--checks',type=Path);p.add_argument('--slot');p.add_argument('--post',action='store_true')
    a=p.parse_args();out=a.out.resolve()
    if a.action=='prepare':
        if a.checks is None:p.error('--checks required')
        prepare(out,a.checks);return 0
    if a.action=='worker':return worker(out,a.slot,a.post)
    if a.action=='batch':return batch(out)
    report(out);return 0


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
            command = [sys.executable, '-B', '-m', 'research.chapter4_scheduler.onp.run',
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

if __name__=="__main__":raise SystemExit(main())
