"""Bind the implemented executor to the prior proposal; no real launch."""
from copy import deepcopy
import argparse
from importlib import metadata
from pathlib import Path
import shutil
import sys

from .common import (HERE, ROOT, PREPARATION, PREPARATION_SHA, INPUT_SHA,
                     require, read, save, sha, validate_plan)


def freeze(out):
    require(not out.exists() and out.is_relative_to((HERE/'results').resolve()), 'NEW_FREEZE_OUTPUT')
    require(sha(PREPARATION/'plan.json') == PREPARATION_SHA
            and sha(PREPARATION/'common_input.json') == INPUT_SHA, 'PRIOR_FREEZE_DRIFT')
    plan = deepcopy(read(PREPARATION/'plan.json'))
    for rel, h in plan['source_sha256'].items():
        require(sha(ROOT/rel) == h, 'PRIOR_SOURCE_DRIFT:'+rel)
    out.mkdir(parents=True)
    shutil.copyfile(PREPARATION/'common_input.json', out/'common_input.json')
    sources = plan['source_sha256']
    snapshots = out/'executor_sources'; snapshots.mkdir()
    for p in sorted(HERE.glob('*.py')):
        sources[p.relative_to(ROOT).as_posix()] = sha(p)
        shutil.copyfile(p, snapshots/p.name)
    versions={}
    for name in ('psutil','numpy','scipy','mpmath'):
        try: versions[name]=metadata.version(name)
        except metadata.PackageNotFoundError: versions[name]=None
    plan.update(schema='ch3-one-shot-method-executor-v1',
        state='IMPLEMENTED_EXECUTOR_FROZEN_PENDING_SEPARATE_USER_APPROVAL',
        real_execution_entry_present=True, execution_authorized=False,
        preparation_plan_sha256=PREPARATION_SHA, memory_sampling_seconds=1,
        python_executable=str(Path(sys.executable).resolve()), python_version=sys.version,
        psutil_version=versions['psutil'],dependency_versions=versions,
        matlab_executable='F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe',
        runtime_isolation='new Python per method/post; whole owns a new MATLAB session; no reuse',
        real_approval_required=True,
        one_shot_claim='package claims/<plan_sha256>.json; never resume or erase',
        monitoring_scope='sampled observed PID/create-time tree plus original MATLAB cleanup receipt; not OS containment')
    validate_plan(plan)
    save(out/'plan.json', plan)
    save(out/'source_manifest.json', sources)
    save(out/'authorization_template.json', {'schema': 'ch3-one-shot-user-approval-v1',
        'authorized': False, 'approved_by': 'USER', 'approval_basis': None,
        'plan_sha256': sha(out/'plan.json'), 'common_input_sha256': INPUT_SHA,
        'scope': {'method_calls': 3, 'method_seconds': 900, 'post_calls': 3,
                  'post_seconds': 180, 'batch_wall_seconds': 1800}})
    return plan


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', required=True)
    freeze(Path(p.parse_args().output).resolve())
