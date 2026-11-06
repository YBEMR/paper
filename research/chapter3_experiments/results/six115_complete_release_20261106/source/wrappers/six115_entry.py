"""Isolated seven-job controlled-six115 entry. Execution is deliberately disabled."""
import bootstrap
from copy import deepcopy
from datetime import datetime, timezone
from importlib import metadata
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import controlled_inputs as ci

HERE, REPO = bootstrap.ROOT, bootstrap.REPO
REFERENCE_PLAN = HERE.parent/'six115_schema_retry_20261105T110602Z/verification_plan.json'
REFERENCE_PLAN_SHA256 = '3a282bd53071e2df7be35595290ddd2d9759cb8e93eff2175ee59a4ec3fe9f04'
EXECUTION_ENABLED = False  # Public archival template; never execute without fresh review.
JOBS = [dict(id='six115_projected_milp', method='whole_milp', seed=None),
        dict(id='six115_heft', method='heft', seed=None)] + [
        dict(id=f'six115_sa{s}', method='sa', seed=s) for s in range(101, 106)]
SCOPE = dict(method_calls=7, method_seconds_each=600, method_seconds_total=4200,
    post_calls_at_most=7, post_seconds_each=60, post_seconds_total_at_most=420,
    job_calendar_seconds=780, batch_calendar_seconds=5520, retries=0)
EXCLUDED = {'results', '.runtime', '.git', '__pycache__', '.pytest_cache', 'cache', '.cache'}

def inventories():
    import os
    scientific = {}
    for directory, children, names in os.walk(REPO / 'research'):
        children[:] = sorted(n for n in children if n not in EXCLUDED)
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix in ('.py', '.m'):
                scientific[path.relative_to(REPO).as_posix()] = ci.sha(path)
    external = {p.name: ci.sha(p) for p in sorted(HERE.glob('*.py'))}
    inputs = {p.name: ci.sha(p) for p in sorted(ci.INPUTS.glob('*.json'))}
    return dict(scientific=scientific, external=external, inputs=inputs)

def verify_sources(plan):
    ci.load_controlled_inputs()
    actual = inventories()
    ci.require(ci.sha(REFERENCE_PLAN) == REFERENCE_PLAN_SHA256
        and actual['scientific'] == ci.read(REFERENCE_PLAN)['source_inventory']['scientific'], 'VALIDATED_SCIENTIFIC_BASELINE_DRIFT')
    ci.require(plan.get('source_inventory') == actual, 'SOURCE_OR_INPUT_INVENTORY_DRIFT')
    ci.require(plan.get('protocol_sha256') == ci.sha(HERE/'PROTOCOL.md'), 'FORMAL_PROTOCOL_DRIFT')
    ci.require(plan.get('validated_scientific_baseline_plan_sha256') == REFERENCE_PLAN_SHA256,
               'SCIENTIFIC_BASELINE_BINDING_MISSING')

def validate_plan(plan):
    from research.chapter3_experiments import bpre_formal_entry as reference
    ci.require(plan.get('schema') == 'six115-controlled-seven-formal-preparation-v2' and plan.get('execution_authorized') is False, 'NEW_SIX115_PLAN_REQUIRED')
    ci.require(plan.get('execution_enabled') is EXECUTION_ENABLED, 'EXECUTION_GATE_DRIFT')
    ci.require(plan.get('jobs') == JOBS and plan.get('scope') == SCOPE, 'SEVEN_JOB_SCOPE_DRIFT')
    ci.require(plan.get('input_identity') == ci.HASHES and plan.get('deadlines_ms') == ci.DEADLINES, 'SIX115_PLAN_IDENTITY')
    ci.require(plan.get('input_file') == str(ci.INPUTS / 'input_instance.json') and plan.get('config_file') == str(ci.INPUTS / 'input_config.json'), 'INPUT_PATH_DRIFT')
    ci.require(plan.get('native_options') == reference.EXPECTED_NATIVE_OPTIONS and len(plan['native_options']) == 23, 'NATIVE_23_OPTIONS_DRIFT')
    ci.require(plan.get('native_executable') == str(reference.NATIVE_EXECUTABLE), 'NATIVE_R2023B_PATH_DRIFT')
    ci.require(plan.get('builder_flags') == reference.base.BUILDER_FLAGS, 'SCIENTIFIC_BUILDER_FLAGS_DRIFT')
    ci.require(plan.get('cut_max_iterations') == 10 and plan.get('outer_round_limit') == 50, 'ROUND_POLICY_DRIFT')
    ci.require(plan.get('cleanup') == {'grace_seconds': 20, 'total_seconds': 40, 'watchdog_seconds': 705}, 'CLEANUP_POLICY_DRIFT')
    ci.require(plan.get('runtime_certificate_policy') == 'fresh_from_actual_model_each_request_no_dimension_constants', 'CERTIFICATE_POLICY_DRIFT')
    ci.require(plan.get('schema_adapter_policy') == 'fixed-byte-input-local-schema-view-v1'
        and plan.get('schema_adapter_scope') == 'all_methods_posts_and_final_legality_with_alias_restoration', 'SCHEMA_ADAPTER_SCOPE_DRIFT')
    ci.require(plan.get('diagnostic_single_request_limit') is False and plan.get('conditional_feedback_enabled') is True,
               'FORMAL_MULTI_REQUEST_FEEDBACK_REQUIRED')
    verify_sources(plan)

