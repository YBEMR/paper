"""File identity and one-shot approval guards, independent of numerical code."""
import hashlib
import json
from pathlib import Path
from control import SECONDS, NATIVE_SECONDS, WATCHDOG


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Path outside declared root')
    return path


def verify_plan(plan_path, workspace, package):
    plan_path = Path(plan_path)
    if sha(plan_path) != read(plan_path.with_suffix('.identity.json'))['sha256']:
        raise ValueError('Frozen plan identity mismatch')
    plan = read(plan_path)
    required = dict(arm='ON', slots=1, maximum_native_calls=1, retries=0,
                    total_window_s=SECONDS, native_MaxTime_s=NATIVE_SECONDS, watchdog_s=WATCHDOG,
                    physical_evaluation_limit=2, formal_ABC_runs=0, model_builds=0,
                    execution_authorized=False)
    if any(plan.get(k) != v for k, v in required.items()):
        raise ValueError('Unsupported frozen scope')
    if plan['execution_directory'] != 'work/on_diagnostic_execution_20261112':
        raise ValueError('One-shot ledger location changed')
    for key, root in [('workspace_files', workspace), ('package_files', package)]:
        for name, expected in plan[key].items():
            if sha(inside(root, name)) != expected:
                raise ValueError('Frozen file drift: ' + name)
    return plan


def verify_approval(approval, plan_hash):
    if approval.get('approved') is not True:
        raise PermissionError('Separate user approval is required; this submission is not execution approval')
    required = dict(plan_sha256=plan_hash, arm='ON', maximum_native_calls=1,
                    total_window_s=SECONDS, native_MaxTime_s=NATIVE_SECONDS, retries=0)
    if any(approval.get(k) != v for k, v in required.items()):
        raise PermissionError('Approval does not match this exact frozen diagnostic')
    if not isinstance(approval.get('user_decision_reference'), str) or not approval['user_decision_reference'].strip():
        raise PermissionError('Missing reference to the actual user decision')


def claim_once(workspace, plan, claim):
    directory = inside(workspace, plan['execution_directory'])
    # Atomic directory creation: a failure, crash, or unused claim consumes this slot too.
    directory.mkdir(parents=True, exist_ok=False)
    save(directory / 'claim.json', claim)
    return directory
