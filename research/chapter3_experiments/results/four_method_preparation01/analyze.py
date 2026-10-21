"""K152 saved-record analysis only: no solver, model construction or heat calls.

Run after launcher_result.json is present. Creates only analysis01; original
result, claim, receipt, input and source bytes are verified unchanged afterward.
"""
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
import csv
import hashlib
import json
import math
import os
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
HERE = REPO/'research/chapter3_experiments'
ROOT = HERE/'results/four_method_comparison01'
OUT = ROOT/'analysis01'
JOBS = ('whole_milp', 'anchor_linked4', 'heft', 'sa101')
NAMES = dict(whole_milp='Whole MILP', anchor_linked4='Preeliminated linked',
             heft='HEFT', sa101='SA101')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


def csvsave(name, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    if not fields:
        fields = ['no_saved_records']
    with (OUT/name).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v, ensure_ascii=False, sort_keys=True)
                if isinstance(v, (dict, list, tuple)) else v for k,v in row.items()})


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        val = float(F(str(value)))
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    return val if math.isfinite(val) else None


def interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    low, high = map(lambda x:F(str(x)), value)
    if low < 0 or high < low:
        raise ValueError('invalid energy interval')
    return low, high


def raw_paths():
    files=[]
    for folder in [ROOT/j for j in JOBS]+[ROOT/'claims']:
        if folder.exists():
            files.extend(p for p in folder.rglob('*') if p.is_file())
    files.extend(ROOT/n for n in ('declaration.json','protocol.md','precheck.json',
        'input_config.json','input_instance.json','input_raw.json','ledger.json',
        'launcher_claim.json','launcher_result.json','runtime_imports.json',
        'wrapper_timing.json') if (ROOT/n).is_file())
    files.extend(p for folder in ('source_snapshot','dependency_snapshot')
        for p in (ROOT/folder).rglob('*') if p.is_file())
    return sorted(set(files))


def manifest(files):
    return {p.relative_to(REPO).as_posix():sha(p) for p in files}


def get_bound(job, result):
    if job == 'anchor_linked4':
        bound = (result.get('deployment_bounds') or {}).get('L0') or {}
    elif job == 'whole_milp':
        p = ROOT/job/'independent_bounds.json'
        bound = (read(p).get('L0') or {}) if p.is_file() else {}
    else:
        bound = result.get('independent_lower_bound') or {}
    bound=dict(bound)
    # Some exact-bound helpers stamp before finishing. The wrapper's explicit
    # post-construction receipt is the publication time, never the phase start.
    explicit=result.get('lower_bound_formed_at_s')
    if number(explicit) is not None:
        bound.update(raw_helper_formed_at_s=bound.get('formed_at_s'),formed_at_s=explicit,
            formed_time_source='result.lower_bound_formed_at_s (explicit completed construction receipt)')
    else:
        bound['formed_time_source']='saved independent-bound formed_at_s; no earlier timestamp invented'
    return bound


def final_evaluation(result):
    return result.get('aggregation') or result.get('evaluation') or {}


def final_schedule_rows(job, result, instance):
    candidate = result.get('safe_candidate') or final_evaluation(result).get('safe_candidate') or {}
    rows=[]
    lookup = {s['id']:s for sc in instance['scenarios'] for s in sc['stage_instances']}
    for scene, stages in candidate.get('scenes',{}).items():
        for stage in stages:
            meta = lookup[stage['stage_id']]
            mode = next(m for m in instance['stage_modes'][meta['shared_stage_id']]
                if m['unit_id']==stage['unit'] and m['opp_id']==stage['opp'])
            end = F(stage['start_ms'])+F(mode['duration_ms'])
            rows.append(dict(job=job, scene=scene, stage_id=stage['stage_id'],
                shared_stage_id=meta['shared_stage_id'], unit=stage['unit'], opp=stage['opp'],
                start_ms=stage['start_ms'], duration_ms=mode['duration_ms'], end_ms=str(end),
                start_ms_numeric=float(F(stage['start_ms'])), end_ms_numeric=float(end),
                frequency_GHz=mode['frequency_GHz'], activity_power_W=mode['activity_power_W'],
                mode_source='frozen input mode lookup; no candidate generation'))
    return rows, candidate


