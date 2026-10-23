"""K181 four-arm, eight-slot preparation and once-only execution contract.

Preparation never authorizes science. A later, explicit human budget decision
must be saved separately, binding this immutable declaration and passing gates.
This is a local single-writer protocol, not a cryptographic permission system.
"""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCIENCE = REPO / 'research/chapter3_experiments'
PACKAGE = HERE.parent
PROTOCOL = 'K181-four-arm-development-v1'
PROPOSAL = SCIENCE / 'results/linked_ablation_preparation01/preparation02/proposal.json'
ORDER = [('base__R1', a) for a in ('C', 'HEFT', 'SINGLE', 'PAIR')] + [
    ('base__R3', a) for a in ('PAIR', 'SINGLE', 'HEFT', 'C')]
BUDGETS = dict(method_s=300, method_total_s=2400, post_s=60,
               post_total_s=480, calendar_s=4800, method_return_s=420, slot_s=480)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def _output(path):
    path = Path(path).resolve()
    if not path.is_relative_to(PACKAGE / 'results') or path == PACKAGE / 'results':
        raise ValueError('Only a new chapter4 results directory is permitted')
    return path


def environment():
    tree = ast.parse((SCIENCE / 'matlab_bridge.py').read_text('utf-8-sig'))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'DEFAULT_MATLAB' for t in n.targets))
    matlab = Path(ast.literal_eval(node.value.args[0])).resolve()
    return dict(python_executable=str(Path(sys.executable).resolve()),
        python_version=sys.version, platform=platform.platform(),
        packages={n: importlib.metadata.version(n) for n in ('numpy', 'scipy')},
        matlab_executable=str(matlab), matlab_executable_sha256=sha(matlab),
        license_check='Only inside a billed original C session; no preparation probe')


def make_declaration(output=None):
    """Read metadata and code bytes only; do not expand a workload or call science."""
    old = read(PROPOSAL)
    cases = []
    for case in old['cases']:
        common = deepcopy(case['common'])
        common.pop('historical_seed_reference', None)
        recipes = {'C': dict(kwargs=deepcopy(case['recipes']['C']['kwargs']))}
        recipes.update({a: dict(method='heft', seed=None, allow_auto_low=True,
            refinement=None if a == 'HEFT' else a.lower()) for a in ('HEFT', 'SINGLE', 'PAIR')})
        cases.append(dict(common=common, recipes=recipes))
    sources = set(old['source_sha256'])
    sources.update(p.relative_to(REPO).as_posix() for p in PACKAGE.glob('*.py'))
    sources.update(p.relative_to(REPO).as_posix() for p in HERE.glob('*.py'))
    sources.update(p.relative_to(REPO).as_posix() for p in (PACKAGE / 'tests').glob('*.py'))
    sources.update('research/chapter3_experiments/linked_ablation_execution/' + n
        for n in ('audit.py', 'registry.py', 'supervise.py'))
    sources.update('research/chapter3_experiments/h02_pair_preflight/' + n
        for n in ('receipts.py', 'common.py'))
    declaration = dict(protocol=PROTOCOL, authorized=False, execution_enabled=False,
        baseline_commit='8501ecd718d51575206237eba950ad42a4fa8e36',
        frozen_at_utc=now(), budgets=BUDGETS.copy(), cases=cases,
        slots=[dict(slot_id=f'{case}__{arm}', case_id=case, arm=arm,
            ordinal=i + 1, method_seconds=300, post_seconds_max=60)
            for i, (case, arm) in enumerate(ORDER)],
        output_directory=None if output is None else _output(output).relative_to(REPO).as_posix(),
        solver_options=deepcopy(old['solver_options']),
        source_sha256={n: sha(REPO / n) for n in sorted(sources)},
        frozen_dependency_sha256={PROPOSAL.relative_to(REPO).as_posix(): sha(PROPOSAL)},
        protected_archive_sha256=deepcopy(old['archive_readonly_sha256']),
        environment=environment(), no_retry=True, research_calls_consumed=0,
        reserved_method_seconds=0, reserved_post_seconds=0,
        initialization='Independent fresh same-call initialization; never import another arm candidate/cache',
        attribution='Compare best initialization SAFE candidate/energy/completion, not receipt timestamps/tokens',
        stops='Any technical/numeric fault, failed post, identity/source drift or cleanup uncertainty stops batch; normal no-SAFE may continue',
        prohibitions=['No physical/input/safety change', 'No historical initialization',
            'No K168 or deadline remainder', 'No rerun/refund/budget extension'])
    validate(declaration)
    return declaration


def validate(d, *, require_active=False):
    if d.get('protocol') != PROTOCOL or d.get('budgets') != BUDGETS:
        raise ValueError('Protocol or eight-call budget drift')
    if d.get('authorized') is not False or d.get('execution_enabled') is not False:
        raise ValueError('Immutable preparation must remain disabled; approval is separate')
    expected = [dict(slot_id=f'{c}__{a}', case_id=c, arm=a, ordinal=i+1,
        method_seconds=300, post_seconds_max=60) for i, (c, a) in enumerate(ORDER)]
    if d.get('slots') != expected or d.get('no_retry') is not True:
        raise ValueError('Slot identity/order or no-retry drift')
    old = read(PROPOSAL)
    if d.get('solver_options') != old['solver_options']:
        raise ValueError('Original solver configuration drift')
    for current, prior in zip(d.get('cases', []), old['cases']):
        common = deepcopy(prior['common']); common.pop('historical_seed_reference', None)
        recipes = {'C': dict(kwargs=deepcopy(prior['recipes']['C']['kwargs']))}
        recipes.update({a: dict(method='heft', seed=None, allow_auto_low=True,
            refinement=None if a == 'HEFT' else a.lower()) for a in ('HEFT', 'SINGLE', 'PAIR')})
        if current != dict(common=common, recipes=recipes):
            raise ValueError('Input or fixed backend recipe drift')
    if len(d.get('cases', [])) != 2:
        raise ValueError('Exactly R1 and R3 are allowed')
    if d.get('output_directory') is not None:
        _output(REPO / d['output_directory'])
    if require_active:
        raise ValueError('Use load_active to verify the separate human authorization')
    return True


