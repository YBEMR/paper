"""K133: one frozen numerical-admission check, never a quality rerun."""
import time
ENTRY_STARTED = time.monotonic()  # before all heavy imports and input reading

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import traceback

import numpy as np
from scipy.io import loadmat

import matlab_bridge as bridge
from augmented_payload import (build_augmented_payload, append_complements,
                               validate_projected_vector)

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
OLD=HERE/'results/fixed_unit_pair02'
AUDIT=HERE/'results/numerical_conflict_audit01'
MAT=OLD/'all_opp_start/matlab/request_000001.mat'
LABELS=AUDIT/'row_trace/labels.json'
PROTOCOL='K133-one-augmented-numerical-admission-v1'
TOTAL_SECONDS=180.0
WORK_SECONDS=135.0  # 40 s existing cleanup ceiling + 5 s terminal recording
NATIVE_SECONDS=60.0

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p=Path(p);t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')
    t.replace(p)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def vector_present(value):return value is not None and np.asarray(value).size>0

class TechnicalBudget:
    def __init__(self,started,clock=time.monotonic):
        self.start=started;self.deadline=started+WORK_SECONDS
        self.total_deadline=started+TOTAL_SECONDS;self.clock=clock;self.phases=[]
    @property
    def elapsed(self):return self.clock()-self.start
    @property
    def remaining(self):return max(0.,self.deadline-self.clock())
    def check(self):
        if self.clock()>=self.deadline:raise TimeoutError('K133 original work/evidence deadline reached')
    @contextmanager
    def phase(self,name):
        begin=self.elapsed
        try:yield
        finally:self.phases.append({'phase':name,'start_s':begin,'end_s':self.elapsed})

def native_cap(budget):
    budget.check();return min(NATIVE_SECONDS,budget.remaining)

def original_payload():
    m=loadmat(MAT)
    p={k:m[k] for k in ('c','A','b','Aeq','beq','lb','ub')}
    p['intcon']=m['intcon'].reshape(-1).astype(np.int64)-1
    return p,m['x0'].reshape(-1)

