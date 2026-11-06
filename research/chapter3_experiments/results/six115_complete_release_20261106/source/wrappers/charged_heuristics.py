"""Original searches/cache, with complete SAFE and charged archive admission."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json

@contextmanager
def install_charged_recorder(folder):
    import heuristic_runner as h
    from research.chapter3_method_entry_executor.common import inspect_safe_receipt
    original = h.CandidateRecorder
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=False)
    serial = [0]
    costs = dict(full_safe_validation_seconds=0., charged_best_archive_seconds=0.,
                 complete_safe_checks=0, best_archives=0,
                 scope='Engineering admission overhead inside unchanged root; no extra search budget')
    class ChargedRecorder(original):
        def assess(self, candidate, source):
            prior = (self.best, self.first_safe_s, len(self.events))
            previous_evaluation_count = len(self.evaluations)
            identity = h.canonical_hash(candidate)
            try:
                result = super().assess(candidate, source)
                if result.get('state') == 'SAFE':
                    validation_started = self.budget.clock()
                    full = inspect_safe_receipt(self.instance, dict(safe_candidate=candidate,
                        evaluation=result, safe_upper_bound_J=result.get('safe_upper_bound_J')), self.budget.seconds)
                    costs['full_safe_validation_seconds'] += self.budget.clock() - validation_started
                    costs['complete_safe_checks'] += 1
                    if not full['preserved']:
                        raise ValueError('INCOMPLETE_FULL_SAFE_RECEIPT')
                    self.budget.check()
                    if self.best is prior[0]:
                        return result  # Same local cache/non-improving result: no extra archive.
                    serial[0] += 1
                    archive_started = self.budget.clock()
                    record = dict(candidate=deepcopy(candidate), evaluation=deepcopy(result), source=source,
                        input_sha256=h.canonical_hash(self.instance), archive_is_not_acceptance_commit=True)
                    with (root / f'candidate_{serial[0]:06d}.json').open('x', encoding='utf-8') as stream:
                        json.dump(record, stream, allow_nan=False)
                    costs['charged_best_archive_seconds'] += self.budget.clock() - archive_started
                    costs['best_archives'] += 1
                    self.budget.check()
                    committed = self.budget.clock()
                    if not self.budget.start <= committed < self.budget.deadline:
                        from thermal import Exhausted
                        raise Exhausted('wall_time_limit')
                    if self.best is not None and self.best.get('candidate_sha256') == identity:
                        self.best['admission_committed_at_s'] = committed - self.budget.start
                return result
            except BaseException as error:
                self.best, self.first_safe_s, event_count = prior
                del self.events[event_count:]
                for row in self.evaluations[previous_evaluation_count:]:
                    row.update(accepted_safe=False, charged_admission_rejected=True,
                               charged_admission_error=type(error).__name__ + ': ' + str(error))
                self.cache.pop(identity, None)
                raise
    h.CandidateRecorder = ChargedRecorder
    try:
        yield
    finally:
        h.CandidateRecorder = original
        with (root / 'charged_costs.json').open('x', encoding='utf-8') as stream:
            json.dump(costs, stream, indent=2, allow_nan=False)