def verify_files(d):
    for field in ('source_sha256', 'frozen_dependency_sha256', 'protected_archive_sha256'):
        mapping = d.get(field)
        if not isinstance(mapping, dict) or not mapping:
            return False
        for name, digest in mapping.items():
            p = (REPO / name).resolve()
            if not p.is_relative_to(REPO) or not p.is_file() or sha(p) != digest:
                return False
    return True


def freeze(output):
    output = _output(output)
    if output.exists():
        raise FileExistsError('Preparation output exists; never replace prior evidence')
    d = make_declaration(output)
    if not verify_files(d):
        raise ValueError('Protected evidence/source mismatch before freeze')
    output.mkdir(parents=True)
    write_new(output / 'declaration.json', d)
    write_new(output / 'declaration_binding.json', dict(protocol=PROTOCOL,
        declaration_sha256=sha(output / 'declaration.json'), authorized=False,
        research_calls_consumed=0, reserved_method_seconds=0, reserved_post_seconds=0))
    for name, digest in d['source_sha256'].items():
        p = output / 'source_snapshot' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, p)
        if sha(p) != digest:
            raise ValueError('Source snapshot mismatch')
    return d


def _context(path):
    path = Path(path).resolve()
    d = read(path); validate(d)
    out = _output(REPO / d['output_directory'])
    if path != out / 'declaration.json':
        raise ValueError('Declaration/output path mismatch')
    if read(out / 'declaration_binding.json')['declaration_sha256'] != sha(path):
        raise ValueError('Declaration binding mismatch')
    auth = read(out / 'authorization.json')
    if (auth.get('origin') != 'direct human budget confirmation'
            or not isinstance(auth.get('confirmation'), str) or not auth['confirmation'].strip()
            or auth.get('declaration_sha256') != sha(path) or auth.get('budgets') != BUDGETS
            or auth.get('authorized') is not True or auth.get('execution_enabled') is not True):
        raise ValueError('No matching human authorization')
    gates = auth.get('precheck_sha256', {})
    if not gates or any(not (REPO / n).is_file() or sha(REPO / n) != h
            or read(REPO / n).get('passed') is not True for n, h in gates.items()):
        raise ValueError('Missing, failed or changed pure precheck gate')
    if not any(read(REPO / n).get('protocol') == 'K181-guarded-execution-precheck-v1'
            and read(REPO / n).get('source_sha256') == d['source_sha256']
            and read(REPO / n).get('new_research_calls') == 0 for n in gates):
        raise ValueError('No current-source, zero-research execution-chain gate')
    if not verify_files(d):
        raise ValueError('Source, input metadata or protected archive drift')
    if (out / 'batch_terminal.json').exists():
        raise ValueError('This once-only batch is terminal')
    return d, out


def _batch(path, out):
    batch = read(out / 'batch.claim.json')
    if batch.get('declaration_sha256') != sha(path):
        raise ValueError('Batch claim does not bind this declaration')
    started = datetime.fromisoformat(batch['started_utc'])
    deadline = datetime.fromisoformat(batch['deadline_utc'])
    if (started.utcoffset() is None or deadline.utcoffset() is None
            or (deadline - started).total_seconds() != 4800
            or datetime.now(timezone.utc) >= deadline):
        raise ValueError('Invalid or expired batch calendar; no new consumption')
    return batch


def load_active(path, slot_id):
    d, out = _context(path)
    batch = _batch(path, out)
    if batch.get('not_scientific') is not False:
        raise ValueError('Simulated batch cannot activate a real worker')
    slot = next((s for s in d['slots'] if s['slot_id'] == slot_id), None)
    if slot is None:
        raise ValueError('Unknown slot')
    folder = out / 'calls' / slot_id
    claim = read(folder / 'slot.claim.json')
    if (claim.get('declaration_sha256') != sha(path) or claim.get('slot') != slot
            or (folder / 'terminal.json').exists()):
        raise ValueError('Missing or terminal once-only slot claim')
    case = next(c for c in d['cases'] if c['common']['case_id'] == slot['case_id'])
    return d, slot, case


def claim_slot(path, slot_id):
    d, out = _context(path)
    _batch(path, out)
    for slot in d['slots']:
        folder = out / 'calls' / slot['slot_id']
        if slot['slot_id'] == slot_id:
            if folder.exists():
                raise FileExistsError('Slot already reserved; no retry/refund')
            folder.mkdir(parents=True)
            write_new(folder / 'slot.claim.json', dict(slot=slot,
                declaration_sha256=sha(path), reserved_method_s=300,
                reserved_at_utc=now(), no_retry=True))
            return folder
        terminal = read(folder / 'terminal.json')
        if terminal.get('continue_allowed') is not True:
            raise ValueError('Earlier slot incomplete or stopped; no advancement')
    raise ValueError('Unknown slot')
