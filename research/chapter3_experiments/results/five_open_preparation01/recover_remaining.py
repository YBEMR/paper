"""K148 minimal post-audit repair; execute only the never-started linked-5 call.

The immutable 167-source protocol and consumed old call are never rewritten.
The correction is exact outward-interval reproduction, not a temperature/energy
tolerance. --precheck does zero research work. A separate --run authorization
is mandatory, and the caller must impose the remaining 607-second watchdog.
"""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from fractions import Fraction as F
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import traceback
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[2]
REPO = HERE.parent.parent
ROOT = HERE/'results/linked_five_open_pair01'
sys.path.insert(0, str(HERE))
import run_five_open_pair as runner

PROTOCOL = 'K148-post-audit-outward-rounding-recovery-v1'
REMAINING_CLAIM = ROOT/'claims/remaining_recovery.json'
PRESERVED = ROOT/'recovery_before'
CHECKS = Path(__file__).with_name('recovery_precheck01.json')
ORIGINAL_AGGREGATE_ISSUES = runner.aggregate_issues
NORMAL = {'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'}


def exact_enclosure(receipt, declaration):
    """Exact Fraction inclusion plus exact reproduction of existing 60-digit I."""
    from scene_adapter import I
    exact = [F(0), F(0)]
    replay = I(0)
    for sid, definition in declaration['scene_spec'].items():
        values = receipt['scenes'][sid]['energy_J']
        lo, hi = map(F, values)
        weight = F(definition['weight'])
        if weight < 0 or lo < 0 or hi < lo:
            return {'accepted': False, 'reason': 'INVALID_SCENE_INTERVAL_OR_WEIGHT'}
        exact[0] += weight*lo
        exact[1] += weight*hi
        replay += I(values[0], values[1])*I.rational(weight)
    lower, upper = map(F, receipt['weighted_energy_J'])
    reproduced = [F(replay.lo), F(replay.hi)]
    included = lower <= exact[0] <= exact[1] <= upper
    same_outward = [lower, upper] == reproduced
    return {'accepted': included and same_outward, 'exact_inclusion': included,
        'original_60digit_outward_endpoints_reproduced': same_outward,
        'aggregate_J': list(map(str, (lower, upper))), 'exact_weighted_J': list(map(str, exact)),
        'outward_reproduced_J': list(map(str, reproduced)),
        'lower_padding_J': str(exact[0]-lower), 'upper_padding_J': str(upper-exact[1]),
        'scope': 'same existing interval arithmetic only; no physical trajectory evaluation'}


def corrected_aggregate_issues(receipt, candidate, declaration, condition):
    issues = ORIGINAL_AGGREGATE_ISSUES(receipt, candidate, declaration, condition)
    if 'WEIGHTED_ENERGY_MISMATCH' not in issues:
        return issues
    try:
        check = exact_enclosure(receipt, declaration)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return issues
    if check['accepted']:
        return [v for v in issues if v != 'WEIGHTED_ENERGY_MISMATCH']
    return issues


def validate_ledger(ledger):
    return bool(ledger.get('state') == 'BLOCKED' and ledger.get('consumed') == 1
        and ledger.get('reserved_method_budget_s') == 300
        and [r.get('id') for r in ledger.get('calls', [])] == ['old_linked4'])


