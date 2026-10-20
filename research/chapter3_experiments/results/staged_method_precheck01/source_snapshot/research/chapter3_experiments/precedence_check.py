"""Exact, standalone cumulative precedence rows for one finite DAG edge.

This module has no scheduling-model or solver integration. Each side must
eventually select exactly one of its options; this module neither creates
those one-hot constraints nor removes options. Option identifiers must be
unique across this one edge, including between its two sides. They are not
identities across scenes: a later integration must bind actual y variables.

For every distinct successor start t, the cumulative row is

    sum(y_j: start_j <= t) - sum(y_i: end_i <= t) <= 0.

With binary one-hot choices, a legal pair end_i <= start_j satisfies every
row. Conversely an illegal pair violates the row at its chosen start_j.
Equality therefore permits immediate succession, without a time grid.

The expected-time row sum(end_i*y_i) - sum(start_j*y_j) <= 0 is always kept.
Optional simplification uses only nonnegativity and one-hot sums: if every
predecessor option has ended by t, its prefix sum is 1 and the successor
prefix is at most 1. Such a row is redundant, also for fractional choices.
Identical coefficient rows may also be deduplicated within this edge only.
An empty predecessor prefix is not redundant: it requires the successor
prefix to be zero. Empty option domains remain empty; their contradictory
one-hot equations are a caller concern, not a reason here to remove rows.
"""
from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction


def _exact_time(value, field):
    """Accept explicit exact input, never silently rationalize a float."""
    if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
        raise ValueError(f'{field} must be an int, rational string, or Fraction')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f'{field} must be a finite exact rational') from exc


def _options(options, side, identifiers):
    normalized = []
    for number, option in enumerate(options):
        if not isinstance(option, Mapping):
            raise ValueError(f'{side} option {number} must be a mapping')
        missing = {'option_id', 'start', 'end'} - option.keys()
        if missing:
            raise ValueError(f'{side} option {number} lacks {sorted(missing)}')
        identifier = option['option_id']
        if not isinstance(identifier, str) or not identifier:
            raise ValueError('option_id must be a nonempty string')
        if identifier in identifiers:
            raise ValueError('option_id must be unique across the edge')
        identifiers.add(identifier)
        start = _exact_time(option['start'], f'{identifier}.start')
        end = _exact_time(option['end'], f'{identifier}.end')
        if end < start:
            raise ValueError(f'{identifier}.end must be >= start')
        item = deepcopy(dict(option))
        item.update(start=start, end=end)
        normalized.append(item)
    return tuple(normalized)


def _signature(row):
    return (tuple(sorted(row['coef'].items())), row['rhs'])


def build_precedence_system(predecessor_options, successor_options, *,
                            simplify=False):
    """Return the expected row and exact cumulative family for one edge.

    Each option is a mapping containing a nonempty string ``option_id`` and
    ``start``/``end`` as ints, rational strings, or Fractions. Floats and bools
    are rejected. Additional labels are copied but never used for pruning.
    Both time origin and unit are arbitrary; durations may be zero.

    Rows contain ``coef`` keyed by option_id, ``rhs`` (always Fraction(0)),
    ``sense``, ``kind``, and, for cumulative rows, an exact ``threshold``.
    ``raw_cumulative_rows`` always retains the full distinct-threshold family;
    ``cumulative_rows`` is the selected version, with an audit entry for every
    optional removal. Returned catalogs retain all input options in order.
    Neither caller input nor the raw rows share mutable objects with the
    selected rows or removal records.
    """
    if not isinstance(simplify, bool):
        raise ValueError('simplify must be a bool')
    identifiers = set()
    predecessor = _options(predecessor_options, 'predecessor', identifiers)
    successor = _options(successor_options, 'successor', identifiers)

    expected_coefficients = {o['option_id']: o['end'] for o in predecessor}
    expected_coefficients.update({o['option_id']: -o['start'] for o in successor})
    expected = {'kind': 'expected_time', 'coef': expected_coefficients,
                'sense': '<=', 'rhs': Fraction(0)}

    raw = []
    for threshold in sorted({o['start'] for o in successor}):
        coefficients = {o['option_id']: Fraction(-1) for o in predecessor
                        if o['end'] <= threshold}
        coefficients.update({o['option_id']: Fraction(1) for o in successor
                             if o['start'] <= threshold})
        raw.append({'kind': 'cumulative', 'threshold': threshold,
                    'coef': coefficients, 'sense': '<=', 'rhs': Fraction(0)})

    selected, removed, seen = [], [], {}
    for row in raw:
        threshold = row['threshold']
        if simplify and predecessor and all(o['end'] <= threshold
                                           for o in predecessor):
            removed.append({'row': deepcopy(row),
                'reason': 'predecessor_prefix_is_one',
                'proof': 'predecessor prefix = 1; successor prefix <= 1 '
                         'by nonnegativity and the two one-hot equations'})
            continue
        signature = _signature(row)
        if simplify and signature in seen:
            removed.append({'row': deepcopy(row),
                'reason': 'duplicate_coefficients',
                'kept_threshold': seen[signature]})
            continue
        seen[signature] = threshold
        selected.append(deepcopy(row))

    return {'expected_row': expected,
            'raw_cumulative_rows': raw,
            'cumulative_rows': selected,
            'removed_rows': removed,
            'predecessor_options': predecessor,
            'successor_options': successor,
            'domain_assumptions': {'nonnegative': True,
                'predecessor_sum': Fraction(1), 'successor_sum': Fraction(1),
                'integer_equivalence_requires_binary': True},
            'empty_option_sides': tuple(side for side, options in
                (('predecessor', predecessor), ('successor', successor))
                if not options),
            'simplified': simplify,
            'scope': 'one_edge_only'}
