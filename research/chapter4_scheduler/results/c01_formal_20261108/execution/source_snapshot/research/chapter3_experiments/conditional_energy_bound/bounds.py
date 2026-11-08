"""Conditional energy lower bounds, using only exact scalar algebra.

No schedule, thermal trajectory, model matrix or solver request is constructed.
The caller supplies the original full input and explicit partial restrictions.
This module is not imported by any production search entry point.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

PROTOCOL = 'conditional-electrothermal-energy-bound-v1'
_REFERENCE_TOKEN = object()


class BoundError(ValueError):
    """Unsupported/malformed contract; never a proof of original infeasibility."""


def _need(test, message):
    if not test:
        raise BoundError(message)


def _q(value):
    _need(not isinstance(value, bool) and isinstance(value, (str, int, F)),
          'Physical and comparison scalars must be exact strings/integers/Fractions')
    try:
        return F(value)
    except (ValueError, ZeroDivisionError) as error:
        raise BoundError('Invalid exact scalar') from error


def _canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _unique(rows, field):
    result = {}
    for row in rows:
        key = row[field]
        _need(isinstance(key, str) and key not in result, 'Duplicate/invalid identity')
        result[key] = row
    return result


def _topological(stages, edges):
    pred = {key: [] for key in stages}
    successors = {key: [] for key in stages}
    for edge in edges:
        _need(isinstance(edge, list) and len(edge) == 2 and
              all(key in stages for key in edge), 'Unknown dependency identity')
        a, b = edge
        _need(a != b and a not in pred[b], 'Repeated/self dependency')
        pred[b].append(a)
        successors[a].append(b)
    degree = {key: len(value) for key, value in pred.items()}
    ready = sorted(key for key, value in degree.items() if value == 0)
    order = []
    while ready:
        key = ready.pop(0)
        order.append(key)
        for child in successors[key]:
            degree[child] -= 1
            if degree[child] == 0:
                ready.append(child)
                ready.sort()
    _need(len(order) == len(stages), 'Dependencies must form a DAG')
    return tuple(order), pred


@dataclass(frozen=True)
class _Mode:
    unit: str
    domain: str
    opp: str
    frequency: F
    duration: F
    direct: F
    source: F
    increment: F
    capacity: F


@dataclass(frozen=True)
class _ArchivedUpperBound:
    input_sha256: str
    upper_J: F
    source: tuple
    token: object


class _BoundReceipt(dict):
    """Detect accidental edits/copies at the local decision interface.

    This is a software integrity contract, not a signature/security boundary.
    JSON evidence must be recomputed by the context before a pruning decision.
    """
    def __init__(self, value):
        super().__init__(value)
        self._seal = _canonical(value)


class BoundContext:
    """Prepared immutable-input coefficients; no condition-result/thermal cache."""

    def __init__(self, instance):
        try:
            self.input_sha256 = _canonical(instance)
            self.problem_id = instance['id']
            self._prepare(json.loads(json.dumps(instance, allow_nan=False)))
        except BoundError:
            raise
        except (KeyError, TypeError, IndexError, ZeroDivisionError, ValueError) as error:
            raise BoundError('Malformed/unsupported full input: '+str(error)) from error

    def _prepare(self, instance):
        _need(instance['schema_version'] == 'chapter3-input-v0.1', 'Unsupported schema')
        rules = instance['execution_rules']
        _need(all(rules[key] is False for key in ('preemption', 'migration', 'in_stage_opp_change')),
              'Unsupported execution rules')
        _need(rules['switch_only_when_domain_empty'] is True and
              rules['interval_convention'] == '[start,end)' and
              rules['idle_holds_last_opp'] is False and
              rules['idle_policy'] == 'auto_low_immediate_v1' and
              _q(rules['idle_delay_ms']) == 0, 'Explicit immediate auto-L required')
        _need(rules['shared_deployment_scope'] ==
              'same application Stage across all scenarios and request copies',
              'Original shared-deployment scope required')
        _need(rules['scenario_entry'] ==
              'independent; no inherited unfinished work or preceding-scenario temperature',
              'Independent scenario entries required')
        for key in ('extra_transfer_time_ms', 'extra_switch_time_ms', 'extra_handoff_time_ms',
                    'extra_transfer_energy_J', 'extra_switch_energy_J', 'extra_handoff_energy_J'):
            _need(_q(rules[key]) == 0, 'Only declared zero overheads supported')
        p = instance['platform']
        self.window = _q(instance['window_ms'])/1000
        _need(self.window > 0 and _q(instance['start_grid_ms']) > 0, 'Invalid window/start grid')
        nodes = tuple(p['node_order'])
        _need(nodes and len(nodes) == len(set(nodes)), 'Invalid node identities')
        self._units = _unique(p['units'], 'id')
        _need(set(u['thermal_node_id'] for u in self._units.values()) == set(nodes)
              and len(self._units) == len(nodes), 'One local node per execution unit required')
        self._domains = json.loads(json.dumps(p['domains']))
        _need(self._domains, 'Empty domains')
        C = tuple(map(_q, p['heat_capacity_J_per_K']))
        G = tuple(tuple(map(_q, row)) for row in p['conductance_W_per_K'])
        n = len(nodes)
        _need(len(C) == n and all(c > 0 for c in C) and len(G) == n and
              all(len(row) == n for row in G), 'Invalid physical dimensions')
        _need(all(G[i][i] > 0 and sum(G[i]) > 0 for i in range(n)) and
              all(G[i][j] == G[j][i] and (i == j or G[i][j] <= 0)
                  for i in range(n) for j in range(n)), 'Grounded passive conductance required')
        reference = _q(p['reference_temperature_degC'])
        ambient = _q(p['ambient_temperature_degC'])
        _need(reference == ambient, 'This bound requires equal reference/ambient temperature')
        valid = tuple(map(_q, p['power_model_temperature_range_degC']))
        _need(len(valid) == 2 and valid[0] <= ambient <= valid[1], 'Invalid physical range')
        external = _q(p['external_common_power_W'])
        _need(external >= 0 and len(p['external_common_heat_distribution']) == n and
              all(_q(x) == 0 for x in p['external_common_heat_distribution']),
              'External common power must not heat local nodes')
        base_heat, lam = [F(0)]*n, [F(0)]*n
        base_L, old_floor = external, external
        cpu_domains = []
        for domain_id, domain in self._domains.items():
            members = domain['unit_ids']
            _need(members and len(members) == len(set(members)) and all(
                u in self._units and self._units[u]['domain_id'] == domain_id and
                self._units[u]['power_group_id'] == domain_id for u in members), 'Domain membership')
            opps = domain['opps']
            _need('L' in opps and domain['entry_opp'] == 'L', 'L entry and low OPP required')
            ordered = sorted(opps, key=lambda k: _q(opps[k]['frequency_GHz']))
            _need(ordered[0] == 'L' and len({_q(opps[k]['frequency_GHz']) for k in opps}) == len(opps),
                  'Unique lowest-frequency L required')
            bases = [_q(domain['baseline_W'][k]) for k in ordered]
            slopes = [_q(domain['local_temperature_slope_W_per_K'][k]) for k in ordered]
            _need(bases[0] >= 0 and slopes[0] >= 0 and bases == sorted(bases)
                  and all(s >= slopes[0] for s in slopes), 'Nonnegative minimum-L coefficients required')
            _need(all(_q(opps[k]['voltage_V']) > 0 and _q(opps[k]['frequency_GHz']) > 0 for k in opps),
                  'Illegal working point')
            distribution = tuple(map(_q, domain['baseline_heat_distribution']))
            _need(len(distribution) == n and all(v >= 0 for v in distribution) and sum(distribution) == 1,
                  'Invalid baseline heat distribution')
            base_L += bases[0]
            old_floor += min(_q(domain['baseline_W'][k])+len(members)*
                            _q(domain['local_temperature_slope_W_per_K'][k])*(valid[0]-reference)
                            for k in opps)
            for i, share in enumerate(distribution):
                base_heat[i] += share*bases[0]
            for u in members:
                lam[nodes.index(self._units[u]['thermal_node_id'])] += slopes[0]
            is_cpu = all(self._units[u]['device_class'] == 'CPU' for u in members)
            if is_cpu:
                cpu_domains.append(domain_id)
            else:
                _need(len(members) == 1, 'Non-CPU domains must be single devices')
            domain['_ordered'] = tuple(ordered)
        _need(len(cpu_domains) <= 1 and all(
            u['domain_id'] in self._domains and uid in self._domains[u['domain_id']]['unit_ids']
            for uid, u in self._units.items()), 'One CPU domain and complete membership required')
        self._cpu = cpu_domains[0] if cpu_domains else None
        beta = max((sum(G[i])-lam[i])/C[i] for i in range(n))
        rho = min(base_heat[i]/C[i] for i in range(n))
        _need(beta > 0, 'Positive scalar damping required')
        poly_area = (self.window-beta*self.window**2/2+beta**2*self.window**3/6
                     -beta**3*self.window**4/24)
        _need(poly_area >= 0, 'Polynomial area outside supported range')
        self._scenes = _unique(instance['scenarios'], 'id')
        _need(self._scenes and sum(_q(s['weight']) for s in self._scenes.values()) == 1
              and all(_q(s['weight']) >= 0 for s in self._scenes.values()), 'Normalized nonnegative weights required')
        self._weights, self._stages, self._costs, self._topo, self._pred = {}, {}, {}, {}, {}
        self._background = F(0)
        self._old_background = old_floor*self.window
        occurrences = {}
        for sid, scene in self._scenes.items():
            weight = self._weights[sid] = _q(scene['weight'])
            entry = scene['entry']
            _need(entry['unfinished_work'] == [] and set(entry['domain_opp']) == set(self._domains)
                  and all(k == 'L' for k in entry['domain_opp'].values()), 'Empty L entry required')
            initial = tuple(map(_q, entry['temperature_degC']))
            _need(len(initial) == n and all(valid[0] <= t <= valid[1] for t in initial), 'Entry temperature')
            x0 = min(initial)-ambient
            _need(x0 >= rho/beta >= 0, 'Initial state outside scalar comparison contract')
            area = rho/beta*self.window+(x0-rho/beta)*poly_area
            self._background += weight*(base_L*self.window+sum(lam)*area)
            requests = _unique(scene['requests'], 'id')
            stages = self._stages[sid] = _unique(scene['stage_instances'], 'id')
            _need(requests and stages, 'Empty request/Stage set')
            for rid, request in requests.items():
                _need(0 <= _q(request['release_ms']) <= _q(request['deadline_ms']) <= self.window*1000,
                      'Invalid request release/deadline')
                ids = request['stage_instance_ids']
                _need(len(ids) == len(set(ids)) and set(ids) ==
                      {key for key, value in stages.items() if value['request_id'] == rid}, 'Request membership')
            self._topo[sid], self._pred[sid] = _topological(stages, scene['dependencies'])
            self._costs[sid] = {}
            limits = tuple(map(_q, scene['maximum_temperature_degC']))
            _need(len(limits) == n, 'Temperature limit dimensions')
            for key, stage in stages.items():
                _need(stage['request_id'] in requests, 'Unknown request')
                shared = stage['shared_stage_id']
                occurrences.setdefault(shared, []).append((sid, key))
                deadline = _q(requests[stage['request_id']]['deadline_ms'])/1000
                values, identities = [], set()
                for mode in instance['stage_modes'][shared]:
                    uid, opp = mode['unit_id'], mode['opp_id']
                    _need(uid in self._units, 'Unknown mode unit')
                    unit = self._units[uid]
                    did = unit['domain_id']
                    domain = self._domains[did]
                    _need(opp in domain['opps'] and (uid, opp) not in identities, 'Unknown/duplicate mode')
                    identities.add((uid, opp))
                    _need(mode['shared_stage_id'] == shared and mode['domain_id'] == did and
                          mode['power_group_id'] == did and mode['thermal_node_id'] == unit['thermal_node_id'],
                          'Mode source/meter mismatch')
                    for field in ('frequency_GHz', 'voltage_V'):
                        _need(_q(mode[field]) == _q(domain['opps'][opp][field]), 'Mode OPP mismatch')
                    duration, q = _q(mode['duration_ms'])/1000, _q(mode['activity_power_W'])
                    _need(duration > 0 and q >= 0, 'Invalid mode time/activity')
                    k = nodes.index(unit['thermal_node_id'])
                    damping = (G[k][k]-lam[k])/C[k]
                    _need(damping > 0, 'Own-node source damping must be positive')
                    h = self.window-deadline
                    eta = max(F(0), lam[k]/C[k]*(h-damping*h*h/2))
                    direct = q*duration
                    increment = (_q(domain['baseline_W'][opp])-_q(domain['baseline_W']['L']))*duration
                    values.append(_Mode(uid, did, opp, _q(mode['frequency_GHz']), duration,
                                        direct, direct*(1+eta), increment, increment/len(domain['unit_ids'])))
                _need(values, 'No original legal modes')
                self._costs[sid][key] = tuple(values)
        self.shared_ids = tuple(sorted(key for key, copies in occurrences.items() if len(copies) > 1))
        self.parameters = {'beta_per_s': str(beta), 'rho_K_per_s': str(rho),
                           'background_lower_bound_J': str(self._background),
                           'old_background_lower_bound_J': str(self._old_background),
                           'window_s': str(self.window)}

    def _allowed(self, partial):
        partial = {} if partial is None else partial
        _need(isinstance(partial, dict) and set(partial) <= {'shared_units', 'by_scene'}, 'Unknown partial field')
        shared, by_scene = partial.get('shared_units', {}), partial.get('by_scene', {})
        _need(isinstance(shared, dict) and isinstance(by_scene, dict), 'Restriction maps required')
        forced = dict(shared)
        for key, uid in shared.items():
            _need(key in self.shared_ids and isinstance(uid, str) and uid in self._units,
                  'Unknown shared identity or unit')
        for sid, restrictions in by_scene.items():
            _need(sid in self._scenes and isinstance(restrictions, dict), 'Unknown scene/restriction map')
            for key, value in restrictions.items():
                _need(key in self._stages[sid] and isinstance(value, dict) and set(value) <= {'unit', 'opp'},
                      'Unknown Stage/partial mode field')
                _need(all(isinstance(v, str) for v in value.values()), 'Unit/OPP labels must be strings')
                if 'unit' in value:
                    _need(value['unit'] in self._units, 'Unknown unit')
                    identity = self._stages[sid][key]['shared_stage_id']
                    if identity in self.shared_ids:
                        _need(identity not in forced or forced[identity] == value['unit'],
                              'Contradictory shared units; no bound produced')
                        forced[identity] = value['unit']
        allowed = {}
        for sid, stages in self._stages.items():
            allowed[sid] = {}
            for key, stage in stages.items():
                rule = by_scene.get(sid, {}).get(key, {})
                uid = forced.get(stage['shared_stage_id'], rule.get('unit'))
                values = tuple(m for m in self._costs[sid][key]
                               if (uid is None or m.unit == uid) and
                                  ('opp' not in rule or m.opp == rule['opp']))
                _need(values, 'Restriction leaves no legal modes; not an original infeasibility certificate')
                allowed[sid][key] = values
        for shared_id in self.shared_ids:
            copies = [(sid, key) for sid in allowed for key in allowed[sid]
                      if self._stages[sid][key]['shared_stage_id'] == shared_id]
            common = set.intersection(*({m.unit for m in allowed[sid][key]} for sid, key in copies))
            _need(common, 'No common shared unit; no numeric bound produced')
            for sid, key in copies:
                allowed[sid][key] = tuple(m for m in allowed[sid][key] if m.unit in common)
        return allowed, _canonical(partial)

    def _minimum(self, allowed, cost):
        total, grouped = F(0), {}
        for sid, stages in self._stages.items():
            for key, stage in stages.items():
                identity = stage['shared_stage_id']
                if identity in self.shared_ids:
                    grouped.setdefault(identity, []).append((sid, key))
                else:
                    total += self._weights[sid]*min(cost(m) for m in allowed[sid][key])
        for copies in grouped.values():
            units = set.intersection(*({m.unit for m in allowed[sid][key]} for sid, key in copies))
            total += min(sum(self._weights[sid]*min(cost(m) for m in allowed[sid][key] if m.unit == unit)
                             for sid, key in copies) for unit in units)
        return total

    def _forced_cpu(self, allowed):
        if self._cpu is None:
            return F(0), {}
        domain = self._domains[self._cpu]
        members = domain['unit_ids']
        total, details = F(0), {}
        for sid, stages in self._stages.items():
            value, rows = F(0), []
            previous = 'L'
            for threshold in domain['_ordered'][1:]:
                frequency = _q(domain['opps'][threshold]['frequency_GHz'])
                delta = _q(domain['baseline_W'][threshold])-_q(domain['baseline_W'][previous])
                forced = {key: min(m.duration for m in modes) for key, modes in allowed[sid].items()
                          if all(m.domain == self._cpu and m.frequency >= frequency for m in modes)}
                unit_load = {u: sum((d for key, d in forced.items()
                                    if {m.unit for m in allowed[sid][key]} == {u}), F(0)) for u in members}
                path = {}
                for key in self._topo[sid]:
                    path[key] = forced.get(key, F(0))+max((path[p] for p in self._pred[sid][key]), default=F(0))
                capacity = sum(forced.values(), F(0))/len(members)
                critical = max(path.values(), default=F(0))
                length = max([capacity, critical, *unit_load.values()])
                value += delta*length
                rows.append({'threshold': threshold, 'forced_stage_ids': sorted(forced),
                             'minimum_durations_s': {k: str(v) for k, v in forced.items()},
                             'unit_load_s': {k: str(v) for k, v in unit_load.items()},
                             'capacity_s': str(capacity), 'DAG_chain_s': str(critical),
                             'residency_lower_s': str(length), 'increment_W': str(delta)})
                previous = threshold
            total += self._weights[sid]*value
            details[sid] = {'weighted_by': str(self._weights[sid]),
                            'CPU_baseline_increment_lower_J': str(value), 'thresholds': rows}
        return total, details

    def bound(self, partial=None):
        """Lower-bound all safe completions of exactly the declared partial domain."""
        allowed, condition_sha = self._allowed(partial)
        legacy = self._old_background+self._minimum(allowed, lambda m: m.direct)
        capacity = self._background+self._minimum(allowed, lambda m: m.source+m.capacity)
        cpu, details = self._forced_cpu(allowed)
        forced = self._background+self._minimum(allowed, lambda m:
                    m.source+(m.increment if m.domain != self._cpu else F(0)))+cpu
        return _BoundReceipt({'protocol': PROTOCOL, 'status': 'BOUND', 'problem_id': self.problem_id,
                'input_sha256': self.input_sha256, 'condition_sha256': condition_sha,
                'lower_bound_J': str(max(legacy, capacity, forced)),
                'legacy_conditioned_lower_bound_J': str(legacy),
                'capacity_lower_bound_J': str(capacity),
                'forced_residency_lower_bound_J': str(forced),
                'background_lower_bound_J': str(self._background),
                'components': {'forced_CPU': details, 'forced_CPU_weighted_J': str(cpu)},
                'bound_scope': 'all_safe_completions_of_declared_partial_assignment',
                'is_global_root_bound': not partial, 'solver_reported': False,
                'new_safe_upper_bound': False, 'production_search_enabled': False})

    def reference_from_archive(self, result_path, postcheck_path):
        """Admit an existing P0 safe U by read-only archive identity checks.

        This trusts the previously audited continuous certificate and checks its
        identity; it does not re-evaluate safety or authorize a new execution.
        """
        try:
            result_path, postcheck_path = Path(result_path).resolve(), Path(postcheck_path).resolve()
            repo = Path(__file__).resolve().parents[3]
            relative = result_path.relative_to(repo).as_posix()
            _need(any(relative.startswith('research/chapter3_experiments/results/'+g+'/calls/')
                      for g in ('p0_execution01', 'p0_resume01')), 'Only original P0 archives admitted')
            _need(result_path.name == 'result.json' and postcheck_path.name == 'postcheck.json'
                  and postcheck_path.parent == result_path.parent, 'Mismatched archive paths')
            paths = [result_path, postcheck_path, result_path.parent/'input_instance.json',
                     result_path.parent/'wrapper_raw_result.json']
            blobs = [p.read_bytes() for p in paths]
            result, post, instance, raw = [json.loads(b.decode('utf-8-sig')) for b in blobs]
            _need(_canonical(instance) == self.input_sha256, 'Archived input mismatch')
            _need(_canonical(result) == _canonical(raw), 'Result differs from its original wrapper receipt')
            _need(F(str(result['timing']['limit_s'])) == F(str(raw['timing']['limit_s'])) == 300,
                  'Original 300-second method budget identity required')
            _need(result['problem_id'] == post['problem_id'] == self.problem_id and
                  result['state'] == post['state'] == 'SAFE' and post['rankable_energy'] is True,
                  'Complete SAFE archive required')
            _need(result['control_policy'] == 'auto_low_immediate_v1' and
                  isinstance(post['control_policy'], dict) and
                  post['control_policy'].get('idle_policy') == 'auto_low_immediate_v1' and
                  _q(post['control_policy']['idle_delay_ms']) == 0,
                  'Archive control policy mismatch')
            upper = _q(result['safe_upper_bound_J'])
            candidate = result['safe_candidate']
            candidate_sha = _canonical(candidate)
            _need(upper >= 0 and raw['safe_candidate'] == candidate and
                  _q(raw['safe_upper_bound_J']) == upper and _q(post['safe_upper_bound_J']) == upper,
                  'Archive safe candidate/U mismatch')
            identity, provenance = post['evidence_identity'], post['post_provenance']
            _need(identity['input_sha256'] == provenance['input_sha256'] == self.input_sha256
                  and identity['candidate_sha256'] == provenance['candidate_sha256'] == candidate_sha
                  and provenance['raw_result_sha256'] == hashlib.sha256(blobs[3]).hexdigest()
                  and provenance['new_U'] is False and provenance['no_search_or_repair'] is True,
                  'Post certificate provenance mismatch')
            _need(set(post['scenes']) == set(self._scenes) == set(candidate['scenes']), 'Incomplete scene coverage')
            for sid, scene in post['scenes'].items():
                _need(scene['state'] == 'SAFE' and scene['complete'] is True and
                      scene['rankable_energy'] is True and _q(scene['covered_until_s']) == self.window,
                      'Incomplete continuous archived certificate')
            snapshot = result.get('committed_safe_snapshot')
            if snapshot:
                _need(snapshot['safe_candidate'] == candidate and _q(snapshot['safe_upper_bound_J']) == upper,
                      'Committed SAFE snapshot mismatch')
                formed = F(str(snapshot['committed_at_s']))
            else:
                evaluation = result['evaluation']
                _need(evaluation['state'] == 'SAFE' and evaluation['evidence_identity'] == identity
                      and _q(evaluation['safe_upper_bound_J']) == upper, 'Original evaluation mismatch')
                formed = F(str(evaluation['completed_at_elapsed_s']))
            _need(0 <= formed < 300, 'No in-budget archived SAFE formation')
            source = tuple((str(path), hashlib.sha256(data).hexdigest()) for path, data in zip(paths, blobs))
            return _ArchivedUpperBound(self.input_sha256, upper, source, _REFERENCE_TOKEN)
        except BoundError:
            raise
        except (ValueError, KeyError, OSError, TypeError) as error:
            raise BoundError('Incomplete/invalid archived SAFE evidence: '+str(error)) from error


def prepare(instance):
    return BoundContext(instance)


def compare_exact_bound(bound, upper_J, input_sha256):
    """Arithmetic comparison only; callers cannot use it as safety admission."""
    _need(isinstance(bound, dict) and bound.get('protocol') == PROTOCOL and
          bound.get('status') == 'BOUND' and bound.get('input_sha256') == input_sha256,
          'Bound/input identity mismatch')
    lower, upper = _q(bound['lower_bound_J']), _q(upper_J)
    _need(upper >= 0, 'Negative upper bound')
    difference = lower-upper
    return {'comparison': 'HIGHER' if difference > 0 else 'TIE' if difference == 0 else 'LOWER',
            'difference_J': str(difference), 'pruning_authorized': False}


def pruning_decision(bound, reference=None):
    _need(isinstance(bound, _BoundReceipt) and bound._seal == _canonical(dict(bound))
          and bound.get('protocol') == PROTOCOL and bound.get('status') == 'BOUND',
          'A completed bound receipt is required')
    result = {'prune': False, 'decision': 'NO_CERTIFIED_UPPER_BOUND',
              'condition_sha256': bound['condition_sha256'], 'original_domain_infeasible': False,
              'posthoc': True, 'production_search_enabled': False}
    if reference is None:
        return result
    _need(isinstance(reference, _ArchivedUpperBound) and reference.token is _REFERENCE_TOKEN,
          'Reference must come from complete original archive admission')
    comparison = compare_exact_bound(bound, reference.upper_J, reference.input_sha256)
    result['decision'] = {'HIGHER': 'PRUNE_ENERGY', 'TIE': 'KEEP_TIE', 'LOWER': 'KEEP'}[comparison['comparison']]
    result['prune'] = comparison['comparison'] == 'HIGHER'
    result['difference_J'] = comparison['difference_J']
    result['archived_upper_bound_J'] = str(reference.upper_J)
    return result
