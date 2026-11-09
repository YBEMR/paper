"""One explicitly authorized continuation of the 110 never-invoked jobs.

Read the stopped five-call batch without changing it. Reuse the exact existing
worker and method budgets; no prior candidate, cache or upper bound is passed
to any method. A separate approval and current-source precheck are required.
The failed SA103 invocation is never retried or relabelled as completed.
"""
from copy import deepcopy
import argparse
import io
import json
from pathlib import Path
import unittest

import run_formal_comparison as base

EXPECTED_INVOKED=5
EXPECTED_REMAINING=110
ALLOWED_SOURCE_CHANGES={
    'research/chapter3_experiments/run_formal_comparison.py',
    'research/chapter3_experiments/test_formal_driver.py',
    'research/chapter3_experiments/run_formal_continuation.py',
    'research/chapter3_experiments/test_formal_continuation.py',
}


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def remaining_manifest(previous):
    previous=Path(previous).resolve()
    frozen=read(previous/'declaration.json');old=frozen['manifest'];full=base.manifest()
    if old!=full or full['calls']!=115:
        raise ValueError('original 115-call problem/rules manifest changed')
    calls=read(previous/'calls.json');stop=read(previous/'stop.json')
    if (len(calls)!=EXPECTED_INVOKED or stop.get('reason')!='TECHNICAL_CHECK_FAILED'
        or stop.get('call')!=calls[-1]
        or [c['job'] for c in calls]!=old['jobs'][:EXPECTED_INVOKED]
        or not all(c.get('technical_check',{}).get('passed') is True for c in calls[:-1])
        or calls[-1].get('technical_check',{}).get('passed') is not False
        or calls[-1].get('returncode')!=1):
        raise ValueError('expected stopped five-call prefix is not intact')
    claims=list(previous.glob('*.claim.json'))
    if len(claims)!=len(calls): raise ValueError('calls/claims coverage mismatch')
    by_name={p.name:p for p in claims}
    files=['declaration.json','calls.json','stop.json','source_integrity.json']
    for call in calls:
        job=call['job'];name=job['call_id']+'.claim.json'
        if name not in by_name or read(by_name[name])!=job:
            raise ValueError('call/claim job identity mismatch')
        files.extend([name,job['call_id']+'/result.json',job['call_id']+'/input_instance.json',
                      job['call_id']+'.stdout.txt'])
    if read(previous/'source_integrity.json').get('unchanged') is not True:
        raise ValueError('original source-integrity record is not intact')
    for relative,sha in frozen['source_sha256'].items():
        path=previous/'source_snapshot'/relative
        if base.digest(path)!=sha: raise ValueError('original source snapshot changed')
    current=base.signature();old_source=frozen['source_sha256']
    changed={name for name in set(current)|set(old_source) if current.get(name)!=old_source.get(name)}
    if not changed<=ALLOWED_SOURCE_CHANGES:
        raise ValueError('method/input/safety source changed beyond declared archival continuation')
    pending=deepcopy(full['jobs'][EXPECTED_INVOKED:])
    if len(pending)!=EXPECTED_REMAINING: raise ValueError('remaining call count mismatch')
    for job in pending:
        if (previous/(job['call_id']+'.claim.json')).exists() or (previous/job['call_id']).exists() or (previous/(job['call_id']+'.stdout.txt')).exists():
            raise ValueError('unrecorded prior activity must not be treated as never invoked')
    identity={'previous_batch':str(previous),'original_manifest_sha256':base.canonical_hash(old),
        'files_sha256':{name:base.digest(previous/name) for name in files},
        'source_sha256':old_source,'invoked_call_ids':[c['job']['call_id'] for c in calls],
        'technical_passed':4,'technical_failed':1}
    result=deepcopy(full)
    result.update(schema_version='chapter3-formal-continuation-v1',jobs=pending,calls=len(pending),
        maximum_method_seconds=sum(j['seconds'] for j in pending),continuation_only=True,
        prior_batch_identity=identity,already_invoked=EXPECTED_INVOKED,
        execution_authorization='new explicit continuation approval; original five never repeated')
    return result


def prepare(previous,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    current=remaining_manifest(previous)
    base.save(out/'proposed_manifest.json',current)
    base.save(out/'source_sha256.json',base.signature())
    base.save(out/'approval_record_example.json',{'approved':False,
        'manifest_sha256':base.canonical_hash(current),'user_confirmation_text':None,
        'scope':'continuation example only; never reuse the consumed 115-call approval'})
    return current


def validate_gate(precheck_record,approval_record,previous):
    gate=read(precheck_record);approval=read(approval_record)
    current=remaining_manifest(previous);fingerprint=base.canonical_hash(current)
    checks=gate.get('checks',[])
    if (not checks or gate.get('passed') is not True or gate.get('count')!=len(checks)
        or not all(c.get('passed') is True for c in checks)
        or gate.get('source_sha256')!=base.signature() or gate.get('manifest_sha256')!=fingerprint):
        raise ValueError('current complete passing continuation precheck required')
    if (approval.get('approved') is not True or approval.get('manifest_sha256')!=fingerprint
        or not isinstance(approval.get('user_confirmation_text'),str)
        or not approval['user_confirmation_text'].strip()):
        raise ValueError('explicit remaining-jobs user approval required')
    return current


def precheck(previous,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    initial=remaining_manifest(previous);before=base.signature()
    # Common method checks use existing correctness fixtures only, never a
    # study invocation. The continuation tests use simulated stopped batches.
    base.precheck(out/'common')
    import test_formal_continuation
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_formal_continuation)
    log=io.StringIO()
    tested=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=base.RecordedResult).run(suite)
    (out/'continuation_checks.txt').write_text(log.getvalue(),encoding='utf-8')
    common=read(out/'common/checks.json');checks=list(common['checks'])+tested.records
    checks.extend([
        {'name':'continuation/source_unchanged','passed':before==base.signature()},
        {'name':'continuation/prior_records_unchanged','passed':initial==remaining_manifest(previous)},
        {'name':'continuation/exact_110_never_invoked_jobs','passed':len(initial['jobs'])==110 and initial['maximum_method_seconds']==33000},
    ])
    record={'passed':all(c['passed'] for c in checks),'count':len(checks),'checks':checks,
        'source_sha256':base.signature(),'manifest_sha256':base.canonical_hash(initial),
        'original_research_or_native_solver_run':False,'common_precheck':'common/checks.json'}
    base.save(out/'checks.json',record)
    print(json.dumps({'passed':record['passed'],'count':len(checks),'remaining_calls':len(initial['jobs'])}),flush=True)
    if not record['passed']: raise RuntimeError('failed continuation precheck retained')


def run(precheck_record,approval_record,previous,out):
    current=validate_gate(precheck_record,approval_record,previous)
    return base.execute_batch(current,precheck_record,approval_record,out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','precheck','run'])
    parser.add_argument('--previous',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--precheck-record',type=Path);parser.add_argument('--approval-record',type=Path)
    args=parser.parse_args()
    if args.mode=='prepare':prepare(args.previous,args.out)
    elif args.mode=='precheck':precheck(args.previous,args.out)
    else:run(args.precheck_record,args.approval_record,args.previous,args.out)
