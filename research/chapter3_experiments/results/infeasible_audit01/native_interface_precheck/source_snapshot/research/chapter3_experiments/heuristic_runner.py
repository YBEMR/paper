"""One deadline, complete continuous receipts, isolated baseline invocation."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

from q1_case import independent_lower_bound
from schedules import validate_schedule
from thermal import Exhausted, evaluate_candidate
from timing import MethodBudget


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


class CandidateRecorder:
    def __init__(self, instance, accuracy, budget, *, evaluator=evaluate_candidate):
        self.instance, self.accuracy, self.budget = instance, accuracy, budget
        self.evaluator = evaluator
        self.cache = {}
        self.evaluations, self.events, self.violations = [], [], []
        self.first_candidate_s = self.first_legal_s = self.first_safe_s = None
        self.best = None
        self.candidates = self.cache_hits = 0

    def assess(self, candidate, source):
        self.budget.check()
        at = self.budget.elapsed
        self.candidates += 1
        if self.first_candidate_s is None: self.first_candidate_s = at
        with self.budget.phase('decode_and_legality'):
            legality = validate_schedule(self.instance, candidate)
        self.budget.check()
        if legality.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED' and self.first_legal_s is None:
            self.first_legal_s = self.budget.elapsed
        identity = canonical_hash(candidate)
        if identity in self.cache:
            self.budget.check()
            self.cache_hits += 1
            return deepcopy(self.cache[identity])
        if legality.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED':
            with self.budget.phase('continuous_thermal_energy_evaluation'):
                receipt = self.evaluator(self.instance, candidate, self.accuracy, self.budget)
        else:
            receipt = {'state': 'INVALID_SCHEDULE', 'rankable_energy': False,
                'reason': legality.get('reason'), 'legality': legality, 'violations': [],
                'weighted_energy_J': None, 'safe_upper_bound_J': None}
        # Preserve previously formed evidence before any outer deadline check.
        witnessed = [v for v in receipt.get('violations', [])
            if isinstance(v.get('formed_at_elapsed_s'), (int, float))
            and not isinstance(v.get('formed_at_elapsed_s'), bool)
            and 0 <= v['formed_at_elapsed_s'] < self.budget.seconds]
        self.violations.extend(deepcopy(witnessed))
        formed = receipt.get('completed_at_elapsed_s')
        timely = isinstance(formed, (int, float)) and not isinstance(formed, bool) and 0 <= formed < self.budget.seconds
        energy = receipt.get('weighted_energy_J')
        safe = bool(receipt.get('state') == 'SAFE' and receipt.get('rankable_energy')
                    and timely and energy and F(energy[0]) <= F(energy[1])
                    and receipt.get('safe_upper_bound_J') is not None
                    and F(receipt['safe_upper_bound_J']) == F(energy[1]))
        row = {'source': source, 'candidate': deepcopy(candidate), 'candidate_sha256': identity,
            'evaluation': deepcopy(receipt), 'returned_at_s': self.budget.elapsed, 'accepted_safe': safe}
        self.evaluations.append(row)
        if safe:
            if self.first_safe_s is None: self.first_safe_s = formed
            if self.best is None or F(receipt['safe_upper_bound_J']) < F(self.best['evaluation']['safe_upper_bound_J']):
                self.best = row
                self.events.append({'event': 'safe_upper_bound', 'at_s': formed,
                    'source': source, 'safe_upper_bound_J': receipt['safe_upper_bound_J'],
                    'candidate_sha256': identity})
        if safe or witnessed:
            # The cache object itself is local to this instance/accuracy/Budget.
            self.cache[identity] = deepcopy(receipt)
        self.budget.check()
        if receipt.get('state') == 'SAFE' and not safe:
            # Archive raw evidence above, but never feed an unaccepted objective
            # into HEFT's descent or SA's acceptance state.
            receipt = deepcopy(receipt)
            receipt.update(state='UNRESOLVED', reason='SAFE_RECEIPT_NOT_ACCEPTED_WITHIN_BUDGET',
                rankable_energy=False, weighted_energy_J=None, safe_upper_bound_J=None)
        return receipt


def execute_heuristic(input_loader, workdir, *, method, seconds, seed=None,
                       clock=time.monotonic, evaluator=evaluate_candidate, search=None):
    """No research workload or budget is selected by this reusable lifecycle."""
    if method not in ('heft', 'sa'): raise ValueError('unknown heuristic')
    if method == 'sa' and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError('SA requires an explicit integer seed')
    if method == 'heft' and seed is not None: raise ValueError('HEFT is deterministic')
    budget = MethodBudget(seconds, clock=clock)
    workdir = Path(workdir)
    if workdir.exists(): raise FileExistsError(str(workdir))
    workdir.mkdir(parents=True)
    result = {'method': method, 'seed': seed, 'state': 'UNRESOLVED', 'reason': None,
        'safe_candidate': None, 'safe_upper_bound_J': None, 'evaluation': None,
        'independently_proven_optimal': False, 'independently_proven_infeasible': False,
        'coverage_complete': False, 'remaining_domain': 'HEURISTIC_DECODER_COVERAGE_NOT_CERTIFIED',
        'candidate_and_cache_shared_between_calls': False, 'solver_reported': None}
    config = instance = recorder = None
    active = 'input_read_and_expansion'
    try:
        with budget.phase(active):
            config, instance = input_loader(budget)
            bound = independent_lower_bound(instance)
            budget.check()
            result.update(problem_id=instance['id'], input_sha256=canonical_hash(instance),
                independent_lower_bound=bound, certified_lower_bound_J=bound['lower_bound_J'],
                lower_bound_formed_at_s=budget.elapsed)
        recorder = CandidateRecorder(instance, config['accuracy_targets'], budget, evaluator=evaluator)
        if search is None:
            if method == 'heft':
                from heft_method import run_heft
                search = run_heft
            else:
                from sa_method import run_sa
                search = run_sa
        active = 'heuristic_search'
        with budget.phase(active):
            result['search'] = (search(instance, config, budget, recorder.assess) if method == 'heft'
                                else search(instance, config, budget, recorder.assess, seed=seed))
        result['reason'] = ('METHOD_BUDGET_EXHAUSTED' if budget.elapsed>=budget.seconds
            or (result.get('search') or {}).get('stop_reason')=='METHOD_BUDGET_EXHAUSTED'
            else 'DECLARED_SEARCH_COMPLETED')
    except Exhausted as error:
        result['reason'] = str(error)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
    except Exception as error:
        result.update(reason='INTERFACE_ERROR', error=f'{type(error).__name__}: {error}')
    stopped = budget.elapsed
    result.update(stop_stage=active, timing=budget.summary(stopped), budget_exhausted=stopped >= budget.seconds)
    if recorder is not None:
        if recorder.best is not None:
            result.update(state='SAFE', safe_candidate=recorder.best['candidate'],
                safe_upper_bound_J=recorder.best['evaluation']['safe_upper_bound_J'],
                evaluation=recorder.best['evaluation'], safe_solution_source=recorder.best['source'])
        result.update(first_candidate_at_s=recorder.first_candidate_s,
            first_legal_candidate_at_s=recorder.first_legal_s, first_safe_at_s=recorder.first_safe_s,
            candidate_count=recorder.candidates, thermal_evaluations=len(recorder.evaluations),
            cache_hits=recorder.cache_hits, violations=recorder.violations,
            events=recorder.events, evaluations=recorder.evaluations)
    # Archival only below; no decoding, repair, evaluation or search after stop.
    archive_start = clock()
    if config is not None: _save(workdir/'input_config.json', config)
    if instance is not None: _save(workdir/'input_instance.json', instance)
    _save(workdir/'result.json', result)
    _save(workdir/'environment.json', {'python': sys.version, 'platform': platform.platform()})
    _save(workdir/'archive_timing.json', {'wall_s': clock()-archive_start,
        'scope': 'serialization only; no new search evidence'})
    return result
