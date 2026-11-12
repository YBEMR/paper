"""One fresh formal comparison on the unchanged natural full domain.

Reuse the existing lifecycle and manual approval path. Only the MILP numerical
representation changes, using the previously verified exact equality mapping.
No archived candidate or numerical matrix is a method input.
"""
from copy import deepcopy
from pathlib import Path
import sys

from research.chapter3_experiments import natural_full_entry as base

ENTRY = 'research/chapter3_experiments/natural_full_repaired_entry.py'
BASE_ENTRY = 'research/chapter3_experiments/natural_full_entry.py'
ADAPTER = 'research/chapter3_experiments/numeric_case_diagnostic/equality_session.py'
HELPER = 'research/chapter3_experiments/numeric_case_diagnostic/exact_equalities.py'
REPRESENTATION = 'exact_opposite_rows_to_equalities_v1'
PREPARATION = base.RESULTS/'natural_full_repaired_preparation01'
OLD_PLAN = base.RESULTS/'natural_full_preparation01/plan.json'
_validate_original = base.validate_plan
_native_factory_original = base.native_session_factory

def validate_plan(plan):
    _validate_original(plan)
    base.require(plan.get('numerical_representation') == REPRESENTATION, 'EQUALITY_REPRESENTATION_REQUIRED')
    base.require(plan.get('representation_adapter') == ADAPTER and plan.get('representation_helper') == HELPER,
                 'REPRESENTATION_INTERFACE_DRIFT')
    base.require(all(p in plan['source_sha256'] for p in (BASE_ENTRY, ENTRY, ADAPTER, HELPER)),
                 'REPRESENTATION_SOURCES_MISSING')


def freeze(folder):
    from importlib import metadata
    folder = Path(folder).resolve()
    base.require(folder == PREPARATION and not folder.exists(), 'NEW_PREPARATION_REQUIRED')
    old = base.read(OLD_PLAN)
    # The original scientific source set remains unchanged. The sole old
    # controller edit exposes its already-fixed worker name as a constant.
    for rel, digest in old['source_sha256'].items():
        if rel != BASE_ENTRY:
            base.require(base.sha(base.ROOT/rel) == digest, 'ORIGINAL_SOURCE_DRIFT:'+rel)
    archived_base = base.git_bytes('show', 'c02306757ade2304ddbc245eeeb9de7d4cfc6b15:'+BASE_ENTRY)
    marker = b"ENTRY = 'research/chapter3_experiments/natural_full_entry.py'"
    end = archived_base.index(marker)+len(marker)
    newline = b'\r\n' if archived_base[end:end+2] == b'\r\n' else b'\n'
    expected = archived_base.replace(marker, marker+newline+
        b"WORKER_MODULE = 'research.chapter3_experiments.natural_full_entry'").replace(
        b"[sys.executable, '-B', '-m', 'research.chapter3_experiments.natural_full_entry',",
        b"[sys.executable, '-B', '-m', WORKER_MODULE,")
    base.require((base.ROOT/BASE_ENTRY).read_bytes() == expected, 'UNDECLARED_CONTROLLER_CHANGE')
    plan = deepcopy(old)
    plan.update(baseline_commit=base.git_bytes('rev-parse', 'HEAD').decode().strip(),
                numerical_representation=REPRESENTATION, representation_adapter=ADAPTER,
                representation_helper=HELPER,
                python_executable=str(Path(sys.executable).resolve()), python_version=sys.version,
                dependencies={n: metadata.version(n) for n in ('numpy', 'scipy', 'psutil')},
                initialization='Fresh original per-method initialization; no historical matrix, candidate or cache input.',
                callback_admission='Original Model logical/schedule checks and original full electrothermal evaluator unchanged.',
                final_numeric_admission='Timely native return checked against original rows; evidence sidecar only, original return preserved.')
    for rel in (BASE_ENTRY, ENTRY, ADAPTER, HELPER):
        plan['source_sha256'][rel] = base.sha(base.ROOT/rel)
    validate_plan(plan)
    base.verify_sources(plan)
    base.save(folder/'plan.json', plan)
    base.save(folder/'approval_template.json', {
        'schema': 'natural-full-three-user-approval-v1', 'approved_by_user': False,
        'approval_source': 'USER_CURRENT_CONVERSATION', 'human_authorization_text': '',
        'subject_commit': None, 'plan_sha256': base.sha(folder/'plan.json'), 'scope': base.SCOPE,
        'output_directory': None, 'not_an_external_agent_loop_review': True})
    return {'plan': str(folder/'plan.json'), 'sha256': base.sha(folder/'plan.json'), 'authorized': False}


def native_session_factory(plan):
    original_factory = _native_factory_original(plan)
    def create(*args, **kwargs):
        session = original_factory(*args, **kwargs)
        try:
            from research.chapter3_experiments.numeric_case_diagnostic.equality_session import attach
            return attach(session)
        except BaseException:
            session.close()
            raise
    return create


def configure():
    """Bind the existing controller only for this entry's dedicated process."""
    base.ENTRY = ENTRY
    base.WORKER_MODULE = 'research.chapter3_experiments.natural_full_repaired_entry'
    base.PREPARATION = PREPARATION
    base.validate_plan = validate_plan
    base.freeze = freeze
    base.native_session_factory = native_session_factory


if __name__ == '__main__':
    configure()
    raise SystemExit(base.main())
