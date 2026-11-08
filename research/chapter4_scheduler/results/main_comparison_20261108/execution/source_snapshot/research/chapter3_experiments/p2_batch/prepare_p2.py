"""K160 P2 preparation only: no executable budget, claims or batch launcher."""
import argparse
import ast
from copy import deepcopy
from pathlib import Path
import platform
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[1]
sys.path[:0] = [str(HERE), str(ROOT/'p0_batch'), str(ROOT)]
import p2_entry as p
from run_four_method_comparison import read, sha, canonical, now, save

PROTOCOL = 'K160-P2-initial78-originalH-preparation-only-v1'
BASE = ROOT/'results/p1_execution01/declaration.json'
OUT = ROOT/'results/p2_batch_preparation01'
COUNTERS = ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations')


def sources():
    inherited = read(BASE)['source_sha256']
    if len(inherited) != 211 or any(sha(REPO/n) != h for n, h in inherited.items()):
        raise ValueError('Original 211 scientific/execution sources changed')
    paths = sorted([*HERE.glob('*.py'), HERE/'protocol.md', HERE/'lineage.json'])
    return {**inherited, **{q.relative_to(REPO).as_posix(): sha(q) for q in paths}}


def lineage_issues():
    issues = []
    for item in read(HERE/'lineage.json'):
        origin = REPO/item['origin']
        text = origin.read_text(encoding='utf-8')
        if sha(origin) != item['sha256']:
            issues.append('ORIGIN_CHANGED:'+item['origin'])
        if item.get('function'):
            def function(source):
                lines = source.splitlines(keepends=True)
                node = next(n for n in ast.parse(source).body
                            if isinstance(n, ast.FunctionDef) and n.name == item['function'])
                return ''.join(lines[node.lineno-1:node.end_lineno]).rstrip()+'\n'
            text = function(text)
            target = function((HERE/item['target']).read_text(encoding='utf-8'))
        else:
            target = (HERE/item['target']).read_text(encoding='utf-8')
        for old, new in item['replacements']:
            if text.count(old) != 1:
                issues.append('AMBIGUOUS_REPLACEMENT:'+item['target'])
            text = text.replace(old, new)
        if text != target:
            issues.append('UNDECLARED_CHANGE:'+item['target'])
    return issues


def differences(a, b, prefix=''):
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return [v for key in a for v in differences(a[key], b[key], prefix+'/'+key)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [v for i, (x, y) in enumerate(zip(a, b)) for v in differences(x, y, prefix+'/'+str(i))]
    return [] if a == b else [{'path': prefix, 'P0': a, 'P2': b}]


def contrast(problem_id):
    """Pure input comparison; never reads a prior solution or temperature trace."""
    raw, config, instance = p.fresh_input(problem_id)
    oldraw, oldconfig, base = p.p0.fresh_input(problem_id.replace('initial_78__', 'base__'))
    expected = {'/id', '/condition_id', '/experiment_group', '/settings/initial_temperature_degC'}
    expected |= {f'/scenarios/{i}/entry/temperature_degC/{j}' for i in range(2) for j in range(4)}
    delta = differences(base, instance)
    if (raw != oldraw or config != oldconfig or {d['path'] for d in delta} != expected
            or len(delta) != 12 or instance['stage_modes'] != base['stage_modes']
            or instance['response_variant'] != 'H' or base['response_variant'] != 'H'
            or instance['ablation_input'] is not True or base['ablation_input'] is not True):
        raise ValueError('P2 must change only P0 initial temperature and catalog identity')
    return {'P0_problem_id': base['id'], 'P2_problem_id': problem_id,
            'differences': delta, 'stage_modes_identical': True,
            'config_identical': True, 'response_variant': 'H',
            'maximum_temperature_degC': '80', 'thermal_evaluation_performed': False}


def check_gate(path):
    g = read(path)
    if (g.get('protocol') != PROTOCOL or g.get('passed') is not True
            or g.get('source_sha256') != sources() or g.get('source_unchanged') is not True
            or g.get('prior_archives_unchanged') is not True
            or not g.get('tests_run') or g.get('error') is not None
            or any(g.get(k) != 0 for k in ('errors', 'failures', 'skipped', *COUNTERS))
            or not g.get('blocked_calls') or any(g['blocked_calls'].values())):
        raise ValueError('Successful source-matched zero-research P2 precheck required')
    return g


def empty_ledger():
    return {'protocol': PROTOCOL, 'state': 'NOT_AUTHORIZED', 'consumed': 0,
            'reserved_method_budget_s': 0, 'calls': []}


def prepare(out, checks):
    out = Path(out).resolve(); out.relative_to(REPO)
    check_gate(checks)
    if lineage_issues():
        raise ValueError('Dispatcher/result-contract lineage mismatch')
    frozen = sources()
    values = {pid: p.input_declaration(pid) for pid in p.PROBLEMS}
    contrasts = {pid: contrast(pid) for pid in p.PROBLEMS}
    out.mkdir(parents=True, exist_ok=False)
    for pid, (definition, triple) in values.items():
        folder = out/'inputs'/pid; folder.mkdir(parents=True)
        for name, value in zip(('raw', 'config', 'instance'), triple):
            save(folder/(name+'.json'), value)
    for name, digest in frozen.items():
        target = out/'source_snapshot'/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, target)
        if sha(target) != digest:
            raise ValueError('Snapshot race')
    shutil.copyfile(checks, out/'precheck.json')
    shutil.copyfile(HERE/'protocol.md', out/'protocol.md')
    save(out/'input_contrast.json', contrasts)
    d = {'protocol': PROTOCOL, 'state': 'PREPARED_NOT_AUTHORIZED',
         'authorised_to_execute': False, 'prepared_at_utc': now(),
         'source_sha256': frozen, 'inputs': {pid: v[0] for pid, v in values.items()},
         'proposed_slots': p.slots(), 'proposed_calls': 40, 'proposed_seconds_each': 300,
         'proposed_method_budget_s': 12000, 'proposed_calendar_reserve_s': 19200,
         'execution_budget_approved': False, 'real_batch_launcher': 'NOT_IMPLEMENTED',
         'precheck_sha256': sha(out/'precheck.json'), 'protocol_sha256': sha(out/'protocol.md'),
         'input_contrast_sha256': sha(out/'input_contrast.json'),
         'inherited_declaration_sha256': sha(BASE),
         'change_condition': 'P0_original_H_initial_temperature_50_to_78_only',
         'historical_initialization': False, **dict.fromkeys(COUNTERS, 0),
         'environment': {'python': sys.version, 'platform': platform.platform()}}
    save(out/'declaration.json', d)
    save(out/'ledger.json', empty_ledger())
    return admission(out)


