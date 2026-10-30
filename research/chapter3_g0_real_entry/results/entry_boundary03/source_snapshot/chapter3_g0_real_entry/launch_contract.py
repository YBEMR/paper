"""Data-only one-shot contract. No approval is manufactured by this module."""
import hashlib
import json
import math
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
INPUT='research/chapter3_method_entry_preparation/results/frozen_entry02/common_input.json'
INPUT_SHA='07e458f3f811746f78931a340d258e230a8de4afb62ac0140459feff6a7bf80a'
SCOPE={'method_calls':1,'method_seconds':300,'post_calls':1,'post_seconds':60,
       'method_process_seconds':480,'batch_seconds':720,'retry_count':0}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def save(path,value,*,exclusive=False):
    """Atomic publication, no overwrite for claims and worker tickets."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    if exclusive:
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    else:
        temp=path.with_name(path.name+'.tmp')
        with temp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)


def verify_plan(plan):
    if (plan.get('schema')!='g0-real-single-entry-v1' or plan.get('scope')!=SCOPE
            or plan.get('input')!=INPUT or plan.get('input_sha256')!=INPUT_SHA
            or plan.get('algorithm')!={'fixed_D0':True,'block_capacities':[2,4],
                                      'stage1_deadline_root_s':150}):
        raise ValueError('PLAN_SCOPE_DRIFT')
    if sha(ROOT/INPUT)!=INPUT_SHA:raise ValueError('INPUT_DRIFT')
    sources=plan.get('source_sha256')
    if not isinstance(sources,dict) or not sources:raise ValueError('NO_SOURCE_FREEZE')
    # Cannot omit a runnable new entry module from the frozen manifest.
    required={str(p.relative_to(ROOT)).replace('\\','/') for p in HERE.glob('*.py')}
    required.update(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'research/chapter3_g0').glob('*.py'))
    baseline=read(ROOT/'research/chapter3_g0/tests/fixtures/protected_baseline.json')
    required.update(baseline['protected_source_sha256'])
    if not required.issubset(sources):raise ValueError('INCOMPLETE_ENTRY_MANIFEST')
    for p,h in sources.items():
        target=(ROOT/p).resolve()
        if not target.is_relative_to(ROOT.resolve()) or sha(target)!=h:
            raise ValueError('SOURCE_DRIFT:'+p)
    if not Path(plan['python_executable']).is_file() or not Path(plan['matlab_executable']).is_file():
        raise ValueError('FROZEN_EXECUTABLE_MISSING')
    for p in (plan['python_executable'],plan['matlab_executable']):
        if plan.get('executable_sha256',{}).get(p)!=sha(p):raise ValueError('EXECUTABLE_DRIFT')
    return plan


def load_authorized(plan_file,approval_file,approval_sha256):
    plan=verify_plan(read(plan_file));ph=sha(plan_file)
    if sha(approval_file)!=approval_sha256:raise PermissionError('APPROVAL_BYTES_MISMATCH')
    a=read(approval_file)
    if (a.get('status')!='APPROVED' or a.get('plan_sha256')!=ph or a.get('scope')!=SCOPE
            or a.get('input_sha256')!=INPUT_SHA or not a.get('user_authorization_reference')
            or a.get('source_manifest_sha256')!=digest(plan['source_sha256'])):
        raise PermissionError('NO_MATCHING_USER_RESEARCH_APPROVAL')
    return {'plan':plan,'plan_sha256':ph,'approval_sha256':approval_sha256,
            'plan_file':str(Path(plan_file).resolve()),'approval_file':str(Path(approval_file).resolve())}


def consume_claim(context,output):
    output=Path(output).resolve()
    if not output.is_relative_to((HERE/'results').resolve()) or output.exists():
        raise ValueError('NEW_ISOLATED_OUTPUT_REQUIRED')
    claim=HERE/'claims'/(context['plan_sha256']+'.json')
    value={'plan_sha256':context['plan_sha256'],'approval_sha256':context['approval_sha256'],
           'output':str(output),'input_sha256':INPUT_SHA}
    save(claim,value,exclusive=True)
    output.mkdir(parents=True,exist_ok=False)
    return claim


def validate_worker_ticket(plan_file,approval_file,approval_sha256,ticket_file,token,mode):
    ctx=load_authorized(plan_file,approval_file,approval_sha256)
    t=read(ticket_file);claim=HERE/'claims'/(ctx['plan_sha256']+'.json')
    c=read(claim);out=Path(c['output']).resolve();tf=Path(ticket_file).resolve()
    if (mode not in ('method','post') or tf!=out/mode/'ticket.json'
            or not out.is_relative_to((HERE/'results').resolve())
            or t.get('mode')!=mode or t.get('token')!=token
            or t.get('plan_sha256')!=ctx['plan_sha256']
            or c.get('approval_sha256')!=approval_sha256
            or t.get('approval_sha256')!=approval_sha256):
        raise PermissionError('WORKER_TICKET_IDENTITY_CONFLICT')
    start=t.get('process_started_monotonic_s');end=t.get('absolute_deadline_monotonic_s')
    cap=480 if mode=='method' else 60
    if (type(start) not in (int,float) or type(end) not in (int,float)
            or not all(math.isfinite(v) for v in (start,end)) or start>time.monotonic()
            or end<=time.monotonic() or not 0<end-start<=cap):
        raise PermissionError('INVALID_TICKET_DEADLINE')
    if mode=='post' and t.get('candidate_sha256')!=digest(t.get('candidate')):
        raise PermissionError('POST_CANDIDATE_DRIFT')
    save(tf.parent/'worker_claim.json',{'ticket_sha256':sha(tf),'token':token},exclusive=True)
    ready=read(tf.parent/'monitor_ready.json')
    if (ready.get('token')!=token or ready.get('plan_sha256')!=ctx['plan_sha256']
            or ready.get('pid')!=os.getpid()):
        raise PermissionError('SUPERVISOR_NOT_READY')
    ctx.update(ticket=t,claim=c,output=out)
    return ctx
