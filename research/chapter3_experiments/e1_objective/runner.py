"""Objective-specific selection; unchanged physical receipts are kept separately.

All scientific dependencies are explicit. Tests inject mocked evaluation and
construction; this module does not import or start a scientific backend.
"""
from copy import deepcopy
from fractions import Fraction as F
from h02_pair_preflight.common import require, sha, timely
from h02_pair_preflight.receipts import safe_receipt, thermal_witness, technical_issues
from h02_pair_b0.budget import RootBudgetExpired
from .scoring import score_candidate


class ObjectiveRecorder:
    def __init__(self, instance, accuracy, budget, objective, *, validator, evaluator,
                 scorer=score_candidate, checkpoint=lambda value: None):
        require(objective in ('FULL', 'OMIT_TEMP'), 'OBJECTIVE')
        self.instance, self.accuracy = deepcopy(instance), deepcopy(accuracy)
        self.budget, self.objective = budget, objective
        self.validator, self.evaluator, self.scorer = validator, evaluator, scorer
        self.checkpoint = checkpoint
        self.evaluations, self.events, self.violations, self.cache = [], [], [], {}
        self.best = None
        self.candidates = self.cache_hits = 0
        self.first_candidate_s = self.first_legal_s = self.first_safe_s = None
        self.input_hash, self.accuracy_hash = sha(instance), sha(accuracy)

    def _immutable_call(self, function, candidate, *, evaluate=False):
        i, c, a = deepcopy(self.instance), deepcopy(candidate), deepcopy(self.accuracy)
        identities = sha(i), sha(c), sha(a)
        out = function(i, c, a, self.budget) if evaluate else function(i, c)
        require(identities == (sha(i), sha(c), sha(a)), 'BACKEND_MUTATED_INPUT')
        return out

    def assess(self, candidate, source):
        self.budget.check()
        self.candidates += 1
        if self.first_candidate_s is None: self.first_candidate_s = self.budget.elapsed
        key = sha(candidate)
        if key in self.cache:
            self.cache_hits += 1
            self.budget.check()
            return deepcopy(self.cache[key])
        with self.budget.phase('legality'):
            legal = self._immutable_call(self.validator, candidate)
        self.budget.check()
        # The unchanged HEFT builder emits only fully validated schedules.
        # A contradictory/malformed output is a technical stop, not new evidence.
        require(legal.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED',
                'BUILDER_LEGALITY_CONTRADICTION')
        if self.first_legal_s is None: self.first_legal_s = self.budget.elapsed
        with self.budget.phase('true_continuous_evaluation'):
            receipt = self._immutable_call(self.evaluator, candidate, evaluate=True)
        returned = self.budget.elapsed
        row = dict(source=source, candidate=deepcopy(candidate), candidate_sha256=key,
                   legality=deepcopy(legal), evaluation=deepcopy(receipt),
                   returned_at_s=returned, accepted_safe=False, eligible_for_selection=False)
        self.evaluations.append(row)
        require(receipt.get('problem_id') == self.instance['id'] and
                receipt.get('evidence_identity') == dict(input_sha256=self.input_hash,
                                                         candidate_sha256=key), 'RECEIPT_IDENTITY')
        if receipt.get('violations'):
            # Preserve pre-deadline witnesses even if the evaluator returned late.
            self.violations.extend(deepcopy(thermal_witness(self.instance, receipt, self.budget.seconds)))
        require(not technical_issues(receipt), 'EVALUATOR_TECHNICAL_FAILURE')
        state = receipt.get('state')
        require(state in ('SAFE', 'UNRESOLVED', 'THERMAL_VIOLATION'), 'EVALUATOR_STATE_CONTRADICTION')
        if state != 'SAFE':
            self.checkpoint(self.snapshot())
            self.budget.check()
            return {'state': state, 'planning_score_J': None}
        formed = receipt.get('completed_at_elapsed_s')
        if not timely(formed, self.budget.seconds):
            row['reason'] = 'LATE_SAFE_NOT_ACCEPTED'
            self.checkpoint(self.snapshot())
            self.budget.check()
            require(False, 'SAFE_TIMESTAMP_INVALID_BEFORE_DEADLINE')
        require(formed <= returned, 'FUTURE_RECEIPT_TIMESTAMP')
        safe_receipt(self.instance, candidate, receipt, self.accuracy, self.budget.seconds)
        require(legal == receipt.get('legality'), 'RECEIPT_LEGALITY_MISMATCH')
        row['accepted_safe'] = True
        if self.first_safe_s is None: self.first_safe_s = formed
        # Timely physical evidence alone cannot create a new post-deadline score.
        self.budget.check()
        with self.budget.phase('objective_and_identity'):
            score = self.scorer(self.instance, candidate, legal, receipt, self.accuracy,
                                self.budget.seconds, self.objective)
            require(score['candidate_sha256'] == key and score['input_sha256'] == self.input_hash,
                    'SCORE_IDENTITY')
            require(score['objective'] == self.objective and
                    tuple(map(F, score['true_energy_J'])) == tuple(map(F, receipt['weighted_energy_J'])) and
                    F(score['true_U_J']) == F(receipt['safe_upper_bound_J']), 'SCORE_TRUE_RECEIPT_MISMATCH')
            self.budget.check()
        # Complete copies/comparison/view construction BEFORE final admission.
        # After the clock check, only publish prebuilt references and timestamps.
        final_row = deepcopy(row)
        final_row.update(score=deepcopy(score), selection_formed_at_s=None, eligible_for_selection=True)
        better = self.best is None or F(score['planning_score_J'][1]) < F(self.best['score']['planning_score_J'][1])
        event = dict(event='planning_score_improvement', at_s=None, candidate_sha256=key,
                     planning_score_J=deepcopy(score['planning_score_J']),
                     selected_true_U_J=receipt['safe_upper_bound_J'])
        events = self.events + [event] if better else self.events
        view = dict(state='SAFE', planning_score_J=deepcopy(score['planning_score_J']))
        cache = {**self.cache, key: deepcopy(view)}
        at = self.budget.elapsed
        self.budget.check()
        final_row['selection_formed_at_s'] = at
        event['at_s'] = at
        self.evaluations[-1] = final_row
        if better: self.best = final_row
        self.events, self.cache = events, cache
        self.checkpoint(self.snapshot())  # archive only, never supplies new evidence
        self.budget.check()
        return view

    def snapshot(self):
        return deepcopy(dict(objective=self.objective, input_sha256=self.input_hash,
            accuracy_sha256=self.accuracy_hash, best=self.best, evaluations=self.evaluations,
            events=self.events, violations=self.violations, candidates=self.candidates,
            cache_hits=self.cache_hits, first_candidate_at_s=self.first_candidate_s,
            first_legal_at_s=self.first_legal_s, first_safe_at_s=self.first_safe_s))


