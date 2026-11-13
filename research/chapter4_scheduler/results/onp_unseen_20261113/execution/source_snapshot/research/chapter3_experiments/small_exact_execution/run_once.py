"""K194: one authorized K193 enumeration, no MILP/MATLAB/optimization.

prepare freezes a new execution declaration. launch owns one worker and one
calendar clock. The worker shares that absolute root clock, stores raw receipts
before ledger admission, and never retries an entry or reads historical energy.
"""
from datetime import datetime, timezone
from fractions import Fraction as Q
from hashlib import sha256
from pathlib import Path
import argparse
import ctypes
import json
import math
import os
import subprocess
import sys
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PRODUCTION = HERE.parent
ROOT = PRODUCTION.parents[1]
PREPARATION = PRODUCTION / 'small_exact_preparation'
PROPOSAL = PRODUCTION / 'results/small_exact_protocol01/protocol_proposal.json'
MANIFEST = PROPOSAL.with_name('scene_manifest.jsonl')
sys.path[:0] = [str(HERE), str(PREPARATION), str(PRODUCTION)]

ROOT_SECONDS, CALENDAR_SECONDS, CALL_SECONDS = 2400, 2700, 10


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def atomic_new(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.writing')
    if path.exists():
        raise FileExistsError(path)
    with temp.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    # Windows rename refuses a pre-existing destination; no evidence overwrite.
    os.rename(temp, path)


def append_event(path, value):
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical(value)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def memory_probe():
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (k, ctypes.c_ulonglong) for k in ('total_phys', 'avail_phys', 'total_page',
                'avail_page', 'total_virtual', 'avail_virtual', 'avail_ext')]
    value = Memory()
    value.length = ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise RuntimeError('Cannot read required resource preflight')
    return {'physical_available_bytes': value.avail_phys,
            'commit_available_bytes': value.avail_page,
            'passed': value.avail_phys >= 256*2**20 and value.avail_page >= 512*2**20}


def source_paths():
    files = list(HERE.glob('*.py')) + [PREPARATION/'contract.py',
        PRODUCTION/'small_domain_precheck/domain/core.py',
        PRODUCTION.parent/'v1_evaluator/interval.py']
    files += [PRODUCTION/name for name in ['inputs.py', 'schedules.py', 'start_domain.py',
        'thermal.py', 'control_policy.py']]
    return sorted(set(files))


def verify_sources(declaration):
    for relative, expected in declaration['source_sha256'].items():
        if digest(ROOT/relative) != expected:
            raise ValueError('SOURCE_DRIFT: '+relative)


def prepare(out, *, fixture_only=False):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    proposal = json.loads(PROPOSAL.read_bytes())
    if digest(ROOT/proposal['input_path']) != proposal['input_sha256'] or \
       digest(ROOT/proposal['config_path']) != proposal['config_sha256'] or \
       digest(MANIFEST) != proposal['manifest_sha256']:
        raise ValueError('K193 frozen input/config/manifest drift')
    for src, dest in [(ROOT/proposal['input_path'], 'input_instance.json'),
                      (ROOT/proposal['config_path'], 'input_config.json'),
                      (MANIFEST, 'scene_manifest.jsonl')]:
        with (out/dest).open('xb') as stream:
            stream.write(src.read_bytes())
    identities = {path.relative_to(ROOT).as_posix(): digest(path) for path in source_paths()}
    for relative in identities:
        dest = out/'source_snapshot'/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write((ROOT/relative).read_bytes())
    declaration = {'protocol':'K194-K193-enumeration-once-v1', 'prepared_utc':now(),
        'authorized':True, 'fixture_only':fixture_only,
        'authorization':'Human replied 继续吧 to the explicit K193 recommendation to approve only enumeration: <=1550 calls, each <=10s, shared 2400s root /2700s calendar. Whole MILP is not authorized.',
        'proposal_sha256':digest(PROPOSAL), 'root_seconds':ROOT_SECONDS,
        'calendar_seconds':CALENDAR_SECONDS, 'per_scene_seconds':CALL_SECONDS,
        'evaluations_at_most':1550, 'retry_or_resume':False,
        'input_sha256':proposal['input_sha256'], 'config_sha256':proposal['config_sha256'],
        'manifest_sha256':proposal['manifest_sha256'], 'source_sha256':identities,
        'python_version':sys.version, 'python_executable':sys.executable,
        'accuracy':{k:json.loads((out/'input_config.json').read_bytes())['accuracy_targets'][k]
            for k in ['temperature_enclosure_width_K','energy_absolute_error_J','energy_relative_error']},
        'independent_epsilon_J':'0.000001', 'optimizer_calls':0, 'MATLAB_starts':0,
        'evidence_cutoff':'inner scene completion/strict point formation before both absolute deadlines; no post-cutoff new energy',
        'clock_scope':'parent begins root before declaration and input hash reads; child shares root_start/deadline, no reset',
        'source_check':'before launch/worker, every 50 returned calls, and end; original loaded modules and source snapshot frozen',
        'old_receipt_cache_or_best_solution_input':False,
        'whole_MILP_authorized':False}
    atomic_new(out/'declaration.json',declaration)
    return declaration