def load_analysis():
    path = ROOT/'analysis01/analyze.py'
    spec = importlib.util.spec_from_file_location('K148_readonly_recovery_receipt_helpers', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_old():
    """Reject every condition except the demonstrated sole post-audit defect."""
    declaration = runner.admission(ROOT)
    ledger = runner.read(ROOT/'ledger.json')
    if not validate_ledger(ledger):
        raise ValueError('Only the original blocked one-consumed/300-reserved state can recover')
    if (not runner.GLOBAL_CLAIM.is_file() or REMAINING_CLAIM.exists()
            or (ROOT/'claims/new_linked5.json').exists() or (ROOT/'new_linked5').exists()):
        raise FileExistsError('Recovery/new call already claimed or original claim missing')
    row = runner.read(ROOT/'claims/old_linked4_result.json')
    if (row.get('id') != 'old_linked4' or row.get('state') != 'BLOCKED'
            or row.get('errors') != [] or row.get('context', {}).get('hard_errors') != ['WEIGHTED_ENERGY_MISMATCH']
            or row.get('domain_issues') != [] or row.get('source_identity_valid') is not True
            or row.get('context', {}).get('input_identity_valid') is not True
            or row.get('context', {}).get('worker_isolation') != 'VERIFIED'
            or row.get('context', {}).get('observed_numerical_rejection') is not False):
        raise ValueError('Original row is not the sole demonstrated weighted-outward audit defect')
    result = runner.read(ROOT/'old_linked4/result.json')
    if result != runner.read(ROOT/'old_linked4/wrapper_raw_result.json'):
        raise ValueError('Original raw/result diverged')
    correction = exact_enclosure(result['aggregation'], declaration)
    if not correction['accepted']:
        raise ValueError('Existing exact intervals do not reproduce original outward endpoints')
    helper = load_analysis()
    instance = runner.read(ROOT/'old_linked4/input_instance.json')
    adapted = dict(declaration, old_opened_by_scene=declaration['first_opened_by_scene'],
        new_opened_by_scene=declaration['linked_opened_by_job']['old_linked4'],
        linked_opened_by_scene=declaration['linked_opened_by_job']['old_linked4'])
    receipt = helper.h.receipt_audit(result, instance, adapted)
    conditions = helper.k.condition_audit(result, instance, adapted)
    warm = helper.h.warm_snapshot_audit(result, instance, helper.h.verified_updates(result, instance))
    if not (receipt.get('all_pass') and conditions and all(v['all_pass'] for v in conditions)
            and all(v['all_pass'] for v in warm)):
        raise ValueError('Independent original receipt/domain/warm audit failed')
    artifact_manifest = runner.read(ROOT/'claims/old_linked4_artifact_sha256.json')
    if any(not (ROOT/'old_linked4'/n).is_file() or runner.sha(ROOT/'old_linked4'/n) != h
           for n,h in artifact_manifest.items()):
        raise ValueError('Original method artifact mismatch')
    with patch.object(runner, 'aggregate_issues', corrected_aggregate_issues):
        corrected = runner.result_records(runner.jobs()[0], result, declaration,
            ROOT/'old_linked4', input_valid=True, source_valid=True, errors=[])
    if corrected['execution']['execution_status'] not in NORMAL or corrected['context']['hard_errors']:
        raise ValueError('Corrected stored-only audit still has a runtime/domain/numerical fault')
    named = ['ledger.json', 'claims/old_linked4_result.json', 'claims/old_linked4.json',
             'claims/old_linked4_artifact_sha256.json', 'old_linked4/result.json',
             'old_linked4/wrapper_raw_result.json', 'declaration.json', 'protocol.md',
             'launcher_claim.json', 'launcher_result.json', 'wrapper_timing.json']
    originals = {n: runner.sha(ROOT/n) for n in named}
    originals['GLOBAL_CLAIM'] = runner.sha(runner.GLOBAL_CLAIM)
    return {'declaration': declaration, 'ledger': ledger, 'original_row': row,
        'corrected_record': corrected, 'original_sha256': originals,
        'outward_check': correction, 'independent_receipt_passed': True,
        'independent_condition_checks': [v['all_pass'] for v in conditions],
        'analysis_helper_sha256': runner.sha(ROOT/'analysis01/analyze.py')}


class RegressionTests(unittest.TestCase):
    def fixture(self):
        return {'scenes': {'S': {'energy_J': ['1', '1']}},
                'weighted_energy_J': ['0.'+'3'*60, '0.'+'3'*59+'4']}, {
                'scene_spec': {'S': {'weight': '1/3'}}}

    def test_outward_rounding_is_valid_without_tolerance(self):
        r,d = self.fixture(); c = exact_enclosure(r,d)
        self.assertTrue(c['accepted'])
        self.assertNotEqual(c['upper_padding_J'], '0')

    def test_non_enclosure_rejected(self):
        r,d = self.fixture(); r['weighted_energy_J'][1] = r['weighted_energy_J'][0]
        self.assertFalse(exact_enclosure(r,d)['accepted'])

    def test_arbitrary_widening_not_same_original_arithmetic(self):
        r,d = self.fixture(); r['weighted_energy_J'] = ['0','1']
        c = exact_enclosure(r,d)
        self.assertTrue(c['exact_inclusion']); self.assertFalse(c['accepted'])

    def test_invalid_scene_interval_rejected(self):
        r,d = self.fixture(); r['scenes']['S']['energy_J'] = ['2','1']
        self.assertFalse(exact_enclosure(r,d)['accepted'])

    def test_other_fault_preserved(self):
        r,d = self.fixture()
        with patch.dict(globals(), ORIGINAL_AGGREGATE_ISSUES=lambda *args: ['WEIGHTED_ENERGY_MISMATCH','OTHER_FAULT']):
            self.assertEqual(corrected_aggregate_issues(r,{},d,{}), ['OTHER_FAULT'])

    def test_no_change_when_no_weight_error(self):
        with patch.dict(globals(), ORIGINAL_AGGREGATE_ISSUES=lambda *args: ['OTHER_FAULT']):
            self.assertEqual(corrected_aggregate_issues({}, {}, {}, {}), ['OTHER_FAULT'])

    def test_no_consumed_call_may_repeat(self):
        old = {'state':'BLOCKED','consumed':1,'reserved_method_budget_s':300,'calls':[{'id':'old_linked4'}]}
        self.assertTrue(validate_ledger(old))
        for key,value in [('consumed',2),('state','RUNNING'),('reserved_method_budget_s',600)]:
            changed = dict(old); changed[key] = value
            self.assertFalse(validate_ledger(changed))
        changed = deepcopy(old); changed['calls'].append({'id':'new_linked5'})
        self.assertFalse(validate_ledger(changed))


def precheck():
    if CHECKS.exists():
        raise FileExistsError('Never replace an existing recovery precheck record')
    before = {n:runner.sha(ROOT/n) for n in ('ledger.json','claims/old_linked4_result.json','old_linked4/result.json')}
    captured = io.StringIO()
    with redirect_stdout(captured), redirect_stderr(captured):
        result = unittest.TextTestRunner(stream=captured, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RegressionTests))
        audit = inspect_old()
    unchanged = before == {n:runner.sha(ROOT/n) for n in before}
    if not result.wasSuccessful() or not unchanged:
        raise ValueError('Recovery regression failed or immutable records changed')
    report = {'protocol':PROTOCOL,'passed':True,'script_sha256':runner.sha(__file__),
        'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
        'research_calls':0,'native_calls':0,'thermal_evaluations':0,'originals_unchanged':unchanged,
        'original_sha256':audit['original_sha256'],'outward_check':audit['outward_check'],
        'independent_receipt_passed':True,'independent_condition_checks':audit['independent_condition_checks'],
        'corrected_old_execution':audit['corrected_record']['execution'],
        'source_sha256':audit['declaration']['source_sha256'],'tests':captured.getvalue()}
    runner.save(CHECKS, report)
    print(json.dumps({k:report[k] for k in ('passed','tests_run','research_calls','corrected_old_execution')},ensure_ascii=False))
    return report