def execute(input_loader, budget, objective, *, search, validator, evaluator,
            exhausted=(), scorer=score_candidate, checkpoint=lambda value: None):
    """Caller owns the root before input/imports; this function never resets it.

    No output here is an independent optimality claim. A technical failure can
    coexist with an earlier SAFE: stop_required governs continuation.
    """
    recorder = None
    out = dict(state='UNRESOLVED', reason=None, stop_required=False, objective=objective,
               safe_candidate=None, evaluation=None, planning_score_J=None,
               safe_upper_bound_J=None, independently_proven_optimal=False,
               coverage_complete=False, method='e1-adapted-heft', seed=None)
    try:
        budget.check()
        with budget.phase('input_and_initialization'):
            config, instance = input_loader(budget)
            require(instance['response_variant'] == 'H', 'E1_REQUIRES_TRUE_H')
            require(objective in ('FULL', 'OMIT_TEMP'), 'OBJECTIVE')
            recorder = ObjectiveRecorder(instance, config['accuracy_targets'], budget, objective,
                validator=validator, evaluator=evaluator, scorer=scorer, checkpoint=checkpoint)
            out.update(problem_id=instance['id'], input_sha256=sha(instance),
                       config_sha256=sha(config), accuracy_sha256=sha(config['accuracy_targets']))
            budget.check()
        with budget.phase('search'):
            out['search'] = search(instance, config, budget, recorder.assess, allow_auto_low=True)
        budget.check()
        out['reason'] = 'DECLARED_SEARCH_COMPLETED'
    except (RootBudgetExpired,) + tuple(exhausted):
        out['reason'] = 'METHOD_BUDGET_EXHAUSTED'
    except Exception as error:
        out.update(reason='TECHNICAL_FAILURE', stop_required=True,
                   error=type(error).__name__ + ':' + str(error))
    if recorder is not None:
        out['archive'] = recorder.snapshot()
        if recorder.best is not None:
            selected = recorder.best
            out.update(state='SAFE', safe_candidate=deepcopy(selected['candidate']),
                       evaluation=deepcopy(selected['evaluation']),
                       safe_upper_bound_J=selected['evaluation']['safe_upper_bound_J'],
                       planning_score_J=deepcopy(selected['score']['planning_score_J']),
                       selected_candidate_sha256=selected['candidate_sha256'],
                       selected_at_s=selected['selection_formed_at_s'],
                       selected_source=selected['source'])
    out['timing'] = budget.summary()
    return out