def read_payload(out, declaration):
    for file, key in [('input_instance.json','input_sha256'),('input_config.json','config_sha256'),
                      ('scene_manifest.jsonl','manifest_sha256')]:
        if digest(out/file) != declaration[key]:
            raise ValueError('Payload drift: '+file)
    instance = json.loads((out/'input_instance.json').read_bytes())
    config = json.loads((out/'input_config.json').read_bytes())
    manifest = [json.loads(line) for line in (out/'scene_manifest.jsonl').read_bytes().splitlines()]
    if len(manifest)!=1550 or [r['ordinal'] for r in manifest]!=list(range(1,1551)):
        raise ValueError('Incomplete/invalid manifest')
    if len({r['id'] for r in manifest})!=1550:
        raise ValueError('Duplicate manifest identity')
    for row in manifest:
        if sha256(canonical(row['candidate']).encode()).hexdigest()!=row['id']:
            raise ValueError('Candidate identity drift')
    return instance, config, manifest


def reference_data(manifest, records, instance):
    import contract
    from schedules import validate_schedule
    result = contract.envelope(manifest, records)
    output = {'state':result['state'], 'lower_bound_J':str(result['lower']) if result['lower'] is not None else '+infinity',
        'upper_bound_J':str(result['upper']) if result['upper'] is not None else '+infinity',
        'gap_J':str(result['gap']) if result['gap'] is not None else None,
        'epsilon_J':'0.000001', 'unique_optimum_proven':False,
        'groups':[{'scene_id':sid,'shared_A_device':unit,
            **{key:str(value) if isinstance(value,Q) else value for key,value in bounds.items()}}
            for (sid,unit),bounds in result['groups'].items()],
        'complete_SAFE_candidate':None, 'complete_SAFE_energy_J':None,
        'chosen_scene_ids':None, 'physical_kernel_independently_validated':False}
    if result['upper'] is not None:
        unit = min((bounds['upper'],unit) for unit,bounds in result['per_device'].items()
                   if bounds['upper'] is not None)[1]
        by_id={row['id']:row for row in manifest}
        ids={sid:result['groups'][(sid,unit)]['SAFE_witness_id'] for sid in ['AB_offset_0ms','AC_offset_0ms']}
        candidate={'scenes':{sid:by_id[key]['candidate']['scenes'][sid] for sid,key in ids.items()}}
        legality=validate_schedule(instance,candidate)
        if legality['state']!='SCHEDULE_VALID_THERMAL_UNCHECKED':
            raise ValueError('SAFE scene aggregation has illegal complete deployment')
        energies=[list(map(Q,records[key]['energy_J'])) for key in ids.values()]
        output.update(shared_A_device=unit, complete_SAFE_candidate=candidate,
            complete_SAFE_energy_J=[str(sum(v[i] for v in energies)/2) for i in [0,1]],
            chosen_scene_ids=ids, complete_structural_legality=legality)
    return output


