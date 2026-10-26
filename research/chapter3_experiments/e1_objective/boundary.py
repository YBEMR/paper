"""E1 phase boundary and mockable budget/once-use contract; no process launch.

The real batch supervisor is deliberately not enabled in this implementation
stage. A future human-approved execution envelope must be implemented/reviewed
before real calls. Changing a Boolean cannot bypass this closed entry.
"""
from dataclasses import dataclass
from copy import deepcopy
from h02_pair_preflight.common import require, sha
from h02_pair_preflight.receipts import safe_receipt, technical_issues
from h02_pair_b0.budget import anchored_budget_class, RootBudgetExpired, watchdog_decision
from .runner import execute
from .exports import verify_export

SLOTS = (('base__R1', 'FULL'), ('base__R1', 'OMIT_TEMP'),
         ('base__R3', 'OMIT_TEMP'), ('base__R3', 'FULL'))
BUDGETS = dict(plan_s=300, post_s=60, plan_calls=4, post_calls=4,
               evidence_s=1440, watchdog_grace_s=5, slot_wall_s=420, batch_wall_s=1800)


def require_mock_only(mode):
    require(mode == 'MOCK_ONLY', 'E1_REAL_EXECUTION_NOT_AUTHORIZED_OR_SUPERVISED')


@dataclass
class Bindings:
    search: object
    validator: object
    evaluator: object
    budget_base: type
    exhausted: type
    kind: str = 'MOCK_ONLY'


def real_backend_spec():
    # Frozen call targets, not live imports or permission to execute them.
    return dict(search='e1_objective.search.run_search',
                constructor='heft_method.build_heft_candidate',
                legality='schedules.validate_schedule',
                evaluator='thermal.evaluate_candidate', budget='timing.MethodBudget')


class MockConsumption:
    """Only mock once-use semantics; not a persistent research authorization."""
    def __init__(self):
        self.claims, self.posts, self.stopped = set(), set(), False

    def claim_plan(self, ordinal):
        require(not self.stopped and type(ordinal) is int and 1 <= ordinal <= 4, 'PLAN_SCOPE_OR_STOP')
        require(ordinal not in self.claims, 'ALREADY_CONSUMED')
        self.claims.add(ordinal)

    def claim_post(self, ordinal, candidate_hash):
        require(not self.stopped and ordinal in self.claims and candidate_hash, 'POST_WITHOUT_PLAN_OR_STOP')
        require(ordinal not in self.posts, 'POST_ALREADY_CONSUMED')
        self.posts.add(ordinal)

    def observe(self, result):
        if result.get('stop_required') is True: self.stopped = True


def validate_pair(left, right):
    require(set(left) == set(right) == {'config', 'instance', 'objective'}, 'PACKET_FIELDS')
    require(left['objective'] == 'FULL' and right['objective'] == 'OMIT_TEMP', 'PAIR_LABELS')
    require(left['config'] == right['config'] and left['instance'] == right['instance'], 'PHYSICAL_INPUT_DRIFT')
    require(left['instance']['response_variant'] == 'H', 'TRUTH_NOT_H')
    return dict(input_sha256=sha(left['instance']), config_sha256=sha(left['config']),
                differing_fields=['objective'])


def planner_chain(packet, root, bindings, *, checkpoint=lambda value: None):
    require_mock_only(bindings.kind)  # BEFORE backend invocation or any fresh budget.
    require(root.limit_s == BUDGETS['plan_s'], 'ROOT_PLAN_LIMIT')
    root.check()
    require(set(packet) == {'config', 'instance', 'objective'}, 'PACKET_FIELDS')
    public = deepcopy(packet)
    budget = anchored_budget_class(bindings.budget_base, root, root.clock)(seconds=300, clock=root.clock)
    def loader(b):
        b.check()
        return deepcopy(public['config']), deepcopy(public['instance'])
    result = execute(loader, budget, public['objective'], search=bindings.search,
        validator=bindings.validator, evaluator=bindings.evaluator, exhausted=(bindings.exhausted,),
        checkpoint=checkpoint)
    require(sha(packet) == sha(public), 'PUBLIC_PACKET_MUTATION')
    checked = verify_export(public['instance'], public['config'], result, 300)
    return dict(result=result, checked=checked, kind='MOCK_ONLY', usable_as_research_evidence=False)


def post_chain(packet, selected, root, bindings):
    """At most one candidate, no search/repair/reselection. Mock-only in this stage."""
    require_mock_only(bindings.kind)
    require(root.limit_s == BUDGETS['post_s'], 'ROOT_POST_LIMIT')
    budget = anchored_budget_class(bindings.budget_base, root, root.clock)(seconds=60, clock=root.clock)
    out = dict(state='UNRESOLVED', stop_required=False, kind='MOCK_ONLY', new_real_SAFE=0)
    try:
        budget.check()
        i, c = deepcopy(packet['instance']), deepcopy(selected['candidate'])
        require(selected['input_sha256'] == sha(i) and selected['candidate_sha256'] == sha(c), 'POST_IDENTITY')
        before = sha(i), sha(c)
        legal = bindings.validator(i, c)
        require(before == (sha(i), sha(c)), 'POST_VALIDATOR_MUTATION')
        require(legal.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED', 'POST_LEGALITY_CONTRADICTION')
        budget.check()
        accuracy = deepcopy(packet['config']['accuracy_targets']); ah = sha(accuracy)
        receipt = bindings.evaluator(i, c, accuracy, budget)
        require(before == (sha(i), sha(c)) and ah == sha(accuracy), 'POST_EVALUATOR_MUTATION')
        out['raw_receipt'] = deepcopy(receipt)
        require(receipt.get('evidence_identity') == dict(input_sha256=before[0],candidate_sha256=before[1]) and
                receipt.get('problem_id') == i['id'], 'POST_RECEIPT_IDENTITY')
        require(not technical_issues(receipt), 'POST_TECHNICAL_FAILURE')
        require(receipt.get('legality') == legal, 'POST_LEGALITY_MISMATCH')
        # Validation after a late return only authenticates already formed bytes.
        if receipt.get('state') == 'SAFE':
            from h02_pair_preflight.common import timely
            if timely(receipt.get('completed_at_elapsed_s'), 60):
                require(receipt['completed_at_elapsed_s'] <= root.elapsed, 'POST_FUTURE_TIMESTAMP')
                safe_receipt(i, c, receipt, accuracy, 60)
                out.update(state='MOCK_SAFE_RECEIPT_CHECKED', candidate_sha256=before[1])
            else: out['reason'] = 'POST_LATE_SAFE'
        elif receipt.get('state') == 'UNRESOLVED': out['reason'] = receipt.get('reason')
        else: out.update(reason='POST_CONTRADICTS_PLAN_OR_INTERFACE', stop_required=True)
    except (bindings.exhausted, RootBudgetExpired): out['reason'] = 'POST_ROOT_EXHAUSTED'
    except Exception as error: out.update(reason=type(error).__name__+':'+str(error), stop_required=True)
    out['root'] = root.summary()
    return out


def supervision_state(now, origin, root_limit, slot_elapsed, batch_elapsed):
    require(root_limit in (300, 60), 'SUPERVISION_LIMIT')
    if batch_elapsed >= BUDGETS['batch_wall_s'] or slot_elapsed >= BUDGETS['slot_wall_s']:
        return 'TERMINATE'
    return watchdog_decision(now, origin, root_limit, BUDGETS['watchdog_grace_s'])
