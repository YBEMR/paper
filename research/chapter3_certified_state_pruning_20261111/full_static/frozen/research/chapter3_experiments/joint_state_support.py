"""Fail-closed joint-state support certificates over exported structural rows.

Only auto-L callers may use this module. It proves necessity for exact integer
option choices in the binary64-exported inequalities, never LP-point equality
or robustness of an arbitrary solver's tolerance tube. Unknown/capped states
remain. It does not change options, events, bounds or physical coefficients.
"""
from collections import Counter
from fractions import Fraction as F
from itertools import combinations, product
import hashlib
import json
import math
import time

PROTOCOL = 'exported-row-joint-state-support-v1'
MAX_GROUP_PRODUCT = 4096
MAX_TOTAL_GROUP_PRODUCT = 2000000


def _f(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Joint-state certificate requires finite binary64 values')
        return F.from_float(value)
    return F(value)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    default=str).encode()).hexdigest()


class SceneSupport:
    """Exact one-hot groups and actual exported dependency inequalities."""
    def __init__(self, scene, stage_options, stage_onehot_rows, dependency_rows,
                 rows, integer_indices, variable_bounds, budget=None):
        began = time.monotonic()
        self.scene = scene
        self.budget = budget
        self.groups = {stage: tuple(y for _, y in choices)
                       for stage, choices in stage_options.items()}
        self.option_by_y = {y: option for choices in stage_options.values()
                            for option, y in choices}
        self.onehot = {}
        integers = frozenset(integer_indices)
        for stage, group in self.groups.items():
            self.check()
            if any(y not in integers or tuple(variable_bounds[y]) != (F(0), F(1)) for y in group):
                raise ValueError('Joint-state support requires original binary option variables')
            pair = stage_onehot_rows[stage]
            if len(pair) != 2:
                raise ValueError('Missing exact Stage one-hot row pair')
            for row_index, sign in zip(pair, (1, -1)):
                row = rows[row_index]
                if row['coef'] != {y: float(sign) for y in group} or _f(row['rhs']) != sign:
                    raise ValueError('Stage one-hot rows are not exact')
            self.onehot[stage] = dict(row_indices=list(pair), option_variables=list(group),
                                     rows_sha256=_digest([rows[i] for i in pair]))
        self.exported_edges = {}
        for edge, index in dependency_rows.items():
            row = rows[index]
            if set(row['coef']) - set(self.option_by_y):
                raise ValueError('Dependency certificate row has non-option columns')
            self.exported_edges[edge] = dict(index=index,
                coef={y: _f(a) for y, a in row['coef'].items()}, rhs=_f(row['rhs']),
                sha256=_digest(row))
        self.paths = {}
        successors = {stage: [] for stage in self.groups}
        for before, after in scene['dependencies']:
            successors[before].append(after)
        for first in successors:
            todo = [(first, [first])]; seen = {first}
            for at, path in todo:
                for last in successors[at]:
                    if last not in seen:
                        seen.add(last); todo.append((last, path+[last]))
                        self.paths[first, last] = path+[last]
        self.pair_cache = {}
        self.products_charged = 0
        self.report = dict(protocol=PROTOCOL, scene=scene['id'],
            stage_onehot=self.onehot, certificate_catalogue={}, interval_reports=[],
            preparation_elapsed_s=time.monotonic()-began,
            proof_scope='Exact exported rows with original integer y; not LP projection equality or solver tolerance-tube equality')

    def check(self):
        if self.budget is not None: self.budget.check()

    def obstruction(self, left, right):
        """Return a certificate ID, or None when the pair is not proved bad."""
        key = (tuple(left['variables']), tuple(right['variables']))
        if key in self.pair_cache: return self.pair_cache[key]
        self.check()
        if left['stage'] == right['stage']:
            # Witnesses belong to different non-L domains; distinct y choices
            # in the same exact one-hot Stage cannot both be selected.
            if set(left['variables']) & set(right['variables']):
                self.pair_cache[key] = None; return None
            proof = dict(rule='exact_stage_unique', stage=left['stage'],
                left_variables=left['variables'], right_variables=right['variables'],
                **self.onehot[left['stage']])
        else:
            if (left['stage'], right['stage']) in self.paths:
                path = self.paths[left['stage'], right['stage']]
            elif (right['stage'], left['stage']) in self.paths:
                path = self.paths[right['stage'], left['stage']]
            else:
                self.pair_cache[key] = None; return None
            edges = [self.exported_edges[a, b] for a, b in zip(path, path[1:])]
            coef = {}
            for row in edges:
                for y, value in row['coef'].items(): coef[y] = coef.get(y, F(0))+value
            restrictions = {left['stage']: tuple(left['variables']),
                            right['stage']: tuple(right['variables'])}
            minima = []
            for stage, full in self.groups.items():
                choices = restrictions.get(stage, full)
                if not choices:
                    self.pair_cache[key] = None; return None
                lower = min(coef.get(y, F(0)) for y in choices)
                minima.append(dict(stage=stage, option_variables=list(choices),
                                   coefficient_minimum=str(lower)))
            lhs_min = sum((F(row['coefficient_minimum']) for row in minima), F(0))
            rhs = sum((row['rhs'] for row in edges), F(0))
            margin = lhs_min-rhs
            if margin <= 0:
                self.pair_cache[key] = None; return None
            proof = dict(rule='exported_dependency_path', path=path,
                row_indices=[r['index'] for r in edges], row_sha256=[r['sha256'] for r in edges],
                stage_minima=minima, summed_rhs=str(rhs), minimum_lhs=str(lhs_min),
                strict_margin=str(margin), tolerance_reference_per_row='1/1000000000',
                exceeds_path_row_tolerance=margin > len(edges)*F(1, 1000000000))
        proof_id = _digest(proof)
        self.report['certificate_catalogue'][proof_id] = proof
        self.pair_cache[key] = proof_id
        return proof_id


