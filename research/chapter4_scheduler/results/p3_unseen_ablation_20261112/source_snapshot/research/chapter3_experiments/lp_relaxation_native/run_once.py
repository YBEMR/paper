"""K191: one approved standalone LP diagnostic under the K190 protocol."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
OLD=REPO/'research/chapter3_experiments/results/whole_long_budget01'
PREP=REPO/'research/chapter3_experiments/results/k190_lp_preparation01'
OUT=REPO/'research/chapter3_experiments/results/lp_relaxation_native01'
CONTROL=REPO/'research/chapter3_experiments/results/fixed_integer_native03/source_snapshot/run_once.py'
spec=importlib.util.spec_from_file_location('k191_frozen_generic_control',CONTROL)
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
# The archived generic controller lives deeper than its original source.
# Restore only runtime locations; no archived file is edited.
common.REPO=REPO;common.OLD=OLD;common.OUT=OUT
common.FROZEN=OLD/'source_snapshot/research/chapter3_experiments'
read,sha,write_new=common.read,common.sha,common.write_new
LP_KEYS=('c','A','b','Aeq','beq','lb','ub')
lp=None


def bind_lp():
    global lp
    sys.path.insert(0,str(REPO/'research/chapter3_experiments/lp_relaxation_preparation'))
    import lp_checks
    lp=lp_checks
    return lp


def prepare():
    if OUT.exists():raise FileExistsError('Do not overwrite or reuse diagnostic output')
    p=read(PREP/'protocol_proposal.json')
    files=[f for f in sorted(HERE.iterdir()) if f.suffix in ('.py','.m','.md')]
    bindings={str(CONTROL.relative_to(REPO).as_posix()):sha(CONTROL)}
    for name in ('protocol_proposal.json','precheck.json','internal_review.json'):
        f=PREP/name;bindings[f.relative_to(REPO).as_posix()]=sha(f)
    for name in p['reference_bindings']:bindings[name]=sha(REPO/name)
    for f in (REPO/'research/chapter3_experiments/lp_relaxation_preparation').glob('*.py'):
        bindings[f.relative_to(REPO).as_posix()]=sha(f)
    declaration=dict(protocol='K191-execution-of-K190-original-independent-LP-v1',authorized=True,
        authorization='User requested priority execution of K190 once at 300 seconds under report protocol; no heat or other solves',
        frozen_at_utc=common.now(),method_seconds=300,calendar_seconds=480,native_requests_max=1,
        thermal_integrations_max=0,no_retry=True,no_auto_followup=True,
        proposal_sha256=sha(PREP/'protocol_proposal.json'),bindings=bindings,
        original_sources=p['source_files'],local_interface_sources=p['local_interface_sources'],
        wrapper_sha256={f.name:sha(f) for f in files},options=p['options'],
        original_native_environment=p['original_native_environment'],original_environment=p['original_environment'],
        no_x0_or_intcon_in_native_payload=True,no_SAFE_or_U=True,LP_is_not_internal_root=True,
        generic_controller='immutable K189 controller; only output/admission/script runtime bindings changed')
    write_new(OUT/'declaration.json',declaration)
    for f in files:
        target=OUT/'source_snapshot'/f.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(f,target)
    (OUT/'.gitattributes').write_bytes(b'* -text\n')
    admission()
    print({'prepared':True,'declaration_sha256':sha(OUT/'declaration.json')})


def admission():
    d=read(OUT/'declaration.json')
    if not d['authorized'] or (d['method_seconds'],d['calendar_seconds'],d['native_requests_max'])!=(300,480,1):
        raise ValueError('Authorization/budget drift')
    for name,h in d['bindings'].items():
        if sha(REPO/name)!=h:raise ValueError('Bound source drift: '+name)
    for name,info in d['original_sources'].items():
        if sha(REPO/name)!=info['sha256']:raise ValueError('Original array/source drift: '+name)
    for info in d['local_interface_sources']:
        if sha(info['path'])!=info['sha256']:raise ValueError('Installed native interface drift')
    for name,h in d['wrapper_sha256'].items():
        if sha(HERE/name)!=h or sha(OUT/'source_snapshot'/name)!=h:raise ValueError('Wrapper drift: '+name)
    return d


def verify_options(actual,remaining_limit):
    expected=dict(Algorithm='dual-simplex',Preprocess='none',ConstraintTolerance=1e-9,
        OptimalityTolerance=1e-7,MaxIterations=2049240,Display='off')
    if any(actual.get(k)!=v for k,v in expected.items()):raise ValueError('Native LP option drift')
    limit=actual.get('MaxTime')
    if isinstance(limit,bool) or not isinstance(limit,(int,float)) or not (0<limit<=remaining_limit+1e-9):
        raise ValueError('Native LP MaxTime exceeds same root remainder')
    return True


def load_sent(path):
    from scipy.io import loadmat,whosmat
    if {entry[0] for entry in whosmat(path)}!=set(LP_KEYS):raise ValueError('Unexpected native argument, x0/intcon prohibited')
    raw=loadmat(path,variable_names=list(LP_KEYS))
    return {k:raw[k] if k in ('A','Aeq') else raw[k].reshape(-1) for k in LP_KEYS}


class LPProcess:
    """One fresh MATLAB process, one standalone LP request, frozen cleanup."""
    def __init__(self,bridge,budget,expected_ready):
        self.bridge,self.budget=bridge,budget
        self.clock=time.monotonic;self.started=self.clock();self.deadline=budget.deadline
        self.workdir=OUT/'matlab';self.workdir.mkdir(exist_ok=False)
        self.closed=False;self.proc=None;self.log=None;self.process_tree=None;self.counter=0;self.cleanup=None
        self.metadata={'interface':'standalone linprog; not intlinprog internal root LP','x0_passed':False}
        self.log=(self.workdir/'matlab.log').open('wb')
        prefs=REPO/'.runtime/matlab_prefs';prefs.mkdir(parents=True,exist_ok=True)
        quote=lambda p:Path(p).as_posix().replace("'","''")
        try:
            budget.check()
            script="addpath('%s'); solve_lp_once('%s',%.17g);"%(quote(HERE),quote(self.workdir),budget.remaining)
            self.proc=subprocess.Popen([str(bridge.DEFAULT_MATLAB),'-batch',script],
                env=dict(os.environ,MATLAB_PREFDIR=str(prefs)),stdout=self.log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.process_tree=bridge._capture_owned_process_tree(self.proc,phase='launch')
            self.environment,info=bridge._read_json_until(self.workdir/'ready.json',self.deadline,self.clock,self.proc)
            self.process_tree=bridge._capture_owned_process_tree(self.proc,self.process_tree,phase='ready')
            for k in ('version','release'):
                if self.environment.get(k)!=expected_ready[k]:raise ValueError('Native version drift: '+k)
            expected=Path(bridge.DEFAULT_MATLAB).parent.parent/'toolbox/optim/optim/linprog.m'
            if self.environment.get('linprog_path','').replace('\\','/').lower()!=expected.as_posix().lower():
                raise ValueError('Native linprog path drift')
            if (self.environment.get('status')!='READY' or not self.environment.get('license_checkout')
                    or self.environment.get('license_test')!=expected_ready['license_test']):
                raise RuntimeError('Native license/ready gate failed')
            if not self.process_tree.get('capture_complete'):raise RuntimeError('Native process identity capture failed')
            write_new(self.workdir/'session.json',dict(environment=self.environment,ready_read=info,
                root_deadline=self.deadline,startup_s=self.clock()-self.started,process_tree=self.process_tree,
                native_entry=str(HERE/'solve_lp_once.m'),x0_passed=False,intcon_passed=False))
            budget.check()
        except BaseException as e:
            self.close();e.matlab_cleanup=self.cleanup;raise

    def submit(self,payload,budget):
        if self.counter:raise RuntimeError('Only one LP request is allowed')
        self.counter+=1;budget.check()
        from scipy.io import savemat
        with budget.phase('LP_mat_serialization_and_identity'):
            savemat(self.workdir/'payload.mat',payload,oned_as='column')
            sent=load_sent(self.workdir/'payload.mat')
            # Compare the seven payload arrays before publishing the request.
            for k in LP_KEYS:
                same=lp.numeric._same_matrix(payload[k],sent[k]) if k in ('A','Aeq') else lp.numeric._same_array(payload[k],sent[k])
                if not same:raise ValueError('Native payload drift: '+k)
            write_new(OUT/'transport_identity.json',dict(passed=True,seven_arguments_bitwise_preserved=True,
                x0_sent=False,intcon_sent=False,payload_sha256=sha(self.workdir/'payload.mat')))
        budget.check();remaining=budget.remaining
        write_new(OUT/'request.claim.json',dict(utc=common.now(),root_s=budget.elapsed,number=1,
            declared_remaining_s=remaining,request='linprog only; original bounds'))
        self.bridge._json(self.workdir/'request.json',{'remaining_s':remaining})
        write_new(OUT/'request_publication.json',dict(root_s=budget.elapsed,remaining_s=remaining))
        result,info=self.bridge._read_json_until(self.workdir/'response.json',budget.deadline,self.clock,self.proc)
        result['publication_read']=info;result['budget_valid']=budget.remaining>0
        return result

    def close(self):
        self.bridge.MatlabSession.close(self)


def worker():
    budget=common.RootBudget()
    launch=read(OUT/'launch.claim.json')
    if launch['declaration_sha256']!=sha(OUT/'declaration.json'):raise ValueError('Launch identity drift')
    write_new(OUT/'method.claim.json',dict(utc=common.now(),start=budget.start,deadline=budget.deadline,
        method_seconds=300,declaration_sha256=launch['declaration_sha256'],no_retry=True))
    process=bridge=None;cleanup=numeric=result=None;errors=[];options_match=False;admitted_at=None
    state='NOT_COMPLETED';markers={}
    try:
        d=admission();host=common.context();write_new(OUT/'worker_host.json',host)
        if not common.resource_ok(host):raise RuntimeError('Host/resource gate failed')
        checks=bind_lp();bridge=common.bind_bridge()
        environment=common.check_python_environment(d['original_environment']);write_new(OUT/'python_environment.json',environment)
        with budget.phase('read_original_LP_and_numeric_witnesses'):
            original,receipt=checks.numeric.load_original_mat(OLD/'method/matlab/request_000001.mat')
            key=(OLD/'method/matlab/request_000001.mat').relative_to(REPO).as_posix()
            if receipt['sha256']!=d['original_sources'][key]['sha256']:raise ValueError('Loaded original payload hash drift')
            payload=checks.make_relaxation(original);identity=checks.assert_identity(original,payload)
            initial=checks.check_vector(original,payload,original['x0'],require_objective=False)
            prior=read(REPO/'research/chapter3_experiments/results/fixed_integer_native03/method_return.json')
            prior_check=checks.check_vector(original,payload,prior['result']['x'],prior['result']['fval'])
            if not initial['accepted'] or not prior_check['accepted']:raise ValueError('Archived witness drift')
            write_new(OUT/'input_precheck.json',dict(source=receipt,identity=identity,x0=initial,K189_vector=prior_check))
        budget.check()
        with budget.phase('MATLAB_startup'):
            process=LPProcess(bridge,budget,d['original_native_environment'])
        admission();budget.check();markers['submit_call_s']=budget.elapsed
        result=process.submit(payload,budget);markers['response_received_s']=budget.elapsed
        budget.check()
        if str(result.get('status','')).startswith('BUDGET_EXHAUSTED'):
            raise TimeoutError('Native LP stopped before entry under its remaining guard')
        if result.get('status')!='SOLVED':raise RuntimeError('Native LP interface result: '+str(result))
        request=read(OUT/'request.claim.json')
        options_match=verify_options(result.get('options',{}),request['declared_remaining_s'])
        if result.get('x'):
            with budget.phase('original_LP_numeric_acceptance'):
                numeric=checks.check_vector(original,payload,result['x'],result.get('fval'))
                budget.check();admitted_at=budget.elapsed
        state=checks.interpret(result.get('exitflag'),bool(numeric and numeric['accepted']),
            in_budget=budget.remaining>0,options_match=options_match)
        markers['classification_completed_s']=budget.elapsed
    except BaseException as e:
        cleanup=getattr(e,'matlab_cleanup',None)
        state='LATE_OR_TIMEOUT_UNRESOLVED' if isinstance(e,TimeoutError) else 'TECHNICAL_FAILURE'
        errors.append(dict(type=type(e).__name__,traceback=traceback.format_exc()))
    finally:
        stopped=budget.elapsed
        if process is not None:
            try:process.close();cleanup=process.cleanup
            except BaseException:errors.append(dict(type='CLEANUP_ERROR',traceback=traceback.format_exc()))
        complete=None
        if bridge is not None and (process is not None or cleanup is not None):
            complete=bridge.cleanup_is_complete(cleanup)
            if not complete:errors.append(dict(type='CLEANUP_UNRESOLVED'))
        try:admission();source_preserved=True
        except Exception:
            source_preserved=False;errors.append(dict(type='SOURCE_DRIFT',traceback=traceback.format_exc()))
        write_new(OUT/'method_return.json',dict(utc=common.now(),state=state,result=result,numeric=numeric,
            method_elapsed_s=stopped,wall_including_cleanup_s=budget.elapsed,
            numeric_admission_completed_s=admitted_at,phase_markers=markers,phases=budget.records,
            options_match=options_match,cleanup=cleanup,lifecycle_complete=complete,
            source_preserved=source_preserved,errors=errors,
            technical_completion='COMPLETE' if not errors else 'ERROR_OR_UNRESOLVED',
            request_attempts=0 if process is None else process.counter,
            thermal_integrations=0,new_SAFE_or_U=False,certified_lower_bound=False,
            x0_passed=False,intcon_passed=False,internal_root_LP_reproduction=False,no_retry=True))
    return 2 if errors else 0


def execute():
    # Reuse only the immutable generic process/deadline controller, not an MILP entry.
    common.OUT=OUT;common.REPO=REPO;common.admission=admission;common.__file__=__file__
    return common.execute()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','execute','worker','context'))
    action=parser.parse_args().action
    result={'prepare':prepare,'execute':execute,'worker':worker,
            'context':lambda:print(json.dumps(common.context()))}[action]()
    raise SystemExit(result or 0)