class NumericalRecorder:
    """Numerical array checks only; raw publications are never changed."""
    def __init__(self,original,augmented,meta,budget,validator=validate_projected_vector):
        self.original=original;self.augmented=augmented;self.meta=meta
        self.budget=budget;self.validator=validator;self.next_event=1
        self.events=[];self.vectors=[];self.failed=False;self.failure_reasons=[]
        self.cancel_requested=False;self.transient_reads=[]
    def fail(self,reason,prefix=None):
        self.failed=True
        if reason not in self.failure_reasons:self.failure_reasons.append(reason)
        if prefix is not None and not self.cancel_requested and self.budget.remaining>0:
            prefix.with_suffix('.cancel').write_text('K133 numerical/interface unresolved\n',encoding='ascii')
            self.cancel_requested=True
    def assess(self,x,source,prefix=None,reported_objective=None):
        record={'source':source,'started_s':self.budget.elapsed,'accepted':False}
        if self.budget.remaining<=0:
            record['reason']='WORK_DEADLINE_BEFORE_ARRAY_CHECK'
            self.vectors.append(record);return record
        original_x,report=self.validator(x,self.original,self.augmented,self.meta)
        record.update(report=report,completed_s=self.budget.elapsed,
                      original_vector_sha256=(digest(original_x.tolist()) if original_x is not None else None))
        if reported_objective is not None and np.asarray(reported_objective).size:
            values=np.asarray(reported_objective,dtype=float).reshape(-1)
            objective=(report.get('original') or {}).get('objective')
            tolerance=None if objective is None else 1e-9*max(1.,abs(objective))
            consistent=bool(len(values)==1 and np.isfinite(values).all() and objective is not None
                            and abs(float(values[0])-objective)<=tolerance)
            record['native_objective_check']={'solver_reported':reported_objective,
                'original_c_dot_x':objective,'engineering_tolerance':tolerance,
                'consistent':consistent,'independent_bound_or_energy_claim':False}
            if not consistent:self.fail('NATIVE_OBJECTIVE_MISMATCH',prefix)
        timely=self.budget.remaining>0
        record['within_original_work_deadline']=timely
        record['accepted']=bool(report['accepted'] and timely and not self.failed)
        self.vectors.append(record)
        if not timely:self.fail('WORK_DEADLINE_DURING_ARRAY_CHECK',prefix)
        elif not report['accepted']:self.fail('ORIGINAL_OR_AUGMENTED_NUMERICAL_CHECK_FAILED',prefix)
        return record
    def poll(self,prefix):
        while self.budget.remaining>0:
            path=Path(f'{prefix}.event_{self.next_event:06d}.json')
            try:event=read(path)
            except FileNotFoundError:return
            except (PermissionError,json.JSONDecodeError,UnicodeDecodeError) as exc:
                self.transient_reads.append({'number':self.next_event,'error':type(exc).__name__,'at_s':self.budget.elapsed});return
            if not isinstance(event,dict):
                self.fail('EVENT_NOT_AN_OBJECT',prefix);return
            if event.get('event_number')!=self.next_event:
                self.fail('EVENT_NUMBER_MISMATCH',prefix);return
            record={'number':self.next_event,'kind':event.get('kind'),
                    'state':event.get('state'),'received_s':self.budget.elapsed,
                    'file':path.name,'file_sha256':sha(path)}
            if vector_present(event.get('x')):
                record['vector_check']=self.assess(event['x'],path.name,prefix,
                    reported_objective=(event.get('values') or {}).get('fval'))
            self.events.append(record);self.next_event+=1
    def finalize(self,result,prefix):
        self.poll(prefix)
        expected={int(x['event_number']) for x in result.get('callbacks',[]) if x.get('event_number') is not None}
        seen={x['number'] for x in self.events if x['kind']=='callback'}
        complete=(expected==seen and all('event_number' in x for x in result.get('callbacks',[])))
        if result.get('intlinprog_entered') and not any(x['kind']=='solver_entered' for x in self.events):complete=False
        if not complete:self.fail('CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED',prefix)
        final=None
        if vector_present(result.get('x')):
            if not vector_present(result.get('fval')):self.fail('NATIVE_FINAL_OBJECTIVE_MISSING',prefix)
            final=self.assess(result['x'],'final_return',prefix,reported_objective=result.get('fval'))
        else:self.fail('NATIVE_FINAL_POINT_MISSING',prefix)
        if result.get('status')!='SOLVED' or result.get('exitflag') not in (1,2,3,-1):
            self.fail('NATIVE_STATUS_NOT_AN_ACCEPTED_FINAL_POINT',prefix)
        accepted=bool(final and final['accepted'] and complete and not self.failed
                      and result.get('budget_valid') and self.budget.remaining>0)
        return {'accepted':accepted,'event_publications_complete':complete,
                'expected_callback_numbers':sorted(expected),'checked_callback_numbers':sorted(seen),
                'final_check':final,'latched_unresolved':self.failed,
                'failure_reasons':list(self.failure_reasons),
                'x0_received_is_not_solver_acceptance':True,
                'thermal_safe_claim':False,'independent_certificate':False}

def matrix_identity(payload):
    identity={}
    for key in ('A','Aeq'):
        a=payload[key].tocsc(copy=True);a.sort_indices()
        h=hashlib.sha256()
        for v in (np.asarray(a.shape,dtype='<i8'),a.indptr.astype('<i8'),a.indices.astype('<i8'),a.data.astype('<f8')):h.update(v.tobytes())
        identity[key]={'shape':list(a.shape),'nnz':int(a.nnz),'canonical_sha256':h.hexdigest()}
    for key in ('c','b','beq','lb','ub','intcon'):
        a=np.asarray(payload[key],dtype='<i8' if key=='intcon' else '<f8').reshape(-1)
        identity[key]={'length':len(a),'sha256':hashlib.sha256(a.tobytes()).hexdigest()}
    return identity

