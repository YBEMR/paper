"""Exact, optional finite start domains shared by planning and evaluation.

An absent declaration preserves the full declared start grid.  A declaration
restricts starts only; it neither changes durations nor validates a schedule.
Empty Stage sets are legitimate empty domains, never a request to fall back to
the full grid.  Legacy fixture-only ``starts`` arguments remain separate.
"""

from fractions import Fraction


def _exact(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise TypeError("Start-domain scalar must be a string, integer or Fraction")
    return Fraction(value)


def explicit_start_sets(instance, budget=None):
    """Return None, or complete scene/Stage maps of sorted exact starts.

    All identities and fields are checked before returning.  Every value must
    lie on the existing grid and in [0, window].  Arrival, duration, deadline
    and resource conditions remain the responsibility of the option builder
    and independent complete-schedule checker.
    """
    if budget is not None:
        budget.check()
    if 'start_domain' not in instance:
        return None
    declaration = instance['start_domain']
    if not isinstance(declaration, dict) or set(declaration) != {
        'version', 'kind', 'by_scene_stage_ms'
    }:
        raise ValueError("Start-domain fields must be version/kind/by_scene_stage_ms")
    if type(declaration['version']) is not int or declaration['version'] != 1:
        raise ValueError("Unsupported start-domain version")
    if declaration['kind'] != 'explicit_grid_subset':
        raise ValueError("Unsupported start-domain kind")
    grid, window = _exact(instance['start_grid_ms']), _exact(instance['window_ms'])
    if grid <= 0 or window <= 0:
        raise ValueError("Start-domain grid and window must be positive")
    expected = {}
    for scene in instance['scenarios']:
        if budget is not None:
            budget.check()
        scene_id = scene['id']
        if not isinstance(scene_id, str) or scene_id in expected:
            raise ValueError("Invalid or duplicate start-domain scene identity")
        stage_ids = [stage['id'] for stage in scene['stage_instances']]
        if (any(not isinstance(stage_id, str) for stage_id in stage_ids) or
                len(stage_ids) != len(set(stage_ids))):
            raise ValueError("Invalid or duplicate start-domain Stage identity")
        expected[scene_id] = set(stage_ids)
    supplied = declaration['by_scene_stage_ms']
    if not isinstance(supplied, dict) or set(supplied) != set(expected):
        raise ValueError("Start domain must cover exactly all declared scenarios")
    result = {}
    for scene_id, stage_ids in expected.items():
        if budget is not None:
            budget.check()
        by_stage = supplied[scene_id]
        if not isinstance(by_stage, dict) or set(by_stage) != stage_ids:
            raise ValueError("Start domain must cover exactly all declared Stage instances")
        result[scene_id] = {}
        for stage_id in sorted(stage_ids):
            if budget is not None:
                budget.check()
            values = by_stage[stage_id]
            if not isinstance(values, list):
                raise TypeError("Each declared Stage start set must be a list")
            exact = []
            for value in values:
                if budget is not None:
                    budget.check()
                value = _exact(value)
                if value < 0 or value > window or (value / grid).denominator != 1:
                    raise ValueError("Declared start lies outside the grid/window")
                exact.append(value)
            if len(exact) != len(set(exact)):
                raise ValueError("Duplicate declared start")
            result[scene_id][stage_id] = sorted(exact)
    if budget is not None:
        budget.check()
    return result