def admission(out):
    out = Path(out).resolve(); out.relative_to(REPO)
    d = read(out/'declaration.json')
    expected = {'protocol': PROTOCOL, 'state': 'PREPARED_NOT_AUTHORIZED',
        'authorised_to_execute': False, 'proposed_slots': p.slots(), 'proposed_calls': 40,
        'proposed_seconds_each': 300, 'proposed_method_budget_s': 12000,
        'proposed_calendar_reserve_s': 19200, 'execution_budget_approved': False,
        'real_batch_launcher': 'NOT_IMPLEMENTED', 'source_sha256': sources(),
        'inherited_declaration_sha256': sha(BASE),
        'change_condition': 'P0_original_H_initial_temperature_50_to_78_only',
        'historical_initialization': False, **dict.fromkeys(COUNTERS, 0)}
    if any(d.get(k) != v for k, v in expected.items()) or set(d.get('inputs', {})) != set(p.PROBLEMS):
        raise ValueError('P2 preparation/source/protocol binding mismatch')
    check_gate(out/'precheck.json')
    for filename, key in (('precheck.json', 'precheck_sha256'),
            ('protocol.md', 'protocol_sha256'), ('input_contrast.json', 'input_contrast_sha256')):
        if sha(out/filename) != d.get(key):
            raise ValueError('Preparation evidence changed: '+filename)
    if sha(out/'protocol.md') != sha(HERE/'protocol.md'):
        raise ValueError('Protocol changed')
    for pid in p.PROBLEMS:
        definition, triple = p.input_declaration(pid)
        stored = [read(out/'inputs'/pid/(name+'.json')) for name in ('raw', 'config', 'instance')]
        if stored != list(triple) or d['inputs'][pid] != definition:
            raise ValueError('Fresh input mismatch: '+pid)
    if read(out/'input_contrast.json') != {pid: contrast(pid) for pid in p.PROBLEMS}:
        raise ValueError('P0 contrast mismatch')
    for name, digest in d['source_sha256'].items():
        if sha(out/'source_snapshot'/name) != digest:
            raise ValueError('Source snapshot changed')
    if read(out/'ledger.json') != empty_ledger() or (out/'claims').exists():
        raise ValueError('Preparation cannot consume or reserve research budget')
    return {'prepared': True, 'authorised_to_execute': False, 'proposed_calls': 40,
            'problem_inputs': 5, 'source_files': len(d['source_sha256']), **dict.fromkeys(COUNTERS, 0)}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('precheck', 'prepare', 'inspect', 'run'))
    cli.add_argument('--out', type=Path, default=OUT)
    cli.add_argument('--checks', type=Path)
    args = cli.parse_args(argv)
    if args.mode == 'run':
        cli.error('P2 execution has no budget authorization or frozen real launcher')
    if args.mode == 'precheck':
        import p2_precheck
        return 0 if p2_precheck.run(args.out) else 1
    if args.mode == 'prepare':
        if args.checks is None:
            cli.error('prepare requires --checks')
        print(prepare(args.out, args.checks))
    else:
        print(admission(args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