def worker(out, expected_sha, root_start, *, evaluator=None, admitter=None, clock=time.monotonic):
    out=Path(out).resolve()
    if digest(out/'declaration.json')!=expected_sha:
        raise ValueError('Declaration identity mismatch')
    declaration=json.loads((out/'declaration.json').read_bytes())
    if not declaration['authorized']:
        raise ValueError('Missing stage authorization')
    if declaration['fixture_only'] and (evaluator is None or admitter is None):
        raise ValueError('Fixture may not call the real evaluator')
    if declaration['root_seconds']!=ROOT_SECONDS or declaration['per_scene_seconds']!=CALL_SECONDS:
        raise ValueError('Budget constants drift')
    deadline=root_start+ROOT_SECONDS
    from thermal import Budget, Exhausted
    from admission import admit, scene_view
    if evaluator is None:
        from thermal import evaluate_candidate
        evaluator=evaluate_candidate
    admitter=admit if admitter is None else admitter

    class CallBudget(Budget):
        def __init__(self):
            super().__init__(seconds=CALL_SECONDS)
            self.start=clock()
            self.deadline=min(deadline,self.start+CALL_SECONDS)
        @property
        def elapsed(self): return clock()-self.start
        def check(self):
            if clock()>=self.deadline: raise Exhausted('wall_time_limit')

    atomic_new(out/'method.claim.json',{'utc':now(),'root_start':root_start,'root_deadline':deadline,
        'declaration_sha256':expected_sha,'retry_allowed':False})
    (out/'receipts').mkdir(exist_ok=False)
    ledger=out/'ledger.jsonl'
    records={}
    manifest=None
    calls_started=0
    stop_reason=None
    try:
        verify_sources(declaration)
        instance,config,manifest=read_payload(out,declaration)
        views={s['id']:scene_view(instance,s['id']) for s in instance['scenarios']}
        view_hashes={sid:sha256(canonical(view).encode()).hexdigest() for sid,view in views.items()}
        append_event(ledger,{'event':'RUN_START','utc':now(),'root_elapsed_s':clock()-root_start})
        for entry in manifest:
            if clock()>=deadline:
                stop_reason='ROOT_TIME_LIMIT';break
            budget=CallBudget()
            budget.check()
            calls_started+=1
            meta={'ordinal':entry['ordinal'],'id':entry['id'],'scene_id':entry['scene_id'],
                'full_input_sha256':declaration['input_sha256'],
                'scene_view_sha256':view_hashes[entry['scene_id']],
                'candidate_sha256':entry['id'],'declaration_sha256':expected_sha,
                'call_start':budget.start,'call_deadline':budget.deadline,'root_deadline':deadline}
            append_event(ledger,{'event':'CALL_STARTED',**meta})
            try:
                raw=evaluator(views[entry['scene_id']],entry['candidate'],accuracy=declaration['accuracy'],budget=budget)
                returned=clock()
                raw_path=out/'receipts'/f"{entry['ordinal']:04d}_{entry['id']}.json"
                atomic_new(raw_path,{'request':meta,'returned_root_elapsed_s':returned-root_start,
                                    'raw_receipt':raw})
                record=admitter(instance,entry,raw,budget.start,budget.deadline,deadline,declaration['accuracy'])
                admission_path=raw_path.with_name(raw_path.stem+'.admission.json')
                atomic_new(admission_path,record)
                records[entry['id']]=record
                append_event(ledger,{'event':'CALL_FINISHED',**meta,'state':record['state'],
                    'reason':record.get('reason'),'technical_stop':record.get('technical_stop',False),
                    'raw_file':raw_path.relative_to(out).as_posix(),'raw_sha256':digest(raw_path),
                    'admission_file':admission_path.relative_to(out).as_posix(),
                    'admission_sha256':digest(admission_path),
                    'call_return_s':returned-budget.start,'root_elapsed_s':clock()-root_start})
                if record.get('technical_stop'):
                    stop_reason='TECHNICAL_RECEIPT: '+str(record.get('reason'));break
            except BaseException as error:
                stop_reason=type(error).__name__+': '+str(error)
                records.setdefault(entry['id'],{'state':'TECHNICAL_UNRESOLVED','energy_J':None,'reason':stop_reason})
                break
            if calls_started%50==0:
                verify_sources(declaration)
                status={state:sum(row['state']==state for row in records.values())
                        for state in ['SAFE','VIOLATION','UNRESOLVED','TECHNICAL_UNRESOLVED']}
                append_event(ledger,{'event':'PROGRESS','calls_started':calls_started,
                    'root_elapsed_s':clock()-root_start,'counts':status})
                print(json.dumps({'completed':calls_started,'root_elapsed_s':round(clock()-root_start,3),**status}),flush=True)
        verify_sources(declaration)
        reference=reference_data(manifest,records,instance)
        reference['formed_root_elapsed_s']=clock()-root_start
        reference['formed_before_root_deadline']=clock()<deadline
        reference['source_integrity_unchanged']=True
        reference['fixture_only']=declaration['fixture_only']
        reference['formal_reference_accepted']=(not declaration['fixture_only'] and
            calls_started==1550 and stop_reason is None and reference['formed_before_root_deadline']
            and reference['state']=='FINITE_DOMAIN_EPSILON_OPTIMAL'
            and all(row['state'] in {'SAFE','VIOLATION'} for row in records.values()))
        atomic_new(out/'reference.json',reference)
        if reference['complete_SAFE_candidate'] is not None:
            atomic_new(out/'best_complete_candidate.json',reference['complete_SAFE_candidate'])
        for entry in manifest:
            records.setdefault(entry['id'],{'state':'NOT_STARTED', 'energy_J':None,
                'reason':'NOT_STARTED_ROOT_LIMIT' if stop_reason=='ROOT_TIME_LIMIT' else 'NOT_STARTED_AFTER_TECHNICAL_STOP'})
        atomic_new(out/'coverage_records.json',records)
        counts={state:sum(row['state']==state for row in records.values())
                for state in ['SAFE','VIOLATION','UNRESOLVED','TIMEOUT','TECHNICAL_UNRESOLVED','NOT_STARTED']}
        terminal={'state':'COMPLETED' if calls_started==1550 and stop_reason is None else 'STOPPED',
            'reason':stop_reason,'counts':counts,'calls_started':calls_started,'root_elapsed_s':clock()-root_start,
            'reference_state':reference['state'],'reference_formed_before_root_deadline':reference['formed_before_root_deadline'],
            'formal_reference_accepted':reference['formal_reference_accepted'],
            'fixture_only':declaration['fixture_only'],
            'optimizer_calls':0,'MATLAB_starts':0,'retries':0,'whole_MILP_started':False}
    except BaseException as error:
        terminal={'state':'TECHNICAL_STOP','reason':type(error).__name__+': '+str(error),
            'calls_started':calls_started,'root_elapsed_s':clock()-root_start,
            'fixture_only':declaration['fixture_only'],'formal_reference_accepted':False,
            'optimizer_calls':0,'MATLAB_starts':0,'retries':0,'whole_MILP_started':False}
        if manifest is not None and not (out/'coverage_records.json').exists():
            for entry in manifest:
                records.setdefault(entry['id'],{'state':'NOT_STARTED','energy_J':None,
                    'reason':'NOT_STARTED_AFTER_TECHNICAL_STOP'})
            atomic_new(out/'coverage_records.json',records)
            terminal['counts']={state:sum(row['state']==state for row in records.values())
                for state in ['SAFE','VIOLATION','UNRESOLVED','TIMEOUT','TECHNICAL_UNRESOLVED','NOT_STARTED']}
    atomic_new(out/'terminal.json',terminal)
    print(json.dumps(terminal),flush=True)
    return terminal


