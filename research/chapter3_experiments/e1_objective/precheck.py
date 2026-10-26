"""Reproducible E1 mock/static preparation. Never starts a research backend."""
import argparse
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
CORE=HERE.parent
REPO=HERE.parents[2]
if str(CORE) not in sys.path: sys.path.insert(0,str(CORE))
BASE='bb0f6e023389d10b94c969a024867510b13b23c1'
ORIGINALS=['inputs.py','config_v01.json','heft_method.py','schedules.py','start_domain.py',
           'control_policy.py','auto_heuristic_policy.py','thermal.py','timing.py',
           'h02_pair_preflight/__init__.py','h02_pair_preflight/common.py','h02_pair_preflight/receipts.py',
           'h02_pair_b0/__init__.py','h02_pair_b0/budget.py']


def digest(raw): return hashlib.sha256(raw).hexdigest()
def save(path,value):
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def main(destination):
    destination=Path(destination)
    if destination.exists(): raise FileExistsError('precheck evidence cannot overwrite: '+str(destination))
    destination.mkdir(parents=True)
    files=[CORE/p for p in ORIGINALS]+[CORE.parent/'v1_evaluator/interval.py']
    sources=[]
    for path in files:
        rel=path.relative_to(REPO).as_posix()
        original=subprocess.run(['git','cat-file','blob',BASE+':'+rel],cwd=REPO,check=True,capture_output=True).stdout
        current=path.read_bytes()
        if current!=original: raise ValueError('ORIGINAL_SOURCE_DRIFT:'+rel)
        sources.append(dict(path=rel,sha256=digest(current),bytes=len(current),base_unchanged=True))
    for path in sorted(HERE.glob('*.py')):
        raw=path.read_bytes()
        if b'\r\n' in raw: raise ValueError('NEW_SOURCE_CRLF:'+path.name)
        compile(raw,str(path),'exec')  # syntax only, no evaluation
        sources.append(dict(path=path.relative_to(REPO).as_posix(),sha256=digest(raw),bytes=len(raw),base_unchanged=False))
    save(destination/'source_manifest.json',dict(base_sha=BASE,sources=sources))
    from e1_objective.boundary import validate_pair, SLOTS, BUDGETS, real_backend_spec
    from h02_pair_preflight.common import sha
    import heft_method
    import thermal
    import inputs
    from control_policy import with_auto_low_idle
    # Profile guard catches direct aliases too, unlike patching only a module name.
    blocked=[]
    kernel=str(thermal.KERNEL_PATH.resolve()).lower()
    thermal_path=str(Path(thermal.__file__).resolve()).lower()
    original_builder=heft_method.build_heft_candidate.__code__
    def no_science(frame,event,arg):
        if event=='call' and (frame.f_code is original_builder or
            frame.f_code.co_filename.lower() in (kernel,thermal_path)):
            blocked.append(frame.f_code.co_name)
            raise AssertionError('SCIENCE_DISABLED_IN_PRECHECK:'+frame.f_code.co_name)
    old_profile=sys.getprofile()
    stream=io.StringIO()
    try:
        # Snapshot imports above are inert; no original scientific function may run below.
        sys.setprofile(no_science)
        with ExitStack() as stack:
            stack.enter_context(patch.object(subprocess,'Popen',side_effect=AssertionError('PROCESS_LAUNCH_FORBIDDEN')))
            suite=unittest.defaultTestLoader.loadTestsFromNames([
                'e1_objective.test_search','e1_objective.test_scoring','e1_objective.test_runner'])
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
            # Exact parameter expansion only: no candidate construction or thermal trace.
            config=with_auto_low_idle(inputs.load_config(CORE/'config_v01.json'))
            identities=[]
            for problem in ('base__R1','base__R3'):
                instance=inputs.build_instance(config,problem)
                left=dict(config=config,instance=instance,objective='FULL')
                right=dict(config=config,instance=instance,objective='OMIT_TEMP')
                checked=validate_pair(left,right)
                identities.append(dict(problem_id=problem,**checked))
                save(destination/(problem+'.json'),dict(config=config,instance=instance))
    finally: sys.setprofile(old_profile)
    (destination/'mock_tests.txt').write_bytes(stream.getvalue().encode())
    passed=result.wasSuccessful() and not blocked
    save(destination/'precheck_result.json',dict(passed=passed,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        science_guard_blocked_calls=blocked,input_pairs=identities,
        original_files_unchanged=len(files),python=sys.version,platform=platform.platform(),
        research_planning_calls=0,true_thermal_evaluations=0,MATLAB_starts=0,new_real_SAFE=0,
        mock_SAFE_is_not_research_evidence=True,expanded_research_inputs=2,
        source_manifest_sha256=digest((destination/'source_manifest.json').read_bytes())))
    save(destination/'four_slot_proposal.json',dict(batch_id='E1-OBJ-01',authorized=False,
        state='INTERFACE_MOCK_PRECHECK_ONLY',slots=[dict(ordinal=j+1,problem_id=s[0],objective=s[1],
            input_sha256=next(x['input_sha256'] for x in identities if x['problem_id']==s[0])) for j,s in enumerate(SLOTS)],
        budgets=BUDGETS,backend_spec=real_backend_spec(),
        missing_before_execution=['persistent once-use research ledger','real process supervisor and frozen worker envelope',
                                  'user formal batch authorization'],
        scientific_calls_consumed=0))
    print(json.dumps(dict(passed=passed,tests=result.testsRun,inputs=2,research_calls=0,new_real_SAFE=0)))
    if not passed: raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',required=True)
    main(parser.parse_args().out)
