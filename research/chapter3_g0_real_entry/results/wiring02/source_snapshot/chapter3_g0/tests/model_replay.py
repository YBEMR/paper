"""Artificial row replay helpers, never RC coefficients or an optimizer.

These rows are hand specified dimensionless test numbers. They are deliberately
not a physical transition model and cannot certify a scientific schedule.
Only test code imports this module; importing it performs no numerical work.
"""
from copy import deepcopy
from fractions import Fraction
from itertools import product
from unittest.mock import patch

from ..local_model import (ManualReplay, build_local_model, inherited_source_check,
                           _digest, _kernel, MANUAL_ORIGIN)


HAND_TEMPERATURE_ROWS = (
    ('1', '0', '0', '0', '1/1000', '0', '0', '0', '1/10000'),
    ('0', '1', '0', '0', '0', '1/1000', '0', '0', '1/10000'),
    ('0', '0', '1', '0', '0', '0', '1/1000', '0', '1/10000'),
    ('0', '0', '0', '1', '0', '0', '0', '1/1000', '1/10000'),
)
HAND_ENERGY_ROW = ('1/100000', '0', '0', '0',
                   '1/1000', '1/1000', '1/1000', '1/1000', '1/100')


class StoredRows:
    """Lookup/copy the above handwritten row; no expm, RC or heat integration."""
    source_kind = MANUAL_ORIGIN

    def __init__(self, platform, options, window_ms, interval_type):
        if len(platform['node_order']) != 4:
            raise ValueError('manual replay fixture requires four nodes')
        self.nodes = list(platform['node_order'])
        self.domains = list(platform['domains'])
        self.requests = []
        events = sorted({Fraction(0), Fraction(window_ms)/1000} |
            {Fraction(option[key])/1000 for option in options for key in ('start_ms', 'end_ms')})
        durations = {right-left for left, right in zip(events, events[1:])}
        states = product(*(platform['domains'][d]['opps'] for d in self.domains))
        self.rows = {}
        for state in states:
            for duration in durations:
                self.rows[tuple(state), duration] = {
                    'temperature': [[interval_type.rational(Fraction(v)) for v in row]
                                    for row in HAND_TEMPERATURE_ROWS],
                    'energy': [interval_type.rational(Fraction(v)) for v in HAND_ENERGY_ROW],
                }

    def power(self, state):
        # Handwritten baseline and local coefficient, unrelated to source RC.
        if len(state) != len(self.domains):
            raise ValueError('unknown manual control-state dimension')
        return ([Fraction(1), Fraction(0), Fraction(0), Fraction(0)],
                [Fraction(1, 100), Fraction(0), Fraction(0), Fraction(0)])

    def get(self, state, duration):
        key = tuple(state), Fraction(duration)
        if key not in self.rows:
            raise ValueError('no prestored artificial row for requested state/duration')
        self.requests.append((list(state), str(duration)))
        return deepcopy(self.rows[key])


def replay_rows(config, instance, condition, options, budget, *, strengthen=True):
    """Exercise inherited arithmetic with guards against all real entry paths.

    Called explicitly by the artificial A16 test. No original build_model or
    original Model constructor runs; Coefficients and thermal evaluation are
    forbidden. Returned counts/fingerprints are manual test evidence only.
    """
    kernel = _kernel()
    rows = StoredRows(instance['platform'], options, instance['window_ms'], kernel.I)
    backend = ManualReplay(options=deepcopy(options), coefficients=rows,
        input_sha256=_digest(instance), config_sha256=_digest(config))
    calls = {'forbidden_real_entries': 0}

    def forbidden(*args, **kwargs):
        calls['forbidden_real_entries'] += 1
        raise AssertionError('real construction/coefficient/evaluation path invoked')

    with patch.object(kernel, 'Coefficients', forbidden), \
            patch.object(kernel, 'build_model', forbidden), \
            patch.object(kernel, 'evaluate_candidate', forbidden), \
            patch.object(kernel.Model, '__init__', forbidden):
        model = build_local_model(config, instance, condition=condition,
            budget=budget, manual=True, manual_backend=backend,
            relax_auxiliary_integrality=True,
            strengthen_energy_lower_bounds=bool(strengthen))
    assert calls['forbidden_real_entries'] == 0
    assert model.preprocessing['manual_origin'] == MANUAL_ORIGIN
    assert model.preprocessing['formal_experiment_result'] is False
    tags = [record['tag'] for record in model.rows]
    assert any(tag.startswith('thermal_propagation') for tag in tags)
    assert any(tag.startswith('complete_energy') for tag in tags)
    assert any(tag.startswith('auto_opp_active_support') for tag in tags)
    if strengthen:
        assert model.energy_bound_certificates
    # Independent exact checks of mandatory one-hot row ordering and signs.
    first_stage_unique = next(row for row in model.rows if row['tag'] == 'stage_unique/upper')
    assert first_stage_unique['rhs'] == 1.0
    assert set(first_stage_unique['coef'].values()) <= {1.0}
    assert all('rounding_allowance' in row and 'rhs_interval' in row for row in model.rows)
    for row in model.rows:
        assert Fraction(row['rounding_allowance']) >= 0
    fingerprint = _digest({'names': model.names, 'bounds': model.bounds,
        'c': model.c, 'integer': model.integer, 'rows': model.rows})
    return model, {
        'kind': MANUAL_ORIGIN, 'formal_experiment_result': False,
        'source_protection': inherited_source_check(),
        'manual_rows': len(model.rows), 'manual_columns': len(model.names),
        'row_fingerprint': fingerprint,
        'manual_lookup_count': len(rows.requests),
        'real_entry_calls': calls['forbidden_real_entries'],
        'independent_checks': ['onehot signs/RHS', 'nonnegative rounding allowance',
            'original row metadata', 'auto-L rows', 'temperature/energy row tags',
            'energy lower-bound certificate rows'],
        'scope': 'artificial row export only; no optimizer or physical trajectory',
    }
