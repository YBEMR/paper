"""Root-lived MATLAB session with a separately scoped startup/request wait.

No process is launched by import. REAL requires the one-shot authorization;
all preparation tests use explicit simulated process and transport functions.
The original worker script, native solve and close implementations are reused.
"""
from copy import deepcopy
import hashlib
import importlib
import math
import os
import json
from pathlib import Path
import subprocess
import sys

from research.chapter3_g0.budget import ScopeExhausted
from .gating import require_permit, require_simulation_dependencies
from .settlement import BoundedSettlement


def _legacy():
    directory=Path(__file__).resolve().parents[1]/'chapter3_experiments'
    if str(directory) not in sys.path:
        sys.path.insert(0,str(directory))
    kernel=importlib.import_module('matlab_bridge')
    if Path(kernel.__file__).resolve()!=directory/'matlab_bridge.py':
        raise ImportError('unexpected native bridge source')
    return kernel


def source_identity():
    directory=Path(__file__).resolve().parents[1]/'chapter3_experiments'
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__),directory/'matlab_bridge.py',directory/'solve_model.m')}


def production_dependencies(permit):
    if require_permit(permit)!='REAL':
        raise PermissionError('production transport requires an approved REAL permit')
    kernel=_legacy()
    return dict(kernel=kernel,launch=subprocess.Popen,read_json=kernel._read_json_until,
        write_json=kernel._json,capture_tree=kernel._capture_owned_process_tree,
        open_log=lambda path:path.open('wb'),
        preference_directory=kernel.REPO/'.runtime/matlab_prefs',
        matlab_path=kernel.DEFAULT_MATLAB,environment=dict(os.environ),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


class ScopedMatlabSession(BoundedSettlement):
    """Same root Budget object; lifetime root-bound, waits scope-bound.

    The startup block deliberately mirrors the original constructor. The
    whitelist differences are dependency injection, provenance, root lifetime
    versus ready-wait deadline, and explicit request-settlement evidence.
    """
    def __init__(self,workdir,*,budget,permit,dependencies=None,total_budget_s=None,
                 matlab_path=None,cut_max_iterations=10,clock=None):
        kind=require_permit(permit)
        if kind=='REAL' and matlab_path is not None:
            raise ValueError('REAL_MATLAB_PATH_OVERRIDE_FORBIDDEN')
        require_simulation_dependencies(permit,dependencies)
        if dependencies is None:
            dependencies=production_dependencies(permit)
        required=('kernel','launch','read_json','write_json','capture_tree','open_log',
                  'preference_directory','matlab_path','environment','creationflags')
        if any(key not in dependencies for key in required):
            raise ValueError('explicit transport dependency set incomplete')
        self.dependencies=dict(dependencies);self.permit=permit
        self.kernel=dependencies['kernel'];self.budget=budget
        self.clock=budget.clock if clock is None else clock
        if self.clock is not budget.clock:
            raise ValueError('native transport must use the root clock')
        budget.check()
        self.started=self.clock()
        self.deadline=float(budget.deadline)
        self.startup_deadline=min(self.deadline,budget.start+budget.effective_deadline_elapsed_s)
        self.cut_max_iterations=self.kernel._cut_iteration_limit(cut_max_iterations)
        if total_budget_s is not None and (not math.isfinite(total_budget_s) or total_budget_s<=0):
            raise ValueError('total_budget_s must be finite and positive')
        self.workdir=Path(workdir).resolve();self.counter=0
        self.closed=False;self.request_blocked=False;self.request_settled=True
        self.proc=self.log=None;self.event_consumer=None;self.process_tree=None
        self.workdir.mkdir(parents=True,exist_ok=False)
        prefs=Path(dependencies['preference_directory'])
        prefs.mkdir(parents=True,exist_ok=True)
        executable=Path(dependencies['matlab_path'] if matlab_path is None else matlab_path)
        self.metadata=dict(scope='g0-root-life-scope-wait-v1',evidence_kind=kind,
            matlab_executable=str(executable),preference_directory=str(prefs),
            worker_guard_seconds=max(0,self.deadline-self.clock()),
            external_absolute_deadline=self.deadline,ready_read_deadline=self.startup_deadline,
            method_deadline_bound=True,source_sha256=source_identity(),
            warm_start_shared=False,candidate_or_thermal_cache_shared=False,
            engineering_compatibility={'IntegerPreprocess':'none','LPPreprocess':'none',
                                       'mathematical_model_unchanged':True},
            cut_max_iterations_declared=self.cut_max_iterations,
            cut_max_iterations_scope='native_cut_pass_limit_only',
            requested_total_budget_s=total_budget_s,
            startup_scope_snapshot=budget.capture_scope(),
            lifetime_rule='root deadline, never first-slot remaining time')
        self.metadata['startup_intervals']={'constructor_start_s':self.started-budget.start}
        write=dependencies['write_json']
        write(self.workdir/'session.json',self.metadata)
        try:
            budget.check()
            guard=self.deadline-self.clock()
            quote=lambda p:Path(p).as_posix().replace("'","''")
            script="addpath('%s'); solve_model('%s',%.17g);" % (
                quote(self.kernel.HERE),quote(self.workdir),guard)
            self.log=dependencies['open_log'](self.workdir/'matlab.log')
            budget.check()
            self.proc=dependencies['launch']([str(executable),'-batch',script],
                env=dict(dependencies['environment'],MATLAB_PREFDIR=str(prefs)),
                stdout=self.log,stderr=subprocess.STDOUT,
                creationflags=dependencies['creationflags'])
            self.metadata['pid']=self.proc.pid
            write(self.workdir/'session.json',self.metadata)
            self.metadata['startup_intervals']['ready_wait_start_s']=budget.elapsed
            try:
                self.environment,read_info=dependencies['read_json'](
                    self.workdir/'ready.json',self.startup_deadline,self.clock,self.proc)
            finally:
                self.metadata['startup_intervals']['ready_wait_end_s']=budget.elapsed
            self.metadata['ready_publication_read']=read_info
            if self.environment.get('status')!='READY':
                raise RuntimeError('MATLAB worker unavailable: '+str(self.environment))
            if self.environment.get('release')!='2023b':
                raise RuntimeError('native bridge requires MATLAB R2023b')
            budget.check()
            self.process_tree=dependencies['capture_tree'](self.proc,phase='ready')
            self.metadata.update(process_tree_at_ready=deepcopy(self.process_tree),
                startup_wall_seconds=self.clock()-self.started,startup_outcome='READY')
            self.metadata['startup_intervals']['ready_accepted_s']=budget.elapsed
            write(self.workdir/'session.json',self.metadata)
        except BaseException as error:
            self.metadata.update(startup_outcome='FAILED_OR_DEADLINE',
                startup_wall_seconds=self.clock()-self.started,
                startup_error=f'{type(error).__name__}: {error}')
            if hasattr(error,'diagnostics'):
                self.metadata['startup_publication_read']=deepcopy(error.diagnostics)
            try:
                write(self.workdir/'session.json',self.metadata)
            except Exception as archive_error:
                self.metadata['startup_archive_error']=repr(archive_error)
            try:
                self.metadata['startup_intervals']['failure_cleanup_start_s']=budget.elapsed
                self.close()
            except BaseException as cleanup_error:
                self.cleanup=getattr(self,'cleanup',{})
                self.cleanup['cleanup_error']=repr(cleanup_error)
            finally:
                self.metadata['startup_intervals']['failure_cleanup_end_s']=budget.elapsed
            # A late file may diagnose a timeout, never make it a READY success.
            # One non-waiting read only; no request, clock change or evaluation.
            late={'observed':False,'accepted_for_startup':False,
                  'observed_at_elapsed_s':budget.elapsed,'after_deadline':self.clock()>=self.startup_deadline}
            try:
                path=self.workdir/'ready.json'
                if path.is_file():
                    value=json.loads(path.read_text(encoding='utf-8-sig'))
                    late.update(observed=True,status=value.get('status'),release=value.get('release'),
                                license_checkout=value.get('license_checkout'))
            except Exception as read_error:
                late['read_error']=type(read_error).__name__+': '+str(read_error)
            self.metadata['failed_startup_publication_observation']=late
            try:
                write(self.workdir/'session.json',self.metadata)
            except Exception as archive_error:
                self.metadata['post_cleanup_archive_error']=repr(archive_error)
            error.matlab_cleanup=getattr(self,'cleanup',{})
            error.matlab_workdir=str(self.workdir)
            error.matlab_startup_metadata=deepcopy(self.metadata)
            raise

    def solve(self,model,remaining_s=None,budget=None,x0=None,solver_max_time_s=None):
        active=self.budget if budget is None else budget
        if active is not self.budget:
            raise ValueError('native request must use the identical root budget')
        if self.closed or self.request_blocked or not self.request_settled:
            raise RuntimeError('worker closed or previous request unsettled')
        active.check()
        available=active.remaining
        if remaining_s is not None:
            if not math.isfinite(remaining_s) or remaining_s<=0:
                raise ValueError('remaining_s must be finite and positive')
            available=min(available,remaining_s)
        cap=available if solver_max_time_s is None else min(available,solver_max_time_s)
        if not math.isfinite(cap) or cap<=0:
            raise ValueError('native MaxTime must be positive and scope bounded')
        previous=self.counter
        scope=active.capture_scope();evidence_deadline=active.effective_deadline_elapsed_s
        self.request_settled=False
        try:
            returned=self.kernel.MatlabSession.solve(self,model,remaining_s=available,
                budget=active,x0=x0,solver_max_time_s=cap)
        except BaseException:
            self.request_blocked=True
            raise
        self.request_settled=(returned.get('status') in ('SOLVED','BUDGET_EXHAUSTED_BEFORE_PUBLICATION')
                              and not self.request_blocked)
        self.note_request_return(returned,previous,scope,evidence_deadline)
        returned=dict(returned)
        returned.update(request_settled=self.request_settled,
                        g0_effective_limit_s=available,g0_session_deadline=self.deadline)
        return returned

    def is_idle(self):
        return (self.request_settled and not self.closed and not self.request_blocked
                and self.event_consumer is None and self.proc is not None and self.proc.poll() is None)

    def close(self):
        self.event_consumer=None
        return self.kernel.MatlabSession.close(self)

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