def filter_interval(context, active, domain_order, states, interval,
                    cap=MAX_GROUP_PRODUCT, total_cap=MAX_TOTAL_GROUP_PRODUCT):
    """Retain every state without exhaustive exported-row support rejection."""
    began = time.monotonic()
    if type(cap) is not int or cap < 0 or type(total_cap) is not int or total_cap < 0:
        raise ValueError('Joint-state support caps must be nonnegative integers')
    support = {domain: {} for domain in domain_order}
    for option, y in active:
        domain, opp = option['domain_id'], option['opp_id']
        key = (option['stage_instance_id'], option['unit_id'])
        support[domain].setdefault(opp, {}).setdefault(key, []).append(y)
    choices_by_domain = {domain: {opp: [dict(stage=stage, unit=unit, variables=variables)
        for (stage, unit), variables in sorted(groups.items())] for opp, groups in opps.items()}
        for domain, opps in support.items()}
    retained, records = [], []
    for state in states:
        context.check()
        choices = [choices_by_domain[d].get(opp, [])
                   for d, opp in zip(domain_order, state) if opp != 'L']
        size = math.prod(map(len, choices))
        if size > cap or context.products_charged+size > total_cap:
            retained.append(state)
            records.append(dict(state=list(state), status='UNKNOWN_CAP', support_product=size))
            continue
        context.products_charged += size
        rejected = []
        for witnesses in product(*choices):
            context.check()
            proof_id = None
            for first, last in combinations(witnesses, 2):
                proof_id = context.obstruction(first, last)
                if proof_id is not None: break
            if proof_id is None:
                retained.append(state)
                records.append(dict(state=list(state), status='UNKNOWN_NOT_PROVED',
                    support_product=size, unblocked_witness_variables=[w['variables'] for w in witnesses]))
                break
            rejected.append(dict(witness_variables=[w['variables'] for w in witnesses],
                                 certificate_id=proof_id))
        else:
            # The empty product for L/L/L has one empty witness, hence is kept.
            records.append(dict(state=list(state), status='PROVED_UNREACHABLE',
                support_product=size, exhaustive_rejections=rejected))
    report = dict(interval=interval, domain_order=list(domain_order), candidate_count=len(states),
        retained_count=len(retained), deleted_count=len(states)-len(retained),
        status_counts=dict(Counter(r['status'] for r in records)), states=records,
        elapsed_s=time.monotonic()-began)
    context.report['interval_reports'].append(report)
    return retained, report


def verify_gate_off_rows(rows, lower_bounds, upper_bounds, gate):
    """Exact-rational box audit of actual binary64 rows with gate fixed to 0.

    No tolerance is subtracted from a violation. A nonredundant row raises,
    so a caller cannot return an unchecked pruned physical model.
    """
    residuals = []
    for position, row in enumerate(rows):
        maximum = F(0)
        for index, coefficient in row['coef'].items():
            if index == gate: continue
            value = _f(coefficient)
            maximum += value*_f(upper_bounds[index] if value >= 0 else lower_bounds[index])
        residual = maximum-_f(row['rhs'])
        if residual > 0:
            raise ValueError('Deleted-state gate-off row is not redundant: row='+str(position)+
                             ', exact_residual='+str(residual))
        residuals.append(residual)
    return dict(checked_rows=len(rows), gate_fixed_value=0,
                maximum_residual=str(max(residuals, default=F(0))),
                minimum_slack=str(-max(residuals, default=F(0))), exact_binary64_box=True)
