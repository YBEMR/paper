"""One claimed, 180 s native request-read interface precheck on Windows.

Six toy requests use one new worker and one absolute budget. No physical
model, heat evaluator, research method, candidate or old answer is executed.
The Python bridge is unchanged; fault injection wraps its atomic rename.
Do not retry this entry after consuming its fixed claim.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import threading
import time
import traceback
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CLAIM = HERE/'results/request_read_native_claim01.json'
K116 = HERE/'results/shared_search_diagnostic01'
SECONDS = 180
HOLD_SECONDS = .2
READ_WINDOW_SECONDS = 2
ORIGINAL_CONFIG_SHA256 = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
# Identical to test_bridge_softcap.MODEL; not a physical scheduling model.
MODEL = {'c':[1.],'Aeq':[[1.]],'beq':[1.],'lb':[0.],'ub':[1.],'intcon':[0]}
CASES = ('short_lock','malformed_json','persistent_lock','cancel_locked','normal','stop_locked')
WIN32_REFERENCE = 'https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew'


def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,
        allow_nan=False)+'\n',encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    return {path.relative_to(REPO).as_posix():sha(path)
            for path in (Path(__file__).resolve(),HERE/'matlab_bridge.py',HERE/'solve_model.m')}


class InterfaceBudget:
    """The bridge's minimal absolute-budget protocol, with no thermal import."""
    def __init__(self):
        self.seconds = SECONDS
        self.start = time.monotonic()
        self.deadline = self.start+SECONDS

    @property
    def elapsed(self):
        return time.monotonic()-self.start

    @property
    def remaining(self):
        return max(0.,self.deadline-time.monotonic())

    def check(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Single 180 s interface budget exhausted')


def reference_identity():
    """Byte preservation only; no reference candidate/energy is consumed."""
    declaration = json.loads((K116/'declaration.json').read_text(encoding='utf-8'))
    old = declaration['source_sha256']; changed = {}
    for name,digest in old.items():
        path = (REPO/name).resolve(); path.relative_to(REPO)
        current = sha(path)
        if current != digest: changed[name] = {'K116_sha256':digest,'current_sha256':current}
    worker = (HERE/'solve_model.m').relative_to(REPO).as_posix()
    if set(changed)-{worker}:
        raise ValueError('Unexpected change to K116 production sources: '+str(sorted(set(changed)-{worker})))
    parameters = sha(HERE/'config_v01.json')
    if parameters != ORIGINAL_CONFIG_SHA256:
        raise ValueError('Original physical parameters changed')
    files = [K116/'declaration.json',K116/'admission.json',K116/'completion.json',
             K116/'invocation/result.json',K116/'invocation/input_config.json',
             K116/'invocation/input_instance.json',HERE/'config_v01.json']
    if (K116/'verification.json').is_file(): files.append(K116/'verification.json')
    return {'key_evidence_sha256':{path.relative_to(REPO).as_posix():sha(path) for path in files},
            'K116_source_file_count':len(old),'production_source_changes':changed,
            'only_allowed_production_change':worker,'physical_config_sha256':parameters,
            'scope':'byte identity only; no historical schedule, energy or solver answer used'}


class PublicationInjection:
    """Lock the closed production .tmp before exposing its final filename.

    GENERIC_READ plus FILE_SHARE_DELETE permits rename access but denies new
    readers while this handle stays open. Actual rename/lock/read failures
    are recorded; an unsuccessful injection is never silently replaced.
    """
    def __init__(self,prefix,mode,budget):
        self.prefix,self.mode,self.budget = prefix,mode,budget
        self.original_replace = Path.replace
        self.handle = None
        self.mutex = threading.Lock()
        self.done = threading.Event()
        self.controller = None
        self.record = {'mode':mode,'request_prefix':str(prefix),'publication_count':0,
                       'lock_acquired':False,'atomic_rename_succeeded':False,
                       'published_name_read_denied':False,'events':[]}
        self.kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
            wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        self.kernel.CreateFileW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL

    def event(self,name,**values):
        self.record['events'].append({'event':name,'elapsed_s':self.budget.elapsed,**values})

    def release(self,reason):
        with self.mutex:
            if self.handle is not None:
                handle,self.handle = self.handle,None
                if not self.kernel.CloseHandle(handle):
                    self.record['release_error'] = str(ctypes.WinError(ctypes.get_last_error()))
                self.event('lock_released',reason=reason)

    def control(self):
        try:
            if self.done.wait(HOLD_SECONDS): return
            if self.mode == 'short_lock':
                self.release('0.2 s publication hold completed')
            elif self.mode in ('cancel_locked','stop_locked'):
                self.budget.check()
                control = (self.prefix.with_suffix('.cancel') if self.mode == 'cancel_locked'
                           else self.prefix.parent/'stop')
                control.write_text('native request-read precheck\n',encoding='ascii')
                self.event('control_published',path=str(control))
                self.record['control_published'] = True
                # Keep the read lock until the native response has returned.
        except Exception:
            self.record['controller_error'] = traceback.format_exc()

    def replace(self,temporary,target):
        target = Path(target)
        expected = self.prefix.with_suffix('.request.json')
        if target != expected:
            return self.original_replace(temporary,target)
        self.budget.check()
        if temporary != expected.with_suffix(expected.suffix+'.tmp'):
            raise RuntimeError('Request publication did not use the production atomic .tmp')
        self.record['publication_count'] += 1
        if self.record['publication_count'] != 1:
            raise RuntimeError('Unexpected duplicate publication; no injection retry')
        self.record['original_request_sha256'] = sha(temporary)
        if self.mode == 'malformed_json':
            temporary.write_text('{"intentionally_malformed":\n',encoding='utf-8')
            self.record['published_bytes_sha256'] = sha(temporary)
            self.event('complete_malformed_file_prepared')
        lock = self.mode in ('short_lock','persistent_lock','cancel_locked','stop_locked')
        if lock:
            # OPEN_EXISTING=3, FILE_ATTRIBUTE_NORMAL=128; the .tmp writer is
            # already closed by production _json before Path.replace is called.
            handle = self.kernel.CreateFileW(str(temporary),0x80000000,0x00000004,None,3,128,None)
            if handle is None or handle == ctypes.c_void_p(-1).value:
                self.record['lock_error'] = str(ctypes.WinError(ctypes.get_last_error()))
                raise OSError(self.record['lock_error'])
            self.handle = handle; self.record['lock_acquired'] = True
            self.event('lock_acquired_on_temporary')
        try:
            value = self.original_replace(temporary,target)
            self.record['atomic_rename_succeeded'] = True
            self.event('request_atomically_published')
            if lock:
                try:
                    with target.open('rb') as stream: stream.read(1)
                except PermissionError as error:
                    self.record['published_name_read_denied'] = True
                    self.record['probe_error'] = {'type':type(error).__name__,
                        'winerror':getattr(error,'winerror',None),'message':str(error)}
                else:
                    raise RuntimeError('Published request unexpectedly readable while the lock is held')
                if self.mode != 'persistent_lock':
                    self.controller = threading.Thread(target=self.control,daemon=True,
                                                       name='request-read-injection')
                    self.controller.start()
            return value
        except Exception:
            self.record['publication_error'] = traceback.format_exc()
            self.release('publication failed; no alternative injection')
            raise

    def finish(self):
        self.done.set()
        if self.controller is not None: self.controller.join(timeout=.5)
        self.release('native return or precheck failure')
        if self.controller is not None and self.controller.is_alive():
            self.record['controller_error'] = 'Injection controller did not stop'


def request_checks(case,returned,injection):
    """Check native branch receipts, not a simulated read or elapsed guess."""
    info = returned.get('request_publication_read') or {}
    checks = {'publication_used_once':injection.get('publication_count') == 1,
        'atomic_publication_succeeded':injection.get('atomic_rename_succeeded') is True,
        'no_controller_or_lock_cleanup_error':not any(injection.get(key) for key in
            ('controller_error','release_error','publication_error','lock_error')),
        'returned_within_one_budget':returned.get('budget_valid') is True,
        'fixed_read_retry_window':info.get('retry_window_s') == READ_WINDOW_SECONDS}
    if case in ('short_lock','persistent_lock','cancel_locked','stop_locked'):
        checks.update(actual_lock_and_rename=injection.get('lock_acquired') is True
            and injection.get('published_name_read_denied') is True,
            actual_native_read_failure=info.get('read_failures',0) >= 1,
            last_native_error_preserved=info.get('last_error_identifier') == 'MATLAB:fileread:cannotOpenFile'
                and bool(info.get('last_error_message')))
    if case in ('short_lock','normal'):
        checks.update(read_completed=info.get('outcome') == 'READ',
            native_toy_solver_entered=returned.get('intlinprog_entered') is True,
            toy_solved=returned.get('status') == 'SOLVED' and returned.get('accepted_for_evaluation') is True
                and returned.get('x') == [1.] and returned.get('exitflag') == 1)
        if case == 'short_lock':
            checks['retried_then_recovered'] = info.get('attempts',0) > info.get('read_failures',0) >= 1
    elif case == 'malformed_json':
        checks.update(json_decode_error_not_io_retry=returned.get('status') == 'ERROR'
            and info.get('outcome') == 'READ' and info.get('attempts') == 1
            and info.get('read_failures') == 0 and bool(returned.get('error_identifier'))
            and returned.get('error_identifier') not in ('chapter3:requestReadTimeout','MATLAB:fileread:cannotOpenFile'),
            no_solver_entry=returned.get('intlinprog_entered') is False)
    else:
        expected = {'persistent_lock':('RETRY_LIMIT','ERROR','chapter3:requestReadTimeout'),
                    'cancel_locked':('CANCELLED','BUDGET_EXHAUSTED_BEFORE_SOLVER','chapter3:requestReadCancelled'),
                    'stop_locked':('STOPPED','BUDGET_EXHAUSTED_BEFORE_SOLVER','chapter3:requestReadStopped')}[case]
        checks.update(expected_read_outcome=info.get('outcome') == expected[0],
            expected_native_status=returned.get('status') == expected[1],
            expected_error_identifier=returned.get('error_identifier') == expected[2],
            no_solver_entry=returned.get('intlinprog_entered') is False)
        if case == 'persistent_lock':
            checks['read_window_exhausted_while_locked'] = info.get('elapsed_s',-1) >= READ_WINDOW_SECONDS
        else:
            checks['control_was_published_during_lock'] = injection.get('control_published') is True
    return checks


def run(out):
    # Start before the first source/reference read. Imports do not execute a
    # physical model and there is no second Budget for any request.
    budget = InterfaceBudget()
    if os.name != 'nt': raise RuntimeError('This actual file-sharing precheck requires Windows')
    out = Path(out).resolve(); out.relative_to(REPO)
    if out.exists(): raise FileExistsError('Precheck output already exists: '+str(out))
    if CLAIM.exists(): raise FileExistsError('Fixed native precheck claim consumed; no retry')
    before,references = sources(),reference_identity()
    budget.check(); out.mkdir(parents=True,exist_ok=False)
    for name in before:
        destination = out/'source_snapshot'/name
        destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(REPO/name,destination)
    declaration = {'scope':'native request read interface only; no physical safety or performance result',
        'budget_s':SECONDS,'budget_origin':'before source/reference reads; one absolute monotonic deadline',
        'requests':list(CASES),'planned_workers':1,'native_method_calls':1,
        'research_calls':0,'actual_physical_models':0,'actual_thermal_evaluations':0,
        'toy_MODEL':MODEL,'MODEL_origin':'same literal as test_bridge_softcap.MODEL',
        'hold_s':HOLD_SECONDS,'read_retry_window_s':READ_WINDOW_SECONDS,
        'lock_recipe':'CreateFileW GENERIC_READ + FILE_SHARE_DELETE before production Path.replace',
        'win32_reference':WIN32_REFERENCE,'source_sha256':before,'references':references,
        'retry_allowed':False,'budget_extension_allowed':False,'physical_parameter_override':False}
    save(out/'declaration.json',declaration)
    with CLAIM.open('x',encoding='utf-8') as stream:
        json.dump({'state':'CLAIMED_NO_RETRY','out':out.relative_to(REPO).as_posix(),
            'source_sha256':before,'budget_s':SECONDS,'requests':6,
            'declaration_sha256':sha(out/'declaration.json')},stream,indent=2)
    session = None; returned_records = []; checked = {}; error = cleanup_error = None
    worker_start_attempts = 0
    worker_exited_from_stop = False
    try:
        # One workspace-file compatibility probe, before any worker launch.
        # A failed rename/lock probe consumes this attempt and starts no MATLAB.
        probe = PublicationInjection(out/'windows_lock_probe','persistent_lock',budget)
        temporary = probe.prefix.with_suffix('.request.json.tmp')
        temporary.write_text('{"workspace_lock_probe":true}\n',encoding='utf-8')
        try:
            probe.replace(temporary,probe.prefix.with_suffix('.request.json'))
        finally:
            probe.finish()
            save(out/'windows_lock_probe.json',probe.record)
        recovered = json.loads(probe.prefix.with_suffix('.request.json').read_text(encoding='utf-8'))
        checked['workspace_lock_rename_then_release_read_recovered'] = (
            probe.record['atomic_rename_succeeded'] and probe.record['published_name_read_denied']
            and not probe.record.get('release_error') and recovered == {'workspace_lock_probe':True})
        if not checked['workspace_lock_rename_then_release_read_recovered']:
            raise RuntimeError('Workspace Windows lock/rename compatibility probe failed; worker not started')
        from matlab_bridge import MatlabSession
        budget.check()
        worker_start_attempts += 1
        session = MatlabSession(out/'matlab',total_budget_s=budget.remaining,budget=budget)
        for index,case in enumerate(CASES,1):
            budget.check()
            injection = PublicationInjection(session.workdir/f'request_{index:06d}',case,budget)
            returned = None
            try:
                def replace(temporary,target): return injection.replace(temporary,target)
                with patch.object(Path,'replace',new=replace):
                    returned = session.solve(MODEL,budget=budget)
            finally:
                injection.finish()
                save(out/f'injection_{index:02d}_{case}.json',injection.record)
            save(out/f'return_{index:02d}_{case}.json',returned)
            checks = request_checks(case,returned,injection.record)
            returned_records.append({'index':index,'case':case,'checks':checks,
                'request_number':returned.get('request_number'),'status':returned.get('status'),
                'request_publication_read':returned.get('request_publication_read')})
            for name,passed in checks.items(): checked[f'{index}:{case}:{name}'] = bool(passed)
            if session.request_blocked or returned.get('status') in ('WORKER_EXITED','BUDGET_EXHAUSTED'):
                break
        if session.counter == 6 and (session.workdir/'stop').is_file() and budget.remaining > 0:
            try:
                session.proc.wait(timeout=min(5.,budget.remaining))
                worker_exited_from_stop = session.proc.poll() is not None
            except subprocess.TimeoutExpired:
                worker_exited_from_stop = False
        budget.check()
    except Exception:
        error = traceback.format_exc()
    finally:
        elapsed = budget.elapsed
        cleanup_started = time.monotonic()
        if session is not None:
            try: session.close()
            except Exception: cleanup_error = traceback.format_exc()
        cleanup_s = time.monotonic()-cleanup_started
    after_references = reference_identity()
    input_deadlines = []
    if session is not None:
        for index in range(1,session.counter+1):
            path = session.workdir/f'request_{index:06d}.input.json'
            if path.is_file():
                input_deadlines.append(json.loads(path.read_text(encoding='utf-8'))['absolute_deadline'])
    checked.update(source_unchanged=sources() == before,
        K116_evidence_and_other_sources_unchanged=after_references == references,
        no_runtime_or_cleanup_error=error is None and cleanup_error is None,
        one_worker_six_requests=session is not None and session.counter == 6 and len(returned_records) == 6,
        one_unreplenished_deadline=len(input_deadlines) == 6 and all(value == budget.deadline for value in input_deadlines),
        final_stop_ended_worker_before_cleanup=worker_exited_from_stop,
        interface_work_within_180s=elapsed < SECONDS)
    report = {'passed':all(checked.values()),'checks':[{'name':key,'passed':bool(value)} for key,value in checked.items()],
        'count':len(checked),'source_sha256':before,'references_before':references,'references_after':after_references,
        'requests':returned_records,'native_method_calls':worker_start_attempts,'research_calls':0,
        'actual_physical_models':0,'actual_thermal_evaluations':0,
        'native_solver_request_attempts':0 if session is None else session.counter,
        'budget_s':SECONDS,'method_elapsed_s':elapsed,'cleanup_s':cleanup_s,
        'error':error,'cleanup_error':cleanup_error,
        'scope':'actual file-read recovery/failure/control branches only; no research result or new SAFE/U'}
    save(out/'verification.json',report)
    save(out/'environment.json',{'python':platform.python_version(),'platform':platform.platform(),
        'win32_reference':WIN32_REFERENCE})
    print(json.dumps({'passed':report['passed'],'requests':len(returned_records),'elapsed_s':elapsed,
                      'out':str(out)},ensure_ascii=False),flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