def prepare(out,payload_checks,driver_checks):
    out=out.resolve();out.relative_to(REPO);out.mkdir(parents=True,exist_ok=False)
    for p in (payload_checks,driver_checks):
        if read(p).get('passed') is not True:raise ValueError(f'precheck not passed: {p}')
    base=read(AUDIT/'declaration.json')['source_sha256']
    assert all(sha(REPO/n)==h for n,h in base.items())
    extra=[Path(__file__),HERE/'augmented_payload.py',HERE/'run_augmented_payload_precheck.py',HERE/'precheck_augmented_native.py']
    sources=dict(base);sources.update({p.relative_to(REPO).as_posix():sha(p) for p in extra})
    declaration={'protocol':PROTOCOL,'declared_at_utc':datetime.now(timezone.utc).isoformat(),
        'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'authorization':'user continues the single K132 recommended technical admission check',
        'execution_context':'approved_host','native_request_cap':1,'worker_startup_cap':1,
        'total_wall_cap_s':TOTAL_SECONDS,'work_evidence_cap_s':WORK_SECONDS,
        'cleanup_reserve_s':40,'terminal_recording_reserve_s':5,'native_MaxTime_cap_s':NATIVE_SECONDS,
        'source_sha256':sources,'original_mat_sha256':sha(MAT),'labels_sha256':sha(LABELS),
        'prechecks':{p.relative_to(REPO).as_posix():sha(p) for p in (payload_checks,driver_checks)},
        'cut_max_iterations':10,'no_retry':True,'model_rebuilds':0,'thermal_evaluations':0,
        'quality_calls':0,'original_K131_evidence_not_updated':True,
        'candidate_acceptance':'all final/callback full augmented, link and original-prefix residual checks; failures latch',
        'objective_consistency_check':'1e-9*max(1,abs(c_dot_original_x)); engineering array check only, not an energy/gap certificate',
        'global_optimality_or_infeasibility_certification':False}
    save(out/'declaration.json',declaration)
    for p in extra:
        target=out/'source_snapshot'/p.relative_to(REPO);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    save(out/'ledger.json',{'protocol':PROTOCOL,'state':'PREPARED','consumed':0,'native_requests_published':0})
    (out/'protocol.md').write_text('''# K.133：唯一一次增广表达原生接纳技术检查

执行前冻结：原K131新版AB载荷、原x0、K132局部补变量，保持原目标、441整数选择、物理输入及容差。只新增技术适配模块，不接生产方法。

每个final／callback非空向量均校增广行、链接、原前缀原约束，失败锁存未决并取消，不被后续通过覆盖；原有独立完整SAFE保留。所有不可变callback发布必须齐全，迟到数据只诊断。原生收到x0不当求解器接纳。

唯一worker／唯一请求，不重试或补跑。总墙钟180秒含导入、读入、变换、启动、交接、数组校验和清理；工作证据截止135秒，原40秒清理预留、5秒末尾记录。native MaxTime至多60秒且受原剩余时钟约束，不能重置总预算。协作式停止不等同操作系统硬实时保证，实际总耗时另核，超限如实失败。

无热重算、无新完整安全U、无质量比较、无最优／无解证明、不补K131。若同样−2或技术未决，保存后结束；若原生通过，仅支持本载荷技术兼容性。所有成本均登记，不把存档变换当免费初始化。
''',encoding='utf-8')
    print(json.dumps({'state':'PREPARED','source_files':len(sources),'prechecks':len(declaration['prechecks'])}),flush=True)

