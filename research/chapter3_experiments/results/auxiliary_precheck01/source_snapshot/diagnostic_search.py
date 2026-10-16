"""Live receipts for one diagnostic; no new model, solver rule or heat cut.

MATLAB publishes immutable events. Python checks candidates on the same
absolute budget while MATLAB continues; monitoring/validation contention is
part of this invocation. Callback bounds remain solver-reported only.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from milp import decode, evaluate_model_candidate, add_thermal_feedback, logical_candidate_diagnostics
from thermal import Exhausted


class Recorder:
    def __init__(self, model, accuracy, budget, folder, *, decoder=decode,
                 evaluator=evaluate_model_candidate):
        self.model, self.accuracy, self.budget = model, accuracy, budget
        self.folder = Path(folder)
        self.decoder, self.evaluator = decoder, evaluator
        self.next_event = {}
        self.cache = {}
        self.best = None
        self.evaluations = []
        self.progress = []
        self.first_candidate_s = self.first_legal_s = self.first_safe_s = None
        self.solver_entered_s = None
        self.event_count = self.candidate_count = self.duplicates = 0
        self.decode_records = []

    def log(self, row):
        # Logging cost is charged; receipt time is never replaced by log time.
        with (self.folder/'diagnostic_events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')

    def poll(self, prefix):
        number = self.next_event.get(str(prefix), 1)
        while self.budget.remaining > 0:
            path = Path(f'{prefix}.event_{number:06d}.json')
            try:
                event = json.loads(path.read_text(encoding='utf-8-sig'))
            except (FileNotFoundError, PermissionError, UnicodeDecodeError, json.JSONDecodeError):
                break
            self.budget.check()  # complete publication read must be in-budget
            number += 1
            self.next_event[str(prefix)] = number
            self.event_count += 1
            stamp = self.budget.elapsed
            row = {k: v for k, v in event.items() if k != 'x'}
            row.update(event='worker_event_received', method_elapsed_s=stamp,
                       request=prefix.name, evidence='solver-reported')
            self.progress.append(row)
            if event.get('kind') == 'solver_entered' and self.solver_entered_s is None:
                self.solver_entered_s = stamp
            self.log(row)
            if event.get('x'):
                self.assess(event['x'], f'{prefix.name}:event{number-1}')

    def assess(self, x, source):
        self.budget.check()
        appeared = self.budget.elapsed
        if self.first_candidate_s is None:
            self.first_candidate_s = appeared
        self.candidate_count += 1
        self.log({'event': 'candidate_received', 'source': source, 'method_elapsed_s': appeared})
        record = {'source': source, 'received_at_s': appeared}
        try:
            with self.budget.phase('decode_and_legality'):
                if hasattr(self.model, 'logical_binary'):
                    record['logical_values'] = logical_candidate_diagnostics(self.model, x)
                    self.budget.check()
                candidate = self.decoder(self.model, x)
        except ValueError as exc:
            record.update(state='REJECTED', reason=str(exc), completed_at_s=self.budget.elapsed,
                          within_budget=self.budget.elapsed < self.budget.seconds)
            self.decode_records.append(record)
            self.log({'event': 'invalid_candidate', 'source': source, 'error': str(exc),
                      'method_elapsed_s': self.budget.elapsed, 'decode': record})
            return None, None
        except Exhausted:
            record.update(state='UNRESOLVED', reason='DECODE_BUDGET_EXHAUSTED',
                          completed_at_s=self.budget.elapsed, within_budget=False)
            self.decode_records.append(record)
            self.log({'event': 'decode_unresolved', 'decode': record})
            raise
        record.update(state='LEGAL' if self.budget.elapsed < self.budget.seconds else 'LATE',
                      completed_at_s=self.budget.elapsed,
                      within_budget=self.budget.elapsed < self.budget.seconds)
        self.decode_records.append(record)
        if record['within_budget'] and self.first_legal_s is None:
            self.first_legal_s = record['completed_at_s']
        self.log({'event': 'candidate_decoded', 'decode': record})
        self.budget.check()
        identity = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()
        if identity in self.cache:
            self.duplicates += 1
            self.log({'event': 'duplicate_receipt_reused', 'candidate_sha256': identity,
                      'source': source, 'method_elapsed_s': self.budget.elapsed})
            return candidate, self.cache[identity]
        with self.budget.phase('continuous_thermal_energy_evaluation'):
            evaluation = self.evaluator(self.model, candidate, self.accuracy, self.budget)
        completed = evaluation.get('completed_at_elapsed_s')
        timely_safe = (evaluation['state'] == 'SAFE' and evaluation.get('rankable_energy')
                       and completed is not None and completed < self.budget.seconds)
        receipt = {'candidate': candidate, 'evaluation': evaluation,
                   'candidate_sha256': identity, 'source': source,
                   'evaluation_returned_at_s': self.budget.elapsed,
                   'accepted_safe': bool(timely_safe)}
        self.evaluations.append(receipt)  # preserve in-budget witness on interruption
        if timely_safe:
            if self.first_safe_s is None:
                self.first_safe_s = completed
            if self.best is None or Fraction(evaluation['safe_upper_bound_J']) < Fraction(self.best['evaluation']['safe_upper_bound_J']):
                self.best = receipt
        # Only complete decisions are reusable, not unresolved/prefix energies.
        if timely_safe or evaluation['state'] == 'THERMAL_VIOLATION':
            self.cache[identity] = evaluation
        self.log({'event': 'candidate_evaluated', **receipt})
        return candidate, evaluation

    def summary(self):
        return {'first_candidate_received_s': self.first_candidate_s,
                'first_legal_candidate_s': self.first_legal_s,
                'first_safe_receipt_s': self.first_safe_s,
                'solver_entered_received_s': self.solver_entered_s,
                'worker_events': self.event_count, 'candidate_receipts': self.candidate_count,
                'duplicate_receipts': self.duplicates, 'evaluations': self.evaluations,
                'decode_records': self.decode_records,
                'decode_rejections': sum(r['state'] == 'REJECTED' and r['within_budget'] for r in self.decode_records),
                'solver_progress': self.progress,
                'time_semantics': 'Python complete receipt/decode/independent SAFE commit; native callback time recorded separately',
                'solver_bounds_independently_certified': False}


def solve_diagnostic(model, session, accuracy, budget, max_rounds=50):
    recorder = Recorder(model, accuracy, budget, session.workdir.parent)
    session.event_consumer = recorder.poll
    result = {'state': 'UNRESOLVED', 'safe_candidate': None, 'safe_upper_bound_J': None,
              'evaluation': None, 'rounds': [], 'feedback': [],
              'independently_proven_optimal': False, 'independently_proven_infeasible': False,
              'remaining_domain': 'retained', 'reason': None}
    try:
        for iteration in range(max_rounds):
            budget.check()
            with budget.phase('matrix_export'):
                solver_input = model.as_solver_dict()
            budget.check()
            with budget.phase('solver_transport_and_solve'):
                returned = session.solve(solver_input, remaining_s=budget.remaining, budget=budget)
            result['rounds'].append(returned)
            budget.check()
            if not returned.get('budget_valid'):
                result['reason'] = 'SOLVER_RETURN_AFTER_BUDGET'; break
            if not returned.get('x'):
                result['reason'] = 'SOLVER_REPORTED_INFEASIBLE' if returned.get('exitflag') == -2 else 'NO_INTEGER_CANDIDATE'; break
            if not returned.get('accepted_for_evaluation'):
                result['reason'] = 'SOLVER_INTERFACE_ERROR'; break
            candidate, evaluation = recorder.assess(returned['x'], f'round{iteration+1}:final')
            if evaluation is None:
                result['reason'] = 'NUMERICAL_CANDIDATE_ANOMALY'; break
            result['evaluation'] = evaluation
            if (evaluation['state'] == 'SAFE' and evaluation.get('rankable_energy')
                    and evaluation.get('completed_at_elapsed_s', budget.seconds) < budget.seconds):
                result['reason'] = 'SAFE_ENGINEERING_CONVERGENCE' if returned.get('exitflag') == 1 else 'SAFE_INCUMBENT'
                break
            if evaluation['state'] != 'THERMAL_VIOLATION':
                result['reason'] = 'EVALUATION_UNRESOLVED'; break
            budget.check()
            with budget.phase('thermal_feedback'):
                feedback = add_thermal_feedback(model, candidate, evaluation)
            feedback['completed_at_elapsed_s'] = budget.elapsed
            feedback['within_budget'] = budget.elapsed < budget.seconds
            result.setdefault('feedback' if feedback['within_budget'] else 'late_feedback_diagnostics', []).append(feedback)
            budget.check()
            if not feedback['rows_added']:
                result['reason'] = 'FEEDBACK_UNRESOLVED'; break
        else:
            result['reason'] = 'OUTER_ROUND_LIMIT'
    except Exhausted as exc:
        result['reason'] = str(exc)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
    except Exception as exc:
        result.update(reason='INTERFACE_ERROR', error=f'{type(exc).__name__}: {exc}')
    finally:
        session.event_consumer = None
        result['diagnostic'] = recorder.summary()
        if recorder.best is not None:
            result.update(state='SAFE', safe_candidate=recorder.best['candidate'],
                          safe_upper_bound_J=recorder.best['evaluation']['safe_upper_bound_J'],
                          evaluation=recorder.best['evaluation'])
        result['elapsed_s'] = budget.elapsed
    return result
