"""K195 pure admission of already-read R2023b ready/request/response records.

No file access, MATLAB startup, solver invocation or thermal evaluation occurs
here.  Native option identity is an interface check, not an optimality proof.
"""
import math


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def positive_finite(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool),
            label + ' must be a real JSON number')
    require(math.isfinite(value) and value > 0, label + ' must be positive and finite')
    return value


def _same_json_value(actual, expected):
    # jsonencode represents MATLAB Inf as JSON null: keep that original
    # representation, rather than substituting an arbitrary finite bound.
    if expected is None:
        return actual is None
    if isinstance(expected, bool):
        return type(actual) is bool and actual is expected
    if isinstance(expected, (int, float)):
        return (isinstance(actual, (int, float)) and not isinstance(actual, bool)
                and math.isfinite(actual) and actual == expected)
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _same_json_value(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and set(actual) == set(expected) and all(
            _same_json_value(actual[key], value) for key, value in expected.items())
    return type(actual) is type(expected) and actual == expected


def validate_ready(ready):
    require(isinstance(ready, dict), 'Native ready record must be an object')
    require(ready.get('status') == 'READY', 'Native worker is not READY')
    require(ready.get('release') == '2023b', 'Native release differs from original R2023b')
    require(ready.get('license_checkout') is True,
            'Optimization Toolbox checkout was not successful')
    require(_same_json_value(ready.get('license_test'), 1),
            'Optimization Toolbox license test was not successful')
    require(isinstance(ready.get('intlinprog_path'), str) and
            bool(ready['intlinprog_path'].strip()), 'Original intlinprog is unavailable')
    return {'passed': True, 'errors': [], 'state': 'NATIVE_READY_IDENTITY_PASS',
            'release': ready['release'], 'license_checkout': True,
            'scope': 'already-read worker identity only; no native launch'}


def validate_request_response(request, response, options_reference, *,
                              cut_max_iterations=10, solver_max_time_s=None,
                              method_seconds=300):
    """Match original options and budget allocation; inspect supplied objects.

    ``options_reference`` is the unchanged K193
    whole_proposal.native_options_reference.options_except_MaxTime object.
    ``response`` may be a normal solved or budget-ended response with recorded
    options; a missing options object is not silently certified.
    """
    require(isinstance(request, dict) and isinstance(response, dict)
            and isinstance(options_reference, dict), 'Native records/reference must be objects')
    require(method_seconds == 300 and not isinstance(method_seconds, bool),
            'Frozen method budget must remain 300 seconds')
    require(cut_max_iterations == 10 and not isinstance(cut_max_iterations, bool),
            'Frozen bridge cut iteration limit must remain 10')
    require(solver_max_time_s is None, 'An artificial native-only solver cap is forbidden')
    for record in (request, response):
        require(not any(key.startswith('solver_max_time_s') for key in record),
                'Native-only solver MaxTime cap appeared in evidence')
    remaining = positive_finite(request.get('remaining_s'), 'request.remaining_s')
    require(remaining <= method_seconds, 'Request exceeds the 300-second method budget')
    require(_same_json_value(request.get('cut_max_iterations'), 10),
            'Request CutMaxIterations differs from original 10')
    for key in ('cut_max_iterations_declared', 'cut_max_iterations_actual_effective'):
        require(_same_json_value(response.get(key), 10),
                'Native CutMaxIterations identity missing/drifted: ' + key)
    options = response.get('options')
    require(isinstance(options, dict), 'Native option readback is missing')
    require('MaxTime' not in options_reference, 'Reference must exclude only MaxTime')
    require(set(options) == set(options_reference) | {'MaxTime'},
            'Native option inventory differs from original reference')
    mismatches = [name for name, expected in options_reference.items()
                  if not _same_json_value(options[name], expected)]
    require(not mismatches, 'Native option value drift: ' + ', '.join(mismatches))
    allocated = positive_finite(options.get('MaxTime'), 'options.MaxTime')
    require(allocated <= remaining and allocated <= method_seconds,
            'Native MaxTime exceeds request remaining time or method root')
    return {'passed': True, 'errors': [], 'state': 'NATIVE_OPTIONS_BUDGET_PASS',
            'matching_options_except_MaxTime': len(options_reference),
            'MaxTime': allocated, 'request_remaining_s': remaining,
            'cut_max_iterations': 10, 'native_only_solver_cap': None,
            'scope': 'readback identity and allocation only; not solver success or certification'}