def component_rows(job, result, instance):
    rows=[]; weighted={}
    receipt=final_evaluation(result)
    weights={s['id']:F(s['weight']) for s in instance['scenarios']}
    for sid, scene in receipt.get('scenes',{}).items():
        physical=scene.get('result') if isinstance(scene.get('result'),dict) else scene
        for component, values in physical.get('energy_components_J',{}).items():
            q=interval(values)
            if q is None:
                raise ValueError('Incomplete saved energy component')
            vals=weighted.setdefault(component,[F(0),F(0)])
            vals[0]+=weights[sid]*q[0]; vals[1]+=weights[sid]*q[1]
            rows.append(dict(job=job,scene=sid,component=component,
                scene_weight=str(weights[sid]),low_J=values[0],high_J=values[1],
                low_J_numeric=float(q[0]),high_J_numeric=float(q[1])))
    for component, q in weighted.items():
        rows.append(dict(job=job,scene='WEIGHTED_ALL_SCENES',component=component,
            scene_weight='already weighted',low_J=str(q[0]),high_J=str(q[1]),
            low_J_numeric=float(q[0]),high_J_numeric=float(q[1]),
            scope='exact weighted saved component intervals; explanatory, not new SAFE evidence'))
    return rows


def diagnostic_sets(result):
    if result.get('phases'):
        for phase in result['phases']:
            for scene, item in phase.get('scenes',{}).items():
                solver=item.get('solver_result') or {}
                yield dict(phase_index=phase.get('phase_index'),scene=scene,
                    phase_name=phase.get('name')), solver.get('diagnostic') or {}, solver
    else:
        yield dict(phase_index=None,scene='ALL',phase_name=None), result.get('diagnostic') or {}, result


def candidate_and_feedback(job,result):
    candidates=[];feedback=[];progress=[]
    for meta, diag, solver in diagnostic_sets(result):
        for i,item in enumerate(diag.get('evaluations',[])):
            evaluation=item.get('evaluation') or item.get('receipt') or item.get('result') or {}
            candidates.append(dict(job=job,**meta,index=i,
                candidate_sha256=canonical(item.get('candidate')),
                source=item.get('source'),accepted_safe=item.get('accepted_safe'),
                within_budget=item.get('within_budget'),started_at_s=item.get('started_at_s'),
                completed_at_s=item.get('completed_at_s'),
                evaluation_returned_at_s=item.get('evaluation_returned_at_s'),
                reason=item.get('reason'), evaluation_state=evaluation.get('state'),
                local_receipt_not_full_system_SAFE=meta['scene']!='ALL',
                saved_scalar_fields={k:v for k,v in item.items() if not isinstance(v,(dict,list))}))
        for i,item in enumerate(diag.get('solver_progress',[])):
            progress.append(dict(job=job,**meta,index=i,saved_record=item,
                scope='solver-reported; no independent certification'))
        for i,item in enumerate(solver.get('feedback',[])):
            feedback.append(dict(job=job,**meta,index=i,saved_record=item))
    for i,item in enumerate(result.get('evaluations',[])):
        evaluation=item.get('evaluation') or {}
        candidates.append(dict(job=job,phase_index=None,scene='ALL',index=i,
            candidate_sha256=canonical(item.get('candidate')),source=item.get('source'),
            accepted_safe=item.get('accepted_safe'),within_budget=item.get('within_budget'),
            started_at_s=item.get('started_at_s'),completed_at_s=evaluation.get('completed_at_elapsed_s'),
            evaluation_state=evaluation.get('state'),local_receipt_not_full_system_SAFE=False,
            saved_scalar_fields={k:v for k,v in item.items() if not isinstance(v,(dict,list))}))
    return candidates,feedback,progress