def run(out):
    out=out.resolve();d=read(out/'declaration.json');budget=TechnicalBudget(ENTRY_STARTED)
    if read(out/'ledger.json')['state']!='PREPARED':raise ValueError('call already consumed or not prepared')
    assert d['protocol']==PROTOCOL and d['total_wall_cap_s']==TOTAL_SECONDS
    assert all(sha(REPO/n)==h for n,h in d['source_sha256'].items())
    assert sha(MAT)==d['original_mat_sha256'] and sha(LABELS)==d['labels_sha256']
    assert all(sha(REPO/n)==h and read(REPO/n).get('passed') is True for n,h in d['prechecks'].items())
    with (out/'claim.json').open('x',encoding='utf-8') as f:json.dump({'consumed':1,'started_at_utc':datetime.now(timezone.utc).isoformat(),'no_retry':True},f)
    save(out/'ledger.json',{'protocol':PROTOCOL,'state':'RUNNING','consumed':1,'native_requests_published':0})
    session=None;rec=None;native=None;admission=None;cleanup=None;error=None;startup_attempts=0
    report={'protocol':PROTOCOL,'technical_acceptance':False,'thermal_safe_claim':False,'quality_claim':False}
    try:
        budget.check()
        with budget.phase('read_and_augment'):
            original,x0=original_payload();augmented,meta=build_augmented_payload(original,read(LABELS))
            full_x0=append_complements(x0,meta)
            prefix,initial=validate_projected_vector(full_x0,original,augmented,meta)
            if not initial['accepted']:raise ValueError('Original x0 failed augmented/original numerical admission')
            save(out/'initial_check.json',initial);save(out/'mapping.json',meta)
            save(out/'matrix_identities.json',{'original':matrix_identity(original),'augmented':matrix_identity(augmented)})
        budget.check()
        with budget.phase('worker_startup'):
            startup_attempts+=1
            session=bridge.MatlabSession(out/'matlab',total_budget_s=budget.remaining,budget=budget,cut_max_iterations=10)
        budget.check()
        rec=NumericalRecorder(original,augmented,meta,budget);session.event_consumer=rec.poll
        with budget.phase('native_request_and_live_array_checks'):
            native=session.solve(augmented,budget=budget,x0=full_x0,solver_max_time_s=native_cap(budget))
        admission=rec.finalize(native,out/'matlab/request_000001')
        report['technical_acceptance']=bool(admission['accepted'])
        report['admission_completed_at_s']=budget.elapsed
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        cleanup=getattr(exc,'matlab_cleanup',None)
        report['admission_completed_at_s']=budget.elapsed
    finally:
        report['work_stopped_at_s']=budget.elapsed
        if session is not None:
            session.event_consumer=None
            try:session.close()
            except BaseException as exc:
                cleanup=getattr(session,'cleanup',None)
                close_error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
                if error is None:error=close_error
                else:error['additional_cleanup_error']=close_error
            else:cleanup=session.cleanup
        report['cleanup_completed_at_s']=budget.elapsed
    report.update(error=error,native_result=native,admission=admission,cleanup=cleanup,
        callback_events=[] if rec is None else rec.events,
        vector_checks=[] if rec is None else rec.vectors,
        callback_transient_reads=[] if rec is None else rec.transient_reads,
        phases=budget.phases,total_limit_s=TOTAL_SECONDS,work_limit_s=WORK_SECONDS,
        native_limit_s=NATIVE_SECONDS,imports_counted=True,model_rebuilds=0,thermal_evaluations=0,
        worker_startups=startup_attempts,
        requests_attempted=0 if session is None else session.counter,
        cleanup_verified=bool(cleanup and bridge.cleanup_is_complete(cleanup)),
        source_unchanged=all(sha(REPO/n)==h for n,h in d['source_sha256'].items()),
        original_mat_unchanged=sha(MAT)==d['original_mat_sha256'],
        new_SAFE_upper_bound=None,independent_optimality=False,independent_infeasibility=False)
    report['total_elapsed_before_final_archive_s']=budget.elapsed
    passed=bool(report['technical_acceptance'] and report['cleanup_verified'] and report['source_unchanged']
                and report['original_mat_unchanged'] and budget.elapsed<=TOTAL_SECONDS and error is None)
    report['state']='TECHNICAL_ACCEPTANCE_PASS' if passed else 'TECHNICAL_UNRESOLVED'
    archive_errors=[]
    try:save(out/'result.json',report)
    except BaseException as exc:
        archive_errors.append({'file':'result.json','type':type(exc).__name__,'message':str(exc)})
        passed=False
    elapsed=budget.elapsed
    ledger={'protocol':PROTOCOL,'state':'COMPLETED' if passed and elapsed<=TOTAL_SECONDS else 'STOPPED_UNRESOLVED',
        'consumed':1,'native_requests_published':len(list((out/'matlab').glob('request_*.request.json'))),
        'native_solver_entered':bool(native and native.get('intlinprog_entered')),
        'technical_acceptance':passed and elapsed<=TOTAL_SECONDS,'total_elapsed_s':elapsed,
        'total_limit_s':TOTAL_SECONDS,'deadline_overrun_s':max(0.,elapsed-TOTAL_SECONDS),
        'no_retry':True,'quality_evidence_added':False,'cleanup_verified':report['cleanup_verified'],
        'archive_errors':archive_errors}
    try:save(out/'ledger.json',ledger)
    except BaseException as exc:
        archive_errors.append({'file':'ledger.json','type':type(exc).__name__,'message':str(exc)});passed=False
    passed=bool(passed and budget.elapsed<=TOTAL_SECONDS)
    print(json.dumps({'state':report['state'],'native_exitflag':None if native is None else native.get('exitflag'),
        'accepted':passed,'elapsed_s':budget.elapsed,'cleanup_verified':report['cleanup_verified'],
        'archive_errors':archive_errors},ensure_ascii=False),flush=True)
    return passed

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--payload-checks',type=Path);parser.add_argument('--driver-checks',type=Path)
    args=parser.parse_args()
    if args.prepare:
        if args.payload_checks is None or args.driver_checks is None:parser.error('prepare requires both precheck records')
        prepare(args.out,args.payload_checks.resolve(),args.driver_checks.resolve())
    else:raise SystemExit(0 if run(args.out) else 1)
