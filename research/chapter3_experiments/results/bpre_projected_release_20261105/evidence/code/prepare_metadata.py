"""Freeze only metadata and source provenance. No model/candidate/native call."""
from pathlib import Path
from datetime import datetime,timezone
import json
import hashlib
import live_variant as v

root=Path(__file__).resolve().parent
previous=root.parent/'bpre_live_heft_milp_20261105T011253Z'
protocol=json.loads((previous/'protocol.json').read_text(encoding='utf-8'))
protocol.update(task='B.pre online enhanced-HEFT initialized equivalent projected MILP, one 600-second execution',
    selected_execution_task_id='delegated-current-once-600-projection',scope=v.SCOPE,
    preparation_first_host_check_utc='2026-11-05T06:46:38.653979+00:00',
    sequence=protocol['sequence'][:6]+[
        'Per request original matrix export, exact opposite-row pairing, certified OR projection and duplicate/empty removal',
        'Full initial-vector original-row admission, projection and original-row roundtrip; native first x0 only',
        'Original native intlinprog; each callback/final independently lifted and checked against all original rows, logic and complete SAFE',
        'Original 50-round conditional feedback; any row/logic/binding rejection fails closed',
        'Commit only after charged certificate/receipt archival and strict root deadline check',
        'Original process cleanup after scientific stop, no further search or evaluation'],
    unchanged=['Frozen B.pre input/config/physics/safety/accuracy/start domain/builder flags',
        'Live full enhanced HEFT parameters/order/seed and original x0 completion',
        'Original native intlinprog and 23 non-time options; remaining MaxTime only',
        '50-round outer limit, conditional thermal feedback, original SAFE decoder/evaluator',
        'One 600-second parent root from before per-job source verification/import/startup'],
    projection=dict(original_vars=8887,original_builder_rows=56320,integer_vars=523,
        equality_rows=3153,inequalities_after_pairing=50014,removed_columns=546,
        removed_inequalities=1372,reduced_vars=8341,reduced_inequalities=48642,
        retained_original_equalities=True,objective_or_feasible_domain_change=False),
    engineered_differences=['Certified OR variable elimination and exact duplicate/empty inequality removal',
        'Original complete-row admission for every callback/final before original logic and full SAFE',
        'No schedule evaluation cache; repeated vectors independently evaluated',
        'Candidate row/logic rejection terminates fail-closed rather than continuing callbacks',
        'Strict charged-archive receipt commit; native timeout and publications preserved',
        'Original 2 GiB gate before/after READY and once per second during checks'],
    resource_gate=dict(minimum_available_bytes=2*1024**3,existing_matlab_forbidden=True,
        user_applications_not_closed=True,resource_failure_no_retry=True),
    baseline=dict(matched_directory=str(previous),matched_U_J='0.920195499983960944974381976769171389159940855612137674194178',
        limitation='Single run with additional conversion/admission/no-cache overhead. Original seven-method MILP used a different initializer; no sole-cause speedup or general superiority claim.'),
    historical_candidate_input=False,retries=0,post_calls=0)
v.save(root/'protocol.json',protocol)
v.save(root/'authorization.json',dict(source='USER_CURRENT_CONVERSATION',scope=v.SCOPE,
    authorization_text='User answered 可以，继续吧 to testing the simplified model on B.pre under the original budget and evaluation rules while retaining the original results.',
    delegated_authorization='Parent explicitly authorizes one B.pre equivalent projected model 600-second end-to-end execution with online enhanced HEFT, no retry, no push/merge/history overwrite.',
    recorded_at_utc=datetime.now(timezone.utc).isoformat()))
files={}
for name in ('live_variant.py','live_heft_initializer.py','run_logged.py','test_live_variant.py','test_live_heft_initializer.py'):
    files[str(previous/name)]=v.sha(previous/name)
old=root.parent/'bpre_native_projection_20261105T032053Z'
for name in ('native_projection.py','projection_admission.py','certified_projection.py'):
    files[str(old/'src'/name)]=v.sha(old/'src'/name)
v.save(root/'source_provenance.json',dict(parent_source_sha256=files,
    core_projection_unchanged=v.sha(root/'certified_projection.py')==files[str(old/'src/certified_projection.py')],
    admission_core_unchanged=v.sha(root/'projection_admission.py')==files[str(old/'src/projection_admission.py')],
    live_initializer_unchanged=v.sha(root/'live_heft_initializer.py')==files[str(previous/'live_heft_initializer.py')],
    new_native_adapter_changes='Only deadline commit/timeout/native evidence preservation, phase accounting and event metadata; no transformation/math change',
    created_utc=datetime.now(timezone.utc).isoformat()))
print('METADATA_PREPARED_NO_METHOD_STARTED',flush=True)