def freeze(folder):
    from research.chapter3_experiments import bpre_formal_entry as reference
    folder = Path(folder).resolve()
    ci.require(folder == HERE / 'prepared_plan' and not folder.exists(), 'NEW_PLAN_DIRECTORY_REQUIRED')
    ci.load_controlled_inputs()
    plan = dict(schema='six115-controlled-seven-formal-preparation-v2', execution_authorized=False,
        execution_enabled=EXECUTION_ENABLED, jobs=JOBS, scope=SCOPE,
        input_identity=ci.HASHES, deadlines_ms=ci.DEADLINES,
        input_file=str(ci.INPUTS / 'input_instance.json'), config_file=str(ci.INPUTS / 'input_config.json'),
        source_inventory=inventories(), builder_flags=reference.base.BUILDER_FLAGS,
        native_options=reference.EXPECTED_NATIVE_OPTIONS, native_executable=str(reference.NATIVE_EXECUTABLE),
        native_executable_sha256=ci.sha(reference.NATIVE_EXECUTABLE),
        python_executable=str(Path(sys.executable).resolve()), python_version=sys.version,
        dependencies={n: metadata.version(n) for n in ('numpy', 'scipy', 'mpmath', 'psutil')},
        cleanup=dict(grace_seconds=20, total_seconds=40, watchdog_seconds=705),
        cut_max_iterations=10, outer_round_limit=50,
        runtime_certificate_policy='fresh_from_actual_model_each_request_no_dimension_constants',
        schema_adapter_policy='fixed-byte-input-local-schema-view-v1',
        schema_adapter_scope='all_methods_posts_and_final_legality_with_alias_restoration',
        diagnostic_single_request_limit=False, conditional_feedback_enabled=True,
        protocol_sha256=ci.sha(HERE/'PROTOCOL.md'),
        validated_scientific_baseline_plan_sha256=REFERENCE_PLAN_SHA256,
        validated_scientific_baseline_plan=str(REFERENCE_PLAN),
        static_size=ci.read(ci.INPUTS / 'static_size.json'), actual_model_dimensions=None,
        actual_projection_dimensions=None, actual_certificate=None, actual_safe_witness=None,
        preparation_contract_preserved=True, preparation_is_not_authorization=True,
        historical_candidate_or_certificate_input=False, post_unresolved_stops_batch=True,
        created_utc=datetime.now(timezone.utc).isoformat())
    validate_plan(plan)
    folder.mkdir()
    save(folder / 'plan.json', plan)
    save(folder / 'approval_template.json', dict(schema='six115-separate-user-approval-v1',
        approved_by_user=False, approval_source='USER_CURRENT_CONVERSATION', human_authorization_text='',
        plan_sha256=ci.sha(folder / 'plan.json'), scope=SCOPE, output_directory=None))
    return dict(state='FROZEN_ENABLED_REQUIRES_BOUND_APPROVAL' if EXECUTION_ENABLED else 'PREPARED_EXECUTION_DISABLED', plan=str(folder / 'plan.json'), sha256=ci.sha(folder / 'plan.json'))

def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False, default=str)
        stream.write('\n')

def execution_gate():
    ci.require(EXECUTION_ENABLED, 'EXECUTION_DISABLED_PREPARATION_ONLY_NO_NATIVE_OR_THERMAL')

