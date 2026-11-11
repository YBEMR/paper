"""Deterministic boundary checks for the absolute method deadline transport.

Fault injection uses an artificial monotonic clock; no research input changes.
The optional real worker check is one binary equality, not a research solve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import matlab_bridge as bridge


class Clock:
    def __init__(self, value=0.0):
        self.value = float(value)

    def __call__(self):
        return self.value


MODEL = {'c': [1.0], 'Aeq': [[1.0]], 'beq': [1.0], 'lb': [0.0],
         'ub': [1.0], 'intcon': [0]}


def _session(folder, clock, deadline=10.0):
    session = bridge.MatlabSession.__new__(bridge.MatlabSession)
    session.workdir = folder
    folder.mkdir()
    session.clock = clock
    session.started = 0.0
    session.deadline = deadline
    session.budget = SimpleNamespace(deadline=deadline)
    session.counter = 0
    session.closed = False
    session.request_blocked = False
    session.proc = SimpleNamespace(poll=lambda: None)
    session.log = None
    return session


def run_checks(out, real_worker=False):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = []

    def check(name, condition, **evidence):
        checks.append({'name': name, 'passed': bool(condition), **evidence})

    with tempfile.TemporaryDirectory(dir=out) as temporary:
        temporary = Path(temporary)
        clock = Clock(10)
        target = temporary / 'expired_startup'
        with patch.object(bridge.subprocess, 'Popen') as spawn:
            try:
                bridge.MatlabSession(target, clock=clock,
                                     budget=SimpleNamespace(deadline=9.0))
                raised = False
            except TimeoutError:
                raised = True
        check('expired_method_cannot_start_worker_or_create_session',
              raised and not target.exists() and not spawn.called)

        clock = Clock()
        target = temporary / 'preparation_expired'
        original_json = bridge._json

        def consume_startup(path, value):
            original_json(path, value)
            if path.name == 'session.json':
                clock.value = 11

        with patch.object(bridge, '_json', consume_startup), \
                patch.object(bridge.subprocess, 'Popen') as spawn:
            try:
                bridge.MatlabSession(target, clock=clock,
                                     budget=SimpleNamespace(deadline=10.0))
                startup_error = None
            except TimeoutError as exc:
                startup_error = exc
        check('startup_preparation_charged_and_cleanup_separate',
              startup_error is not None and not spawn.called and
              startup_error.matlab_cleanup['cleanup_not_available_for_new_evidence'])

        clock = Clock()
        session = _session(temporary/'prepare', clock)
        original_prepare = bridge._prepare

        def slow_prepare(model):
            payload = original_prepare(model)
            clock.value = 11
            return payload

        with patch.object(bridge, '_prepare', slow_prepare):
            returned = session.solve(MODEL, remaining_s=60)
        check('conversion_cannot_replenish_absolute_deadline',
              not returned['accepted_for_evaluation'] and
              returned['phase'] == 'numerical_conversion' and
              not list(session.workdir.glob('*.request.json')))

        clock = Clock()
        session = _session(temporary/'serialize', clock)
        original_save = bridge.savemat

        def slow_save(*args, **kwargs):
            original_save(*args, **kwargs)
            clock.value = 11

        with patch.object(bridge, 'savemat', slow_save):
            returned = session.solve(MODEL, remaining_s=60)
        check('serialization_expiry_never_submits_model',
              returned.get('phase') == 'mat_serialization' and
              not list(session.workdir.glob('*.request.json')))

        clock = Clock()
        session = _session(temporary/'late_publish', clock)

        def late_publish(path, value):
            original_json(path, value)
            if path.name.endswith('.request.json'):
                clock.value = 11

        with patch.object(bridge, '_json', late_publish), \
                patch.object(session, 'close') as cleanup:
            returned = session.solve(MODEL, remaining_s=60)
        check('late_publication_cancelled_without_in_solve_cleanup',
              not returned['accepted_for_evaluation'] and session.request_blocked
              and not cleanup.called and bool(list(session.workdir.glob('*.cancel'))))
        try:
            session.solve(MODEL, remaining_s=60)
            blocked = False
        except RuntimeError:
            blocked = True
        check('timed_out_worker_cannot_receive_next_round', blocked)

        clock = Clock()
        session = _session(temporary/'archive', clock)

        def reply(*args, **kwargs):
            return {'status': 'SOLVED', 'x': 1.0, 'fval': 1.0}, {'attempts': 1}

        def late_archive(path, value):
            original_json(path, value)
            if path.name.endswith('.python.json'):
                clock.value = 11

        with patch.object(bridge, '_read_json_until', reply), \
                patch.object(bridge, '_json', late_archive):
            returned = session.solve(MODEL, remaining_s=60)
        archived = json.loads((session.workdir/'request_000001.python.json').read_text())
        check('receipt_archiving_expiry_cannot_return_candidate',
              returned['status'] == 'BUDGET_EXHAUSTED_BEFORE_RETURN' and
              returned['x'] == [] and not returned['accepted_for_evaluation'] and
              not archived['accepted_for_evaluation'])

        clock = Clock()
        session = _session(temporary/'repeat', clock)
        deadlines = []

        def record_reply(path, deadline, *args, **kwargs):
            deadlines.append(deadline)
            return reply()

        with patch.object(bridge, '_read_json_until', record_reply):
            first = session.solve(MODEL, remaining_s=60)
            clock.value = 9
            second = session.solve(MODEL, remaining_s=60)
            clock.value = 10
            third = session.solve(MODEL, remaining_s=60)
        check('repeated_solves_keep_one_original_deadline',
              deadlines == [10.0, 10.0] and first['accepted_for_evaluation'] and
              second['accepted_for_evaluation'] and not third['accepted_for_evaluation'],
              observed_deadlines=deadlines)

        clock = Clock()
        session = _session(temporary/'tighter', clock)
        deadlines = []
        with patch.object(bridge, '_read_json_until', record_reply):
            returned = session.solve(MODEL, budget=SimpleNamespace(deadline=5.0))
        check('explicit_solve_budget_can_only_shorten_session_deadline',
              deadlines == [5.0] and returned['accepted_for_evaluation'])

    if real_worker:
        started = time.monotonic()
        budget = SimpleNamespace(start=started, seconds=60.0, deadline=started+60.0)
        session = None
        try:
            session = bridge.MatlabSession(out/'real_matlab', budget=budget)
            returned = session.solve(MODEL, budget=budget)
            check('real_worker_absolute_budget_and_fixed_options',
                  returned['accepted_for_evaluation'] and returned['x'] == [1.0] and
                  returned['options']['IntegerPreprocess'] == 'none' and
                  returned['deadline_authority'] == 'Python absolute monotonic deadline' and
                  not returned['callback_candidates_independently_thermal_checked'],
                  method_wall_before_cleanup_s=time.monotonic()-started,
                  response=returned)
        finally:
            if session is not None:
                session.close()
        check('real_worker_cleanup_has_separate_receipt',
              session is not None and session.cleanup['cleanup_wall_seconds'] >= 0 and
              session.cleanup['cleanup_not_available_for_new_evidence'])

    result = {'passed': all(item['passed'] for item in checks), 'checks': checks,
              'real_worker_requested': real_worker, 'research_cases_run': 0,
              'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [Path(__file__), Path(bridge.__file__),
                                          bridge.HERE/'solve_model.m']}}
    (out/'checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n',
                                  encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--real-worker', action='store_true')
    args = parser.parse_args()
    result = run_checks(args.out, args.real_worker)
    print(json.dumps({'passed': result['passed'], 'count': len(result['checks'])}))
    raise SystemExit(0 if result['passed'] else 1)
