"""K139 linked-subset correctness gate; no native/research/original-size model.

Use a fresh output directory. Failed records remain immutable. The baseline
is captured from K138 before implementation; only milp dispatch may change.
"""
import argparse
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from functools import wraps
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
BASELINE=REPO/'.runtime/k139_baseline.json'
MODULES=('test_linked_neighborhood','test_linked_method',
         'test_neighborhood_milp','test_fixed_unit_neighborhood','test_staged_method')
PROTOCOL='K139-linked-subset-dual-anchor-correctness-precheck-v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,
        allow_nan=False,default=str)+'\n',encoding='utf-8')
def sources():
    files=list(HERE.glob('*.py'))+[HERE/'config_v01.json',HERE/'solve_model.m',HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(files)}

def run(out):
    out=out.resolve();out.relative_to(REPO);out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();captured=io.StringIO();error=None;results={};details={}
    before={};base={};history={};environment={};inherited={}
    guards={name:0 for name in ('subprocess.Popen','MatlabSession.__init__',
                                'scipy.optimize.milp','scipy.optimize.linprog','original_scale_build_model')}
    models={'current_fixture_structural_models':0,'current_fixture_physical_models':0,
            'named_invalid_argument_rejection_checks':0}
    def forbidden(name):
        def reject(*args,**kwargs):
            guards[name]+=1
            raise AssertionError('Forbidden K139 precheck entry: '+name)
        return reject
    try:
        base=read(BASELINE);history=base['historical_artifact_sha256'];before=sources()
        inherited=base['baseline_source_sha256'];allowed=set(base['allowed_existing_source_changes'])
        assert len(inherited)==149 and allowed=={'research/chapter3_experiments/milp.py'}
        assert set(before)-set(inherited)==set(base['new_sources'])
        assert not set(inherited)-set(before)
        assert all(before[n]==h for n,h in inherited.items() if n not in allowed)
        assert all((REPO/n).is_file() and sha(REPO/n)==h for n,h in history.items())
        for name in before:
            target=out/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((REPO/name).read_bytes())
        (out/'parent_baseline.json').write_bytes(BASELINE.read_bytes())
        environment={'python':sys.version,'platform':platform.platform(),'machine':platform.machine()}
        import scipy.optimize
        import matlab_bridge
        import milp
        original_build=milp.build_model
        @wraps(original_build)
        def bounded_build(instance,*args,**kwargs):
            if not str(instance.get('id','')).startswith('fixture_'):
                # One inherited test intentionally renames a tiny fixture so
                # the production-only starts restriction must reject it.
                # Admit only that named, nonphysical, explicitly tiny input;
                # never admit base__R1 or a physical original-size model.
                domain=instance.get('start_domain',{})
                tiny_rejection=(instance.get('id')=='not_a_fixture_n1_interface'
                    and kwargs.get('include_physics') is False and kwargs.get('starts') is not None
                    and domain.get('kind')=='explicit_grid_subset'
                    and len(instance.get('scenarios',[]))==2
                    and sum(len(s.get('stage_instances',[])) for s in instance['scenarios'])<=6
                    and all(len(v)<=2 for by_stage in domain.get('by_scene_stage_ms',{}).values()
                            for v in by_stage.values()))
                if tiny_rejection:
                    models['named_invalid_argument_rejection_checks']+=1
                    return original_build(instance,*args,**kwargs)
                return forbidden('original_scale_build_model')(instance,*args,**kwargs)
            key='current_fixture_physical_models' if kwargs.get('include_physics',True) else 'current_fixture_structural_models'
            models[key]+=1
            return original_build(instance,*args,**kwargs)
        fixture_root=REPO/'.runtime/linked_precheck_fixtures';fixture_root.mkdir(parents=True,exist_ok=True)
        class Folder:
            def __init__(self,*args,**kwargs):
                requested=kwargs.get('dir',args[2] if len(args)>2 else None)
                parent=Path(requested).resolve() if requested is not None else fixture_root
                parent.relative_to(REPO);parent.mkdir(parents=True,exist_ok=True)
                path=parent/('case_'+uuid4().hex);path.mkdir();self.name=str(path)
            def __enter__(self):return self.name
            def __exit__(self,*args):return False
            def cleanup(self):pass
        save(out/'declaration.json',{'stage':'K139','protocol':PROTOCOL,
            'declared_at_utc':datetime.now(timezone.utc).isoformat(),
            'source_sha256':before,'source_count':len(before),'historical_artifact_sha256':history,
            'historical_artifact_count':len(history),'modules':MODULES,
            'scope':'single linked subset; mock/tiny correctness, not research optimization',
            'changed_existing_source':sorted(allowed),'new_sources':sorted(base['new_sources']),
            'reference_original_scope':'A.pre/A.main/A.post plus B.pre or C.pre; main/post closed at latest complete phase1 SAFE',
            'original_parameters_and_safety_changed':False,'native_calls':0,'research_calls':0,
            'original_scale_models':0,'quality_or_speed_claim':False})
        with ExitStack() as stack,redirect_stdout(captured),redirect_stderr(captured):
            stack.enter_context(patch.object(tempfile,'TemporaryDirectory',Folder))
            stack.enter_context(patch.object(subprocess,'Popen',side_effect=forbidden('subprocess.Popen')))
            stack.enter_context(patch.object(matlab_bridge.MatlabSession,'__init__',side_effect=forbidden('MatlabSession.__init__')))
            for name in ('milp','linprog'):
                stack.enter_context(patch.object(scipy.optimize,name,side_effect=forbidden('scipy.optimize.'+name)))
            stack.enter_context(patch.object(milp,'build_model',new=bounded_build))
            for name in MODULES:
                suite=unittest.defaultTestLoader.loadTestsFromName(name)
                result=unittest.TextTestRunner(stream=captured,verbosity=2).run(suite)
                results[name]={'passed':result.wasSuccessful(),'count':result.testsRun,
                    'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped)}
                module=sys.modules.get(name)
                details[name]=getattr(module,'RECORDS',{})
    except BaseException:
        error=traceback.format_exc();captured.write(error)
    after=sources()
    history_mismatch=[n for n,h in history.items() if not (REPO/n).is_file() or sha(REPO/n)!=h]
    snapshot_mismatch=[n for n,h in before.items() if not (out/'source_snapshot'/n).is_file() or sha(out/'source_snapshot'/n)!=h]
    (out/'unittest.txt').write_bytes(captured.getvalue().encode('utf-8'))
    save(out/'fixture_records.json',details);save(out/'environment.json',environment)
    report={'stage':'K139','protocol':PROTOCOL,
        'passed':bool(len(results)==len(MODULES) and all(v['passed'] and not v['skipped'] for v in results.values())
            and before==after and not history_mismatch and not snapshot_mismatch and not any(guards.values()) and error is None),
        'modules':results,'count':sum(v['count'] for v in results.values()),
        'source_sha256':after,'source_count':len(after),'source_unchanged':before==after,
        'source_snapshot_mismatches':snapshot_mismatch,
        'historical_artifact_count':len(history),'historical_artifacts_unchanged':not history_mismatch,
        'historical_mismatches':history_mismatch,
        'unchanged_inherited_source_count':sum(before.get(n)==h for n,h in inherited.items()
            if n not in set(base.get('allowed_existing_source_changes',[]))),
        'blocked_calls':guards,'observed_current_builds':models,
        'native_calls':0,'research_calls':0,'original_scale_models':0,
        'elapsed_s':time.monotonic()-started,'error':error,
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'environment':environment,'failed_runs_retained':True,
        'scope':'mock, structural Cartesian projection and tiny physical echo; no scheduling-quality or speed evidence'}
    save(out/'checks.json',report)
    print(json.dumps({k:report[k] for k in ('passed','count','elapsed_s','error')},ensure_ascii=False),flush=True)
    return report['passed']

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(0 if run(parser.parse_args().out) else 1)
