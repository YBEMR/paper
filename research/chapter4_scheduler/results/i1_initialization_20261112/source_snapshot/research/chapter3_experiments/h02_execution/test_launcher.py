"""Pure calendar/authority fixtures: never launch a process or evaluator."""
import argparse
import copy
import json
from pathlib import Path
import tempfile

try:
    from . import launcher as m
except ImportError:
    import launcher as m


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now
    def sleep(self, duration):
        self.now += duration


class Process:
    pid = 314159
    def __init__(self, clock, end, code=0):
        self.clock, self.end, self.code = clock, end, code
        self.returncode = None
        self.killed = False
    def poll(self):
        if self.killed or self.clock.now >= self.end:
            self.returncode = -9 if self.killed else self.code
        return self.returncode
    def wait(self, timeout=None):
        return self.poll()


def fixture(root):
    root = Path(root)
    for relative in (m.POLICY_REL, m.GATE_REL, m.CONTROLLER_REL, m.SELF_REL):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((m.REPO / relative).read_bytes())
    policy = m.load(root / m.POLICY_REL)
    policy['execution_enabled'] = True
    m.save(root / m.POLICY_REL, policy)
    gate = m.load(root / m.GATE_REL)
    gate.update(research_authorized=True, four_slot_authorized=True,
                approval_reference='PURE-FIXTURE-NEVER-REAL', authorization_id=m.AUTHORIZATION_ID,
                allowed_run_directory=str((root / m.OUT_REL).resolve()),
                authority_store=str((root / 'pure_authority').resolve()))
    m.save(root / m.GATE_REL, gate)
    value = dict(protocol=m.PROTOCOL, calendar_limit_s=1200, budgets=copy.deepcopy(m.BUDGETS),
                 slots=copy.deepcopy(m.SLOTS), output_directory=str((root / m.OUT_REL).resolve()),
                 global_claim=str((root / m.CLAIM_REL).resolve()),
                 policy_path=str((root / m.POLICY_REL).resolve()),
                 gate_path=str((root / m.GATE_REL).resolve()),
                 scientific_policy_sha256=m.SCIENTIFIC_POLICY_SHA,
                 expected_sha={p.as_posix(): m.digest(root / p) for p in
                               (m.POLICY_REL, m.GATE_REL, m.CONTROLLER_REL, m.SELF_REL)})
    declaration = root / 'declaration.json'
    m.save(declaration, value)
    return declaration, m.digest(declaration), value


def expected_error(action, text):
    try:
        action()
    except (ValueError, FileExistsError) as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError('expected rejection: ' + text)


