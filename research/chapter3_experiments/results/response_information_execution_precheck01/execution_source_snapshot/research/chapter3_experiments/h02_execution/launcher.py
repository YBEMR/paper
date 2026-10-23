"""Fixed H02 one-use calendar supervisor. No automatic retry or repair."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[3]
CORE_REL = Path('research/chapter3_experiments')
OUT_REL = CORE_REL / 'results/response_information_execution01'
CLAIM_REL = CORE_REL / 'results/response_information_execution_claim01.json'
SUPERVISION_REL = CORE_REL / 'results/response_information_execution01_supervision'
POLICY_REL = CORE_REL / 'h02_pair_b0/policy.json'
GATE_REL = CORE_REL / 'h02_pair_b0/execution_gate.json'
CONTROLLER_REL = CORE_REL / 'h02_pair_b0/controller.py'
SELF_REL = CORE_REL / 'h02_execution/launcher.py'
PROTOCOL = 'H02-main-four-slot-execution-v1'
AUTHORIZATION_ID = 'H02_K177_R1R2_20261023_01'
SCIENTIFIC_POLICY_SHA = '916b07173b9ed7923f0cc37859828fa31e3cb60b51ad9fff67d05af1c6a2f18f'
BUDGETS = dict(plan_s=120, audit_s=60, maximum_plan_calls=4,
               maximum_audit_calls=4, plan_total_s=480, audit_total_s=240,
               scientific_total_s=720)
SLOTS = [dict(ordinal=1, problem_id='base__R1', view='H'),
         dict(ordinal=2, problem_id='base__R1', view='R'),
         dict(ordinal=3, problem_id='base__R2', view='R'),
         dict(ordinal=4, problem_id='base__R2', view='H')]


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'DUPLICATE_JSON_KEY')
            value[key] = item
        return value
    def reject(value):
        raise ValueError('NONFINITE_JSON:' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=unique, parse_constant=reject)


def save(path, value, *, exclusive=False):
    path = Path(path)
    if exclusive:
        with path.open('xb') as handle:
            handle.write(encoded(value))
            handle.flush()
            os.fsync(handle.fileno())
    else:
        temporary = path.with_name(path.name + '.tmp')
        with temporary.open('xb') as handle:
            handle.write(encoded(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)


def exact_path(value, expected, reason):
    require(isinstance(value, str) and Path(value).is_absolute(), reason)
    require(Path(value).resolve() == expected.resolve(), reason)


def validate(declaration_path, declaration_sha, *, repo=REPO):
    """Pure prelaunch checks; no imports of planner or thermal evaluator."""
    repo = Path(repo).resolve()
    require(isinstance(declaration_sha, str) and len(declaration_sha) == 64,
            'MISSING_DECLARATION_SHA')
    require(digest(declaration_path) == declaration_sha, 'DECLARATION_SHA_DRIFT')
    value = load(declaration_path)
    require(value.get('protocol') == PROTOCOL, 'PROTOCOL_DRIFT')
    require(value.get('calendar_limit_s') == 1200, 'CALENDAR_LIMIT_DRIFT')
    require(value.get('budgets') == BUDGETS, 'SCIENTIFIC_BUDGET_DRIFT')
    require(value.get('slots') == SLOTS, 'SLOT_ORDER_OR_IDENTITY_DRIFT')
    exact_path(value.get('output_directory'), repo / OUT_REL, 'OUTPUT_DIRECTORY_DRIFT')
    exact_path(value.get('global_claim'), repo / CLAIM_REL, 'GLOBAL_CLAIM_DRIFT')
    exact_path(value.get('policy_path'), repo / POLICY_REL, 'POLICY_PATH_DRIFT')
    exact_path(value.get('gate_path'), repo / GATE_REL, 'GATE_PATH_DRIFT')
    require(value.get('scientific_policy_sha256') == SCIENTIFIC_POLICY_SHA,
            'SCIENTIFIC_POLICY_IDENTITY_DRIFT')
    expected = value.get('expected_sha')
    require(isinstance(expected, dict) and expected, 'MISSING_SOURCE_MANIFEST')
    required = {p.as_posix() for p in (POLICY_REL, GATE_REL, CONTROLLER_REL, SELF_REL)}
    require(required.issubset(expected), 'SOURCE_MANIFEST_INCOMPLETE')
    for relative, wanted in expected.items():
        require(isinstance(relative, str) and not Path(relative).is_absolute(),
                'NONRELATIVE_SOURCE_PATH')
        target = (repo / relative).resolve()
        require(target.is_relative_to(repo), 'SOURCE_PATH_ESCAPE')
        require(isinstance(wanted, str) and len(wanted) == 64
                and target.is_file() and digest(target) == wanted,
                'SOURCE_SHA_DRIFT:' + relative)
    policy = load(repo / POLICY_REL)
    gate = load(repo / GATE_REL)
    scientific = {k: v for k, v in policy.items() if k != 'execution_enabled'}
    require(hashlib.sha256(encoded(scientific)).hexdigest() == SCIENTIFIC_POLICY_SHA,
            'H02_SCIENTIFIC_POLICY_DRIFT')
    require(policy.get('execution_enabled') is True
            and gate.get('research_authorized') is True
            and gate.get('four_slot_authorized') is True,
            'B0_RESEARCH_EXECUTION_NOT_AUTHORIZED')
    require(gate.get('authorization_id') == AUTHORIZATION_ID, 'GATE_AUTHORIZATION_DRIFT')
    require(isinstance(gate.get('approval_reference'), str)
            and gate['approval_reference'].strip(), 'MISSING_HUMAN_AUTHORIZATION_REFERENCE')
    exact_path(gate.get('allowed_run_directory'), repo / OUT_REL,
               'GATE_RUN_DIRECTORY_DRIFT')
    require(isinstance(gate.get('authority_store'), str)
            and Path(gate['authority_store']).is_absolute(), 'INVALID_AUTHORITY_STORE')
    for key, expected_value in dict(plan_limit_s=120, audit_limit_s=60,
                                    maximum_plan_calls=4, maximum_audit_calls=4,
                                    maximum_plan_budget_s=480, maximum_audit_budget_s=240,
                                    research_budget_s=720, slots=SLOTS).items():
        require(policy.get(key) == expected_value, 'POLICY_BUDGET_OR_SLOT_DRIFT:' + key)
    # Existing gate claims independently prohibit another path through B0.
    require(not (Path(gate['authority_store']) / (AUTHORIZATION_ID + '.claim.json')).exists(),
            'B0_AUTHORIZATION_ALREADY_CONSUMED')
    require(not (repo / OUT_REL).exists(), 'OUTPUT_ALREADY_EXISTS')
    require(not (repo / CLAIM_REL).exists(), 'GLOBAL_CLAIM_ALREADY_CONSUMED')
    require(not (repo / SUPERVISION_REL).exists(), 'SUPERVISION_ALREADY_EXISTS')
    return value


def kill_owned_tree(process):
    """Terminate only the current owned Popen tree, never process-name matches."""
    if os.name == 'nt':
        result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=False,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        # A concurrent natural exit may make taskkill return nonzero.
        require(result.returncode == 0 or process.poll() is not None,
                'OWNED_TREE_TERMINATION_FAILED')
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


@dataclass
class Services:
    clock: object = time.monotonic
    sleep: object = time.sleep
    popen: object = subprocess.Popen
    terminate_tree: object = kill_owned_tree


def ledger_snapshot(output):
    records = []
    ledger = Path(output) / 'ledger'
    for path in sorted(ledger.glob('*.claim.json')) if ledger.exists() else []:
        value = load(path)
        name = value.get('name', '')
        kind = 'plan' if name.startswith('slot_') else 'audit' if name.startswith('audit_') else None
        require(kind is not None, 'UNKNOWN_CONTROLLER_CLAIM')
        ordinal = int(name.split('_')[1])
        require(1 <= ordinal <= 4, 'CONTROLLER_CLAIM_SLOT_RANGE')
        require(name == ('slot_' if kind == 'plan' else 'audit_') + str(ordinal),
                'CONTROLLER_CLAIM_NAME_DRIFT')
        require(value.get('budget_s') == (120 if kind == 'plan' else 60),
                'CONTROLLER_CLAIM_BUDGET_DRIFT')
        if kind == 'plan':
            require(value.get('slot') == SLOTS[ordinal - 1], 'CONTROLLER_CLAIM_SLOT_IDENTITY')
        records.append(dict(file=path.name, kind=kind, ordinal=ordinal,
                            budget_s=value['budget_s'], sha256=digest(path)))
    plans = [r for r in records if r['kind'] == 'plan']
    audits = [r for r in records if r['kind'] == 'audit']
    require(len(plans) <= 4 and len(audits) <= 4, 'CONTROLLER_CALL_LIMIT_EXCEEDED')
    total = sum(r['budget_s'] for r in records)
    require(total <= 720, 'CONTROLLER_SCIENTIFIC_BUDGET_EXCEEDED')
    return dict(records=records, plan_calls_consumed=len(plans),
                audit_calls_consumed=len(audits), reserved_scientific_budget_s=total,
                declared_scientific_cap_s=720)


def run(declaration_path, declaration_sha, *, services=None, repo=REPO):
    """Root clock precedes source validation; claims precede process creation.

    Injectable services/repo are for isolated pure fixtures, absent from the CLI.
    """
    services = services or Services()
    repo = Path(repo).resolve()
    started = services.clock()
    declaration = validate(declaration_path, declaration_sha, repo=repo)
    output, claim, supervision = repo / OUT_REL, repo / CLAIM_REL, repo / SUPERVISION_REL
    require(services.clock() - started < 1200, 'CALENDAR_EXPIRED_BEFORE_CLAIM')
    claim.parent.mkdir(parents=True, exist_ok=True)
    save(claim, dict(protocol=PROTOCOL, declaration_sha256=declaration_sha,
                     authorization_id=AUTHORIZATION_ID, output_directory=str(output),
                     consumed_before_launch=True, automatic_retry=False,
                     utc=datetime.now(timezone.utc).isoformat()), exclusive=True)
    supervision.mkdir()
    save(supervision / 'declaration.json', declaration, exclusive=True)
    command = [sys.executable, '-B', '-m', 'h02_pair_b0.controller', '--execute', str(output)]
    process = None
    terminal = dict(protocol=PROTOCOL, declaration_sha256=declaration_sha,
                    authorization_id=AUTHORIZATION_ID, command=command,
                    calendar_limit_s=1200, scientific_budget_s=720,
                    automatic_retry=False, scientific_results_created_by_supervisor=False,
                    status='CONSUMED_NOT_LAUNCHED', killed_owned_tree=False)
    try:
        require(services.clock() - started < 1200, 'CALENDAR_EXPIRED_BEFORE_LAUNCH')
        with (supervision / 'stdout.log').open('wb') as stdout, (supervision / 'stderr.log').open('wb') as stderr:
            options = dict(cwd=repo / CORE_REL, stdin=subprocess.DEVNULL,
                           stdout=stdout, stderr=stderr, shell=False)
            if os.name == 'nt':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            else:
                options['start_new_session'] = True
            process = services.popen(command, **options)
            terminal.update(status='RUNNING', owned_pid=process.pid)
            save(supervision / 'launch.json', dict(terminal), exclusive=True)
            while process.poll() is None:
                elapsed = services.clock() - started
                if elapsed >= 1200:
                    services.terminate_tree(process)
                    terminal.update(status='CALENDAR_DEADLINE', killed_owned_tree=True)
                    break
                services.sleep(min(0.1, 1200 - elapsed))
            terminal['returncode'] = process.returncode
            if terminal['status'] == 'RUNNING':
                terminal['status'] = 'CONTROLLER_RETURNED' if process.returncode == 0 else 'CONTROLLER_NONZERO_EXIT'
        terminal['controller_ledger'] = ledger_snapshot(output)
        if terminal['status'] == 'CONTROLLER_RETURNED':
            require((output / 'terminal.json').is_file(), 'CONTROLLER_FINAL_RECEIPT_MISSING')
            controller_terminal = load(output / 'terminal.json')
            require(type(controller_terminal.get('stopped')) is bool, 'CONTROLLER_STOP_STATE_MISSING')
            completed_slots = controller_terminal.get('slots')
            require(isinstance(completed_slots, list) and len(completed_slots) <= 4,
                    'CONTROLLER_FINAL_SLOT_LIST')
            require(all(row.get('slot') == SLOTS[i] for i, row in enumerate(completed_slots)),
                    'CONTROLLER_FINAL_SLOT_IDENTITY')
            require(controller_terminal['stopped'] or len(completed_slots) == 4,
                    'CONTROLLER_UNSTOPPED_INCOMPLETE_BATCH')
            terminal['controller_terminal_sha256'] = digest(output / 'terminal.json')
            terminal['status'] = 'CONTROLLER_STOPPED' if controller_terminal.get('stopped') is True else 'COMPLETED'
    except BaseException as error:
        terminal.update(status='SUPERVISOR_TECHNICAL_FAILURE', error=type(error).__name__ + ':' + str(error))
        if process is not None and process.poll() is None:
            try:
                services.terminate_tree(process)
                terminal['killed_owned_tree'] = True
            except Exception as stop_error:
                terminal['termination_error'] = type(stop_error).__name__ + ':' + str(stop_error)
        try:
            terminal['controller_ledger'] = ledger_snapshot(output)
        except Exception as ledger_error:
            terminal['ledger_error'] = type(ledger_error).__name__ + ':' + str(ledger_error)
    terminal['calendar_elapsed_s'] = services.clock() - started
    save(supervision / 'terminal.json', terminal, exclusive=True)
    return terminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declaration', type=Path, required=True)
    parser.add_argument('--declaration-sha', required=True)
    args = parser.parse_args()
    try:
        terminal = run(args.declaration, args.declaration_sha)
    except Exception as error:
        print(type(error).__name__ + ':' + str(error), file=sys.stderr)
        return 3
    print(json.dumps(terminal, ensure_ascii=False))
    return 0 if terminal['status'] == 'COMPLETED' else 3


if __name__ == '__main__':
    raise SystemExit(main())