def launch(out, expected_sha):
    out=Path(out).resolve()
    started=time.monotonic()  # before stage declaration/input reads; shared with worker
    if digest(out/'declaration.json')!=expected_sha:
        raise ValueError('Declaration identity mismatch')
    declaration=json.loads((out/'declaration.json').read_bytes())
    if declaration['fixture_only'] or not declaration['authorized']:
        raise ValueError('Real launch forbidden for fixture/unapproved declaration')
    verify_sources(declaration)
    resource=memory_probe()
    atomic_new(out/'resource_preflight.json',resource)
    if not resource['passed']:
        raise ValueError('Resource preflight insufficient; no worker launched')
    atomic_new(out/'launch.claim.json',{'utc':now(),'root_start':started,
        'calendar_deadline':started+CALENDAR_SECONDS,'declaration_sha256':expected_sha,'retry_allowed':False})
    args=[sys.executable,'-B',str(Path(__file__).resolve()),'worker',str(out),
          '--declaration-sha',expected_sha,'--root-start',repr(started)]
    with (out/'worker_stdout.txt').open('x',encoding='utf-8') as stdout, \
         (out/'worker_stderr.txt').open('x',encoding='utf-8') as stderr:
        process=subprocess.Popen(args,cwd=ROOT,stdout=stdout,stderr=stderr,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        atomic_new(out/'process_identity.json',{'pid':process.pid,'created_utc':now(),
            'parent_pid':os.getpid(),'args':args,'owned_worker_only':True})
        killed=False
        while process.poll() is None:
            if time.monotonic()>=started+CALENDAR_SECONDS:
                process.terminate();killed=True;break
            time.sleep(0.5)
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=10);killed=True
    terminal={'state':'WORKER_EXITED' if not killed else 'CALENDAR_TERMINATED',
        'returncode':process.returncode,'calendar_elapsed_s':time.monotonic()-started,
        'worker_pid':process.pid,'worker_exited':process.poll() is not None,
        'optimizer_calls':0,'MATLAB_starts':0,'retry':False}
    atomic_new(out/'supervisor_terminal.json',terminal)
    print(json.dumps(terminal),flush=True)
    return terminal


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','launch','worker'])
    parser.add_argument('out',type=Path)
    parser.add_argument('--declaration-sha')
    parser.add_argument('--root-start',type=float)
    args=parser.parse_args()
    if args.action=='prepare':
        prepare(args.out);print(digest(args.out/'declaration.json'))
    elif args.action=='launch':
        if not args.declaration_sha: parser.error('launch requires frozen declaration SHA')
        launch(args.out,args.declaration_sha)
    else:
        if not args.declaration_sha or args.root_start is None or not math.isfinite(args.root_start):
            parser.error('worker requires frozen declaration SHA and shared root start')
        # A real enumeration worker must never launch another native process.
        with patch('subprocess.Popen',side_effect=AssertionError('Native operation forbidden in enumeration worker')):
            worker(args.out,args.declaration_sha,args.root_start)