def services(root, *, code=0, end=0.3, stopped=False, missing=False, incomplete=False):
    clock = Clock()
    calls, kills = [], []
    def popen(command, **kwargs):
        calls.append((command, kwargs))
        assert command[:5] == [m.sys.executable, '-B', '-m', 'h02_pair_b0.controller', '--execute']
        assert Path(command[5]) == (root / m.OUT_REL).resolve()
        assert Path(kwargs['cwd']) == root / m.CORE_REL
        assert kwargs['shell'] is False
        output = root / m.OUT_REL
        output.mkdir(parents=True)
        ledger = output / 'ledger'
        ledger.mkdir()
        m.save(ledger / 'slot_1.claim.json', dict(name='slot_1', slot=m.SLOTS[0], budget_s=120))
        m.save(ledger / 'audit_1.claim.json', dict(name='audit_1', budget_s=60))
        if not missing:
            rows = m.SLOTS[:1] if stopped or incomplete else m.SLOTS
            m.save(output / 'terminal.json', dict(stopped=stopped, slots=[dict(slot=s) for s in rows]))
        return Process(clock, end, code)
    def terminate(process):
        kills.append(process.pid)
        process.killed = True
        process.wait()
    return m.Services(clock=clock, sleep=clock.sleep, popen=popen, terminate_tree=terminate), calls, kills


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    require_out = args.out.resolve()
    require_out.mkdir(parents=True, exist_ok=False)
    checks = []
    def check(name, fn):
        with tempfile.TemporaryDirectory(prefix='f_', dir=require_out) as folder:
            root = Path(folder).resolve()
            declaration, identity, value = fixture(root)
            fn(root, declaration, identity, value)
        checks.append(dict(name=name, passed=True))

    def validate_clean(r, d, h, v):
        assert m.validate(d, h, repo=r) == v
        assert not (r / m.CLAIM_REL).exists()
    check('fixed_scope_static_validation_no_claim', validate_clean)

    def success(r, d, h, v):
        s, calls, kills = services(r)
        result = m.run(d, h, services=s, repo=r)
        assert result['status'] == 'COMPLETED' and len(calls) == 1 and not kills
        assert result['controller_ledger']['reserved_scientific_budget_s'] == 180
        assert result['scientific_results_created_by_supervisor'] is False
        assert (r / m.SUPERVISION_REL / 'terminal.json').is_file()
        expected_error(lambda: m.run(d, h, services=s, repo=r), 'OUTPUT_ALREADY_EXISTS')
        assert len(calls) == 1
    check('success_once_only_no_real_process', success)

    def global_once(r, d, h, v):
        (r / m.CLAIM_REL).parent.mkdir(parents=True, exist_ok=True)
        m.save(r / m.CLAIM_REL, {'old': True})
        expected_error(lambda: m.validate(d, h, repo=r), 'GLOBAL_CLAIM_ALREADY_CONSUMED')
    check('global_claim_cannot_be_reused', global_once)

    def drift(r, d, h, v):
        (r / m.CONTROLLER_REL).write_text('# drift\n', encoding='utf-8')
        expected_error(lambda: m.validate(d, h, repo=r), 'SOURCE_SHA_DRIFT')
        assert not (r / m.CLAIM_REL).exists()
    check('source_drift_refused_before_consumption', drift)

    check('declaration_sha_drift', lambda r,d,h,v: expected_error(lambda: m.validate(d, '0'*64, repo=r), 'DECLARATION_SHA_DRIFT'))

    def budget_change(r, d, h, v):
        for key, amount in [('plan_total_s', 481), ('scientific_total_s', 721), ('maximum_plan_calls', 5)]:
            changed = copy.deepcopy(v)
            changed['budgets'][key] = amount
            m.save(d, changed)
            expected_error(lambda: m.validate(d, m.digest(d), repo=r), 'SCIENTIFIC_BUDGET_DRIFT')
    check('cannot_expand_720_seconds_or_four_calls', budget_change)

    def order(r, d, h, v):
        v['slots'][2], v['slots'][3] = v['slots'][3], v['slots'][2]
        m.save(d, v)
        expected_error(lambda: m.validate(d, m.digest(d), repo=r), 'SLOT_ORDER_OR_IDENTITY_DRIFT')
    check('H_R_R_H_order_fixed', order)

    def gate_drift(r, d, h, v):
        gate = m.load(r / m.GATE_REL)
        gate['authorization_id'] = 'OTHER'
        m.save(r / m.GATE_REL, gate)
        v['expected_sha'][m.GATE_REL.as_posix()] = m.digest(r / m.GATE_REL)
        m.save(d, v)
        expected_error(lambda: m.validate(d, m.digest(d), repo=r), 'GATE_AUTHORIZATION_DRIFT')
    check('same_B0_authorization_identity_required', gate_drift)

    def expired_before_claim(r, d, h, v):
        calls = []
        times = iter([0, 1200])
        s = m.Services(clock=lambda: next(times), popen=lambda *a,**k: calls.append(a))
        expected_error(lambda: m.run(d, h, services=s, repo=r), 'CALENDAR_EXPIRED_BEFORE_CLAIM')
        assert not calls and not (r / m.CLAIM_REL).exists()
    check('calendar_expiry_before_claim_no_launch', expired_before_claim)

    def expired_after_claim(r, d, h, v):
        calls = []
        times = iter([0, 0, 1200, 1200])
        s = m.Services(clock=lambda: next(times), popen=lambda *a,**k: calls.append(a))
        result = m.run(d, h, services=s, repo=r)
        assert result['status'] == 'SUPERVISOR_TECHNICAL_FAILURE'
        assert 'CALENDAR_EXPIRED_BEFORE_LAUNCH' in result['error']
        assert not calls and (r / m.CLAIM_REL).exists()
    check('calendar_expiry_after_claim_stays_consumed', expired_after_claim)

    def nonzero(r, d, h, v):
        s, calls, kills = services(r, code=7)
        result = m.run(d, h, services=s, repo=r)
        assert result['status'] == 'CONTROLLER_NONZERO_EXIT' and result['returncode'] == 7
        assert len(calls) == 1 and not kills
    check('nonzero_exit_preserved_no_retry', nonzero)

    def deadline(r, d, h, v):
        s, calls, kills = services(r, end=float('inf'))
        result = m.run(d, h, services=s, repo=r)
        assert result['status'] == 'CALENDAR_DEADLINE' and kills == [314159]
        assert result['calendar_elapsed_s'] == 1200 and len(calls) == 1
    check('calendar_deadline_kills_only_owned_tree', deadline)

    def stopped(r, d, h, v):
        s, calls, kills = services(r, stopped=True)
        assert m.run(d, h, services=s, repo=r)['status'] == 'CONTROLLER_STOPPED'
        assert len(calls) == 1
    check('controller_fault_stop_does_not_continue', stopped)

    def incomplete(r, d, h, v):
        s, _, _ = services(r, incomplete=True)
        result = m.run(d, h, services=s, repo=r)
        assert result['status'] == 'SUPERVISOR_TECHNICAL_FAILURE'
        assert 'CONTROLLER_UNSTOPPED_INCOMPLETE_BATCH' in result['error']
    check('incomplete_receipt_cannot_be_called_complete', incomplete)

    def missing(r, d, h, v):
        s, _, _ = services(r, missing=True)
        result = m.run(d, h, services=s, repo=r)
        assert result['status'] == 'SUPERVISOR_TECHNICAL_FAILURE'
        assert 'CONTROLLER_FINAL_RECEIPT_MISSING' in result['error']
    check('missing_receipt_is_technical_failure', missing)

    m.save(require_out / 'checks.json', dict(protocol='K177-calendar-pure-precheck-v1',
                                            passed=True, checks=checks,
                                            real_process_calls=0, research_calls=0,
                                            thermal_integrations=0))
    print(json.dumps(dict(passed=True, checks=len(checks), real_process_calls=0)))


if __name__ == '__main__':
    main()