def native_records(job):
    summaries=[];callbacks=[];details=[]
    folder=ROOT/job/'matlab'
    for p in sorted(folder.glob('request_*.response.json')):
        r=read(p);n=int(p.name.split('_')[1].split('.')[0])
        inputpath=p.with_name(f'request_{n:06d}.input.json')
        py=p.with_name(f'request_{n:06d}.python.json')
        metadata=read(inputpath) if inputpath.is_file() else {}
        admission=read(py) if py.is_file() else {}
        roots=[c for c in r.get('callbacks',[]) if c.get('values',{}).get('phase')=='rootlp']
        root=roots[0] if roots else {}
        vals=root.get('values') or {};output=r.get('output') or {}
        summaries.append(dict(job=job,request_number=n,status=r.get('status'),
            exitflag=r.get('exitflag'),fval=r.get('fval'),final_output=output,
            rootlp_lowerbound_native=vals.get('lowerbound'),rootlp_native_cumulative_s=vals.get('time'),
            rootlp_request_wall_s=root.get('request_wall_seconds'),
            native_MaxTime_s=(r.get('options') or {}).get('MaxTime'),
            native_call_s=(r.get('phase_seconds') or {}).get('intlinprog_call'),
            root_budget_valid=admission.get('budget_valid'),
            accepted_for_evaluation=admission.get('accepted_for_evaluation'),
            request_absolute_deadline=metadata.get('absolute_deadline'),
            nonempty_callback_vectors=sum(bool(c.get('x')) for c in r.get('callbacks',[])),
            scope='native solver-reported objective; local/full objective identity retained, not certified L0 or safe U'))
        for c in r.get('callbacks',[]):
            callbacks.append(dict(job=job,request_number=n,event_number=c.get('event_number'),
                state=c.get('state'),request_wall_s=c.get('request_wall_seconds'),
                phase=(c.get('values') or {}).get('phase'),
                time_native=(c.get('values') or {}).get('time'),
                lowerbound_solver_reported=(c.get('values') or {}).get('lowerbound'),
                fval_solver_reported=(c.get('values') or {}).get('fval'),
                relativegap_solver_reported=(c.get('values') or {}).get('relativegap'),
                numnodes=(c.get('values') or {}).get('numnodes'),
                numfeaspoints=(c.get('values') or {}).get('numfeaspoints'),
                nonempty_vector=bool(c.get('x')),vector_sha256=canonical(c.get('x')),
                time_scope='request wall/native cumulative; no fabricated method-time alignment'))
        details.append(dict(job=job,request_number=n,path=p.relative_to(ROOT).as_posix(),
            response_sha256=sha(p),input_metadata=metadata,
            raw_response_excluding_vectors={k:v for k,v in r.items() if k not in ('x','callbacks')},
            callback_values=[{k:v for k,v in c.items() if k!='x'}|{'nonempty_vector':bool(c.get('x'))}
                for c in r.get('callbacks',[])]))
    return summaries,callbacks,details


def plot(facts):
    os.environ['MPLCONFIGDIR']=str(REPO/'.runtime/k152_matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,(ax,lb)=plt.subplots(2,1,figsize=(9.5,7),sharex=True,
        gridspec_kw={'height_ratios':[3,1]},layout='constrained')
    colors=['#426c9e','#dd7e28','#2c8a58','#9564b5']
    for row,color in zip(facts['methods'],colors):
        points=row['complete_SAFE_receipts'];last=None;xs=[];ys=[]
        for point in points:
            upper=F(point['energy_interval_J'][1])
            if last is None or upper<last:
                xs.append(point['completed_at_s']);ys.append(float(upper));last=upper
        stop=min(300,row.get('method_stop_at_s') or 300)
        if xs:
            ax.step(xs+[stop],ys+[ys[-1]],where='post',label=NAMES[row['job']],color=color)
            ax.scatter(xs,ys,color=color,s=17)
            ax.scatter([stop],[ys[-1]],marker='X',s=55,color=color)
            if stop<300:
                ax.plot([stop,300],[ys[-1],ys[-1]],linestyle=':',color=color)
        else:
            ax.plot([],[],color=color,label=NAMES[row['job']]+' (no saved full SAFE)')
        b=row['L0'];t=number(b.get('formed_at_s'));bound=number(b.get('lower_bound_J'))
        if t is not None and bound is not None and 0<=t<300:
            lb.plot([t,stop],[bound,bound],color=color,linestyle='--',label=NAMES[row['job']])
            lb.scatter([t],[bound],color=color,s=23,marker='|')
        for phase in row['phases']:
            if phase.get('phase_index')==2 and phase.get('start_s') is not None:
                ax.axvline(phase['start_s'],color=color,alpha=.4,linestyle='--',linewidth=.7)
    ax.set(ylabel='Complete SAFE upper U (J)',title='K152: one original-input run per method; no historical splice')
    ax.legend(fontsize=8);ax.grid(alpha=.2)
    lb.set(xlim=(0,300),xlabel='Independent method time (s)',ylabel='Independent L0 (J)')
    lb.ticklabel_format(axis='y',style='plain',useOffset=False);lb.grid(alpha=.2)
    fig.suptitle('X = actual method stop; dotted tail retains existing U without further search',fontsize=10)
    fig.savefig(OUT/'safe_energy_and_L0.png',dpi=180)
    fig.savefig(OUT/'safe_energy_and_L0.svg');plt.close(fig)