def run(*, execution_authorized=False):
    if execution_authorized is not True:
        raise PermissionError('Root must explicitly authorize continuation after recovery precheck')
    checks = runner.read(CHECKS)
    if (checks.get('passed') is not True or checks.get('script_sha256') != runner.sha(__file__)
            or checks.get('research_calls') != 0 or checks.get('native_calls') != 0
            or checks.get('thermal_evaluations') != 0):
        raise ValueError('Matching successful zero-call recovery precheck required')
    audit = inspect_old()
    if checks['original_sha256'] != audit['original_sha256']:
        raise ValueError('Original blocked evidence changed after recovery precheck')
    # Preserve the full original ledger/result BEFORE changing only continuation state.
    PRESERVED.mkdir(exist_ok=False)
    for name in ('ledger.json','claims/old_linked4_result.json'):
        target = PRESERVED/Path(name).name
        target.write_bytes((ROOT/name).read_bytes())
    with REMAINING_CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'protocol':PROTOCOL,'script_sha256':runner.sha(__file__),
            'checks_sha256':runner.sha(CHECKS),'original_sha256':audit['original_sha256'],
            'new_call_only':True,'no_retry':True,'remaining_outer_watchdog_s':607,
            'created_utc':runner.now()},stream,indent=2)
    runner.save(ROOT/'corrected_old_record.json',{
        'original_status_preserved':'TECHNICAL_FAILURE_CONFIRMED',
        'correction':'sole post-audit equality defect; exact enclosure and same 60-digit outward arithmetic',
        'original_claim_sha256':audit['original_sha256']['claims/old_linked4_result.json'],
        'source_revision_protocol':PROTOCOL, **audit['corrected_record']})
    entries = runner.entry_points()
    job = runner.jobs()[1]
    with (ROOT/'claims/new_linked5.json').open('x',encoding='utf-8') as stream:
        json.dump({**job,'seconds':300,'claimed_utc':runner.now(),'no_retry':True,
                   'continuation_protocol':PROTOCOL},stream)
    ledger = audit['ledger']
    row = {**job,'state':'RUNNING','started_utc':runner.now(),'continuation_protocol':PROTOCOL}
    ledger['calls'].append(row)
    ledger.update(state='RUNNING',consumed=2,reserved_method_budget_s=600,
                  continuation_protocol=PROTOCOL)
    runner.save(ROOT/'ledger.json',ledger)
    result, identity, errors = None, {'input_verified':None}, []
    started = time.monotonic()
    try:
        result, identity = runner.execute(job,ROOT,audit['declaration'],entries)
    except BaseException:
        errors.append(traceback.format_exc())
    returned = time.monotonic()-started
    source_valid = True
    try:
        runner.admission(ROOT)
    except Exception:
        source_valid = False;errors.append(traceback.format_exc())
    post = time.monotonic()
    if isinstance(result,dict):
        runner.save(ROOT/'new_linked5/wrapper_raw_result.json',result)
    try:
        with patch.object(runner,'aggregate_issues',corrected_aggregate_issues):
            records = runner.result_records(job,result,audit['declaration'],ROOT/'new_linked5',
                input_valid=identity['input_verified'],source_valid=source_valid,errors=errors)
    except Exception:
        errors.append(traceback.format_exc())
        records = {'execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED'},
                   'usable_U_J':None,'record_errors':errors}
    acceptable = records['execution']['execution_status'] in NORMAL
    row.update(state='COMPLETED' if acceptable else 'BLOCKED',completed_utc=runner.now(),
        errors=errors,method_return_inclusive_wall_s=returned,source_identity_valid=source_valid,**records)
    runner.save(ROOT/'claims/new_linked5_result.json',row)
    row['post_method_record_wall_s'] = time.monotonic()-post
    artifacts = {p.relative_to(ROOT/'new_linked5').as_posix():runner.sha(p)
                 for p in sorted((ROOT/'new_linked5').rglob('*')) if p.is_file()}
    runner.save(ROOT/'claims/new_linked5_artifact_sha256.json',artifacts)
    ledger['state'] = 'COMPLETED_WITH_POST_AUDIT_RECOVERY' if acceptable else 'BLOCKED'
    runner.save(ROOT/'ledger.json',ledger)
    # Verify original old call/claim and global consumption record remain bit-identical.
    fixed = {n:h for n,h in audit['original_sha256'].items() if n!='ledger.json'}
    for name,expected in fixed.items():
        path = runner.GLOBAL_CLAIM if name=='GLOBAL_CLAIM' else ROOT/name
        if runner.sha(path)!=expected:
            raise ValueError('Immutable original evidence changed: '+name)
    runner.save(ROOT/'recovery_result.json',{'protocol':PROTOCOL,'execution_status':records['execution']['execution_status'],
        'accepted_remaining_call':acceptable,'consumed_calls':2,'reserved_method_budget_s':600,
        'remaining_method_return_wall_s':returned,'original_old_claim_unchanged':True,
        'original_ledger_preserved_sha256':runner.sha(PRESERVED/'ledger.json'),
        'original_status_not_rewritten':True,'no_research_call_retried':True,'completed_utc':runner.now()})
    print(json.dumps({'remaining_call_finished':True,'execution':records['execution'],
                      'usable_U_J':records.get('usable_U_J')},ensure_ascii=False),flush=True)
    return acceptable


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--precheck',action='store_true')
    mode.add_argument('--run',action='store_true')
    parser.add_argument('--execution-authorized',action='store_true')
    args = parser.parse_args()
    if args.precheck:
        precheck()
    else:
        raise SystemExit(0 if run(execution_authorized=args.execution_authorized) else 1)
