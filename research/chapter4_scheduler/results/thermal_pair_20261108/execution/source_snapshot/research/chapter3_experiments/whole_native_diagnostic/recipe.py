"""Pure callable binding for the proposed one-request diagnostic.

Requires explicit dependency injection; no imports of the physical model,
MATLAB or an optimizer, and no execution or authorization entry here.
"""
from functools import partial


def make_bindings(entries):
    """Bind the existing whole stack without executing any callable.

    The future confirmed runner must use deadline_dispatch's billed loader,
    independent L0, single fresh input and current-input identity checks.
    This function is only its inner whole-entry replacement.
    """
    required = {'context', 'whole', 'builder', 'session'}
    if set(entries) != required or not all(callable(v) for v in entries.values()):
        raise ValueError('Exactly the four frozen whole dependencies are required')
    factory = partial(entries['session'], cut_max_iterations=10)
    context = entries['context'](session_factory=factory)
    kwargs = {
        'seconds': 300, 'feedback_kind': 'conditional',
        'session_factory': context.session_factory,
        'model_builder': partial(entries['builder'], prefilter_deadlines=True,
                                 cumulative_precedence=False),
        'diagnostic_solver': partial(context.solve_formal_diagnostic, max_rounds=1)}
    limits = {'research_method_calls': 1, 'native_requests': 1,
              'actual_max_rounds': 1, 'legacy_entry_outer_round_limit_label': 50,
              'corrected_limit_is_separately_recorded': True}
    return context, partial(entries['whole'], **kwargs), limits