def run():
    if not (ROOT/'launcher_result.json').is_file():
        raise RuntimeError('K152 launch is not terminal; analysis refused')
    if OUT.exists():
        raise FileExistsError('Refusing to overwrite completed analysis01')
    ledger=read(ROOT/'ledger.json');declaration=read(ROOT/'declaration.json')
    if ledger.get('state') not in ('COMPLETED','BLOCKED'):
        raise RuntimeError('Ledger is not terminal')
    OUT.mkdir()
    paths=raw_paths();before=manifest(paths)
    source={n:sha(REPO/n) for n in declaration['source_sha256']}
    snapshots={n:sha(ROOT/'source_snapshot'/n) for n in declaration['source_sha256']}
    if len(source)!=178 or source!=declaration['source_sha256'] or snapshots!=source:
        raise ValueError('Frozen 178 sources changed')
    if (any(sha(ROOT/n)!=expected for n,expected in declaration['input_file_sha256'].items())
            or canonical(read(ROOT/'input_instance.json'))!=declaration['input_sha256']):
        raise ValueError('Frozen input bytes/identity changed')
    instance=read(ROOT/'input_instance.json')
    facts=dict(protocol='K152-terminal-pure-archive-analysis-v1',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),methods=[],
        ledger_state=ledger['state'],consumed_calls=ledger['consumed'],
        reserved_method_budget_s=ledger['reserved_method_budget_s'],
        launcher=read(ROOT/'launcher_result.json'),source_sha256=source,
        wrapper_timing=read(ROOT/'wrapper_timing.json') if (ROOT/'wrapper_timing.json').is_file() else None,
        common_entry_imports=read(ROOT/'runtime_imports.json'),
        declaration_sha256=sha(ROOT/'declaration.json'),scope='this round only; no new physical evidence or proof')
    schedules=[];components=[];exclusive=[];phases=[];candidate_rows=[];feedback=[];progress=[]
    native=[];callbacks=[];native_details=[];pairs=[];comparison=[];safe_rows=[];models=[]
    for job in JOBS:
        claimpath=ROOT/'claims'/(job+'_result.json');resultpath=ROOT/job/'result.json'
        if not claimpath.is_file():
            facts['methods'].append(dict(job=job,status='NOT_RUN',complete_SAFE_receipts=[],L0={},phases=[]))
            comparison.append(dict(job=job,execution_status='NOT_RUN'));continue
        claim=read(claimpath);result=read(resultpath) if resultpath.is_file() else {}
        metrics=claim.get('completion_metrics') or {};ev=final_evaluation(result)
        q=interval(ev.get('weighted_energy_J'));usable=claim.get('usable_U_J')
        bound=get_bound(job,result);b=F(bound['lower_bound_J']) if bound.get('lower_bound_J') is not None else None
        initial=interval(metrics.get('initial_complete_SAFE_energy_interval_J'))
        row=dict(job=job,status=claim.get('execution',{}).get('execution_status'),
            raw_state=result.get('state'),raw_reason=result.get('reason'),usable_U_J=usable,
            saved_final_energy_interval_J=ev.get('weighted_energy_J'),
            usable_final_interval_J=ev.get('weighted_energy_J') if usable is not None else None,
            first_SAFE_at_s=metrics.get('first_complete_SAFE_at_s'),
            first_strict_improvement_at_s=metrics.get('first_strict_improvement_at_s'),
            method_stop_at_s=metrics.get('root_stop_at_s'),matlab_startup=metrics.get('matlab_startup'),
            method_return_inclusive_wall_s=claim.get('method_return_inclusive_wall_s'),
            cleanup_s=metrics.get('cleanup_s'),deadline_overshoot_s=metrics.get('deadline_overshoot_s'),
            L0=bound,phases=metrics.get('phases') or [],complete_SAFE_receipts=metrics.get('complete_SAFE_receipts') or [],
            local_scope=result.get('search_scope',result.get('remaining_domain')),
            source_identity_valid=claim.get('source_identity_valid'),
            independently_proven_optimal=result.get('independently_proven_optimal'),
            independently_proven_infeasible=result.get('independently_proven_infeasible'),
            candidate_count=result.get('candidate_count'),thermal_evaluations=result.get('thermal_evaluations'),
            first_legal_candidate_at_s=result.get('first_legal_candidate_at_s',
                (result.get('diagnostic') or {}).get('first_legal_candidate_s')),
            strict_improvement_from_initial=bool(usable is not None and q and initial and q[1]<initial[0]),
            initial_complete_interval_J=metrics.get('initial_complete_SAFE_energy_interval_J'),
            safe_solution_source=result.get('safe_solution_source'),
            milp_improved_initial_upper_bound=result.get('milp_improved_initial_upper_bound',
                result.get('inner_MILP_improved_initial_upper_bound')),
            independent_relative_gap=(float((F(usable)-b)/F(usable)) if usable is not None and b is not None else None),
            phase_quality=claim.get('phase_quality'),claim_sha256=sha(claimpath),result_sha256=sha(resultpath) if resultpath.is_file() else None)
        timing=result.get('timing') or {}
        measured_exclusive=sum((F(str(v)) for v in timing.get('phases_exclusive_s',{}).values()),F(0))
        unattributed=number(timing.get('unattributed_s'))
        row['exclusive_accounting']=dict(measured_exclusive_s=str(measured_exclusive),
            unattributed_s=timing.get('unattributed_s'),root_stop_s=metrics.get('root_stop_at_s'),
            residual_s=(number(metrics.get('root_stop_at_s'))-float(measured_exclusive)-unattributed
                if number(metrics.get('root_stop_at_s')) is not None and unattributed is not None else None),
            scope='saved exclusive logger sum; cleanup not counted a second time')
        facts['methods'].append(row)
        comparison.append(dict(job=job,execution_status=row['status'],usable_U_J=usable,
            energy_low_J=number(q[0]) if q and usable is not None else None,
            energy_upper_J=number(q[1]) if q and usable is not None else None,
            first_SAFE_s=row['first_SAFE_at_s'],first_strict_s=row['first_strict_improvement_at_s'],
            method_stop_s=row['method_stop_at_s'],return_inclusive_s=row['method_return_inclusive_wall_s'],
            matlab_startup_s=(row['matlab_startup'] or {}).get('wall_s'),cleanup_s=row['cleanup_s'],
            certified_L0_J=number(bound.get('lower_bound_J')),L0_formed_at_s=bound.get('formed_at_s'),
            independent_relative_gap=row['independent_relative_gap'],
            independently_proven_optimal=row['independently_proven_optimal']))
        for point in row['complete_SAFE_receipts']:
            safe_rows.append(dict(job=job,**point))
        for phase in row['phases']:
            before_phase=[p for p in row['complete_SAFE_receipts']
                if phase.get('start_s') is not None and p['completed_at_s']<=phase['start_s']]
            through_phase=[p for p in row['complete_SAFE_receipts']
                if phase.get('end_s') is not None and p['completed_at_s']<=phase['end_s']]
            best=lambda seq:min(seq,key=lambda p:F(p['energy_interval_J'][1])) if seq else None
            base=best(before_phase);end=best(through_phase)
            phase.update(best_complete_interval_at_entry=None if base is None else base['energy_interval_J'],
                best_complete_interval_at_end=None if end is None else end['energy_interval_J'],
                strict_phase_improvement=bool(base and end and
                    F(end['energy_interval_J'][1])<F(base['energy_interval_J'][0])))
            phases.append(dict(job=job,**phase))
        for phase,secs in (result.get('timing') or {}).get('phases_exclusive_s',{}).items():
            exclusive.append(dict(job=job,phase=phase,exclusive_s=secs))
        exclusive.append(dict(job=job,phase='unattributed',exclusive_s=(result.get('timing') or {}).get('unattributed_s')))
        sr,candidate=final_schedule_rows(job,result,instance);schedules.extend(sr)
        save(job+'_complete_schedule.json',candidate)
        components.extend(component_rows(job,result,instance))
        cr,fr,pr=candidate_and_feedback(job,result);candidate_rows.extend(cr);feedback.extend(fr);progress.extend(pr)
        row['stored_candidate_records']=len(cr);row['stored_feedback_records']=len(fr)
        nr,cb,nd=native_records(job);native.extend(nr);callbacks.extend(cb);native_details.extend(nd)
        for p in sorted((ROOT/job).rglob('matrix_identities.json')):
            models.append(dict(job=job,path=p.relative_to(ROOT).as_posix(),saved_record=read(p)))
        save(job+'_original_execution_record.json',claim.get('execution'))
    for a in facts['methods']:
        qa=interval(a.get('usable_final_interval_J'))
        for b in facts['methods']:
            if a['job']==b['job']:
                continue
            qb=interval(b.get('usable_final_interval_J'))
            pairs.append(dict(lower_energy_method=a['job'],comparison_method=b['job'],
                both_usable=bool(qa and qb),strict_interval_improvement=bool(qa and qb and qa[1]<qb[0]),
                conservative_reduction_pct=(100*float((qb[0]-qa[1])/qb[0]) if qa and qb else None),
                conservative_reduction_pct_exact=(str(100*(qb[0]-qa[1])/qb[0]) if qa and qb else None),
                reduction_formula='100 * (other saved energy lower - this SAFE upper) / other saved energy lower',
                interpretation='descriptive one-run U comparison; not an exact optimum gap'))
    facts.update(pairwise=pairs,feedback_records=feedback,
        sum_actual_method_stop_s=sum(r.get('method_stop_at_s') or 0 for r in facts['methods']),
        native_scope='native bounds/gaps are solver-reported, and local native objectives are not merged into system certified bounds',
        raw_manifest_sha256=canonical(before))
    for name,rows in [('comparison.csv',comparison),('schedules.csv',schedules),
        ('energy_components.csv',components),('exclusive_costs.csv',exclusive),('phase_timing.csv',phases),
        ('complete_safe_receipts.csv',safe_rows),('candidate_evaluations.csv',candidate_rows),
        ('feedback.csv',feedback),('solver_progress.csv',progress),('native.csv',native),
        ('native_callbacks.csv',callbacks),('strict_pairwise.csv',pairs)]:
        csvsave(name,rows)
    save('facts.json',facts);save('native_details.json',native_details);save('matrix_details.json',models)
    plot(facts)
    lines=['# K152 四方法同轮存档分析','',
        '只读取本轮原始记录；连续物理复核由独立审查另行完成。每方法一次300秒，不拼接历史结果。','',
        '| 方法 | 安全U/J | 首次完整SAFE/s | 首次严格改善/s | 方法停止/s | MATLAB启动/s | 状态 |',
        '|---|---:|---:|---:|---:|---:|---|']
    fmt=lambda x:'未取得／不适用' if x is None else f'{float(F(str(x))):.6f}'
    for row in comparison:
        lines.append('| '+' | '.join([NAMES[row['job']],fmt(row.get('usable_U_J')),
            fmt(row.get('first_SAFE_s')),fmt(row.get('first_strict_s')),fmt(row.get('method_stop_s')),
            fmt(row.get('matlab_startup_s')),str(row.get('execution_status'))])+' |')
    lines.extend(['','严格节能按新区间上端小于对方区间下端判断。认证L0与内部界分列；'
        '单次SA101不支持随机稳定性或普遍排名。联动仅搜索本次种子部署及所声明的两遍局部域，'
        '整体MILP、HEFT、SA保留各自原有设备选择。','',
        f"研究调用消费{ledger['consumed']}次，预留方法预算{ledger['reserved_method_budget_s']}秒。",
        '原生根LP时间为求解器累计回调时间，不能解释为独占LP计算耗时。',
        '相对L0的(U−L0)/U是独立最优相对差距的上界，不是已知确切最优差距。',
        '图中L0只从各方法实际形成时刻开始；提前完成后的虚线仅保留已有U，不代表继续搜索。'])
    (OUT/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    after=manifest(paths)
    checks=dict(protocol='K152-pure-archive-analysis-integrity-v1',
        raw_files_unchanged=before==after,frozen_178_sources_unchanged=source=={n:sha(REPO/n) for n in source},
        frozen_178_snapshots_match=snapshots==source,
        input_identity_preserved=sha(ROOT/'input_instance.json')==before[(ROOT/'input_instance.json').relative_to(REPO).as_posix()],
        research_calls=0,model_constructions=0,thermal_evaluations=0,
        source_count=len(source),raw_file_count=len(before),before_sha256=before,after_sha256=after,
        analysis_script_sha256=sha(Path(__file__)),script_path=Path(__file__).relative_to(REPO).as_posix())
    save('integrity_checks.json',checks)
    if not checks['raw_files_unchanged'] or not checks['frozen_178_sources_unchanged']:
        raise ValueError('Analysis changed original evidence or frozen sources')
    print(json.dumps(dict(out=str(OUT),methods=comparison,integrity=True),ensure_ascii=False))


if __name__=='__main__':
    run()