def authorize(plan_path, approval_path, output, *, verify_subject=True):
    execution_gate()
    plan_path, approval_path, output = map(lambda p: Path(p).resolve(), (plan_path, approval_path, output))
    plan, auth = ci.read(plan_path), ci.read(approval_path)
    validate_plan(plan)
    ci.require(plan_path == HERE / 'prepared_plan/plan.json' and output.is_relative_to(HERE / 'execution')
               and output != HERE / 'execution', 'ISOLATED_EXECUTION_PATH_REQUIRED')
    ci.require(auth.get('schema') == 'six115-separate-user-approval-v1' and auth.get('approved_by_user') is True
        and auth.get('approval_source') == 'USER_CURRENT_CONVERSATION'
        and isinstance(auth.get('human_authorization_text'), str) and auth['human_authorization_text'].strip(), 'NEW_EXPLICIT_USER_AUTHORIZATION_REQUIRED')
    ci.require(auth.get('plan_sha256') == ci.sha(plan_path) and auth.get('scope') == SCOPE
        and Path(auth.get('output_directory') or '').resolve() == output, 'NEW_PLAN_AUTHORIZATION_BINDING')
    ci.require(plan['python_executable'] == str(Path(sys.executable).resolve()) and plan['python_version'] == sys.version, 'PYTHON_DRIFT')
    ci.require(all(metadata.version(n) == v for n, v in plan['dependencies'].items()), 'DEPENDENCY_DRIFT')
    ci.require(ci.sha(plan['native_executable']) == plan['native_executable_sha256'], 'NATIVE_BINARY_DRIFT')
    return plan

def configure():
    """Bind the copied lifecycle's own globals; never mutate the original entry."""
    import six115_controller as c
    if getattr(c, '_six115_configured', False):
        return c
    from research.chapter3_experiments.natural_full_600_entry import validate_response_600
    c.ROOT, c.EXP, c.RESULTS = REPO, bootstrap.SOURCE, HERE / 'execution'
    c.ENTRY, c.WORKER_MODULE = str(HERE / 'six115_entry.py'), 'six115_entry'
    c.INPUT, c.CONFIG = ci.INPUTS / 'input_instance.json', ci.INPUTS / 'input_config.json'
    c.PREPARATION, c.STATIC, c.DOMAIN = ci.INPUTS, ci.INPUTS / 'static_size.json', ci.INPUTS / 'domain_audit.json'
    c.JOBS, c.SCOPE = deepcopy(JOBS), deepcopy(SCOPE)
    c.METHOD_SECONDS, c.METHOD_WATCHDOG_SECONDS = 600, 705
    c.NATIVE_RESPONSE_VALIDATOR = validate_response_600
    c.verify_sources, c.validate_plan, c.authorize, c.freeze = verify_sources, validate_plan, authorize, freeze
    # The factory and lifecycle are captured from THIS controller, with its own globals.
    original_whole, original_worker, original_run = c.run_whole, c.worker, c.run
    owner = SimpleNamespace(base=c, repaired=SimpleNamespace(_native_factory_original=c.native_session_factory))
    def whole(ticket, plan, folder):
        from live_heft_initializer import install_initializer
        from projected_integration import install_projection
        sys.path.insert(0, str(c.EXP / 'p0_batch'))
        import audit_whole, audit_heuristic
        prior_seconds = audit_whole.SECONDS, audit_heuristic.SECONDS
        audit_whole.SECONDS = audit_heuristic.SECONDS = 600
        config, instance = ci.load_controlled_inputs()
        context = {}
        try:
            with install_projection(owner, folder), install_initializer(instance, config, folder / 'online_heft',
                    origin=ticket['origin'], deadline=ticket['scientific_deadline'], audit_context=context):
                return original_whole(ticket, plan, folder)
        finally:
            audit_whole.SECONDS, audit_heuristic.SECONDS = prior_seconds
            c.save(folder / 'initializer_context.json', context)
    def worker(ticket_path, token):
        execution_gate()
        from charged_heuristics import install_charged_recorder
        with install_charged_recorder(Path(ticket_path).parent / 'charged_candidate_receipts'):
            return original_worker(ticket_path, token)
    def run(*args, **kwargs):
        execution_gate()
        return original_run(*args, **kwargs)
    c.run_whole, c.worker, c.run = whole, worker, run
    c._six115_configured = True
    return c

def main():
    return configure().main()

if __name__ == '__main__':
    raise SystemExit(main())
