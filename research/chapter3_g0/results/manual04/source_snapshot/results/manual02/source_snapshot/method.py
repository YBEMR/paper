"""G0 lifecycle coordinator, enabled only for injected manual backends.

The coordinator is implemented; a real process/solver entry is intentionally
absent. Preparation, selection, numerical admission and callbacks share one
root clock. Manual output never claims a newly physically certified SAFE.
"""
from copy import deepcopy
from dataclasses import dataclass

from . import REAL_EXECUTION_ENABLED
from .budget import G0Budget, ScopeExhausted, Exhausted
from .blocks import select_block, coverage
from .contract import (validate_inputs, canonical_hash, scenes, make_scene_view)
from .local_domain import make_condition
from .receipts import Archive, ReceiptBridge


@dataclass
class ManualBackend:
    """Only these injected seams can execute work in this release.

    initializer(instance, config, budget, assess) has the legacy HEFT callback
    shape, but must be a handmade fake. build receives the full input and G0
    condition; its returned model must have the exact unweighted scene view.
    prepare returns matching model-view evaluation plus x0 admission metadata.
    search(model, x0, budget, emit) may emit several local scene candidates.
    is_idle confirms the simulated worker is drained before anchor freeze.
    """
    initializer: object
    build: object
    prepare: object
    search: object
    is_idle: object
    receipt_dependencies: object
    source_hashes: dict
    evidence_kind: str = 'MANUAL_FIXTURE'


class CleanupFailure(RuntimeError):
    pass


def make_model_view(instance, scene_id, deployment):
    view = make_scene_view(instance, scene_id)
    for shared, modes in view['stage_modes'].items():
        view['stage_modes'][shared] = [m for m in modes if m['unit_id']==deployment[shared]]
    return view


def run_g0(input_loader, backend, *, seconds, clock, manual=False):
    """Execute deterministic coordination only with explicit manual seams.

    No default initializer, solver, coefficient factory or evaluator exists.
    A future real entry needs separate approval and integration validation.
    """
    if not manual or REAL_EXECUTION_ENABLED or backend.evidence_kind != 'MANUAL_FIXTURE':
        raise PermissionError('REAL_G0_ENTRY_DISABLED')
    budget = G0Budget(seconds, clock=clock)
    out = dict(schema='g0-manual-lifecycle-v1', evidence_kind='MANUAL_FIXTURE',
               real_execution=False, state='UNRESOLVED', reason=None,
               stages={'1': [], '2': []}, initialization=None, S0=None, S1=None,
               final=None, D0=None, events=[], coverage={}, failure=None)
    out['blocks'] = {'1': {}, '2': {}}
    archive = bridge = None
    b1 = {}
    config = instance = None

    def idle():
        if backend.is_idle() is not True:
            raise CleanupFailure('WORKER_IDLE_NOT_CONFIRMED')

    def event(kind, **details):
        out['events'].append(dict(kind=kind, root_elapsed_s=budget.elapsed, **details))

    def local(stage, sid, anchor, block, phase_deadline, index, count):
        record = dict(scene_id=sid, phase=stage, block=deepcopy(block),
                      declared=True, model_completed=False, solver_entered=False,
                      complete_updates=0, status='DECLARED', started_s=budget.elapsed)
        out['stages'][str(stage)].append(record)
        if not block['open_ids']:
            record.update(status='EMPTY_BLOCK_SKIP', finished_s=budget.elapsed)
            return
        remaining = max(0.0, phase_deadline-budget.elapsed)
        slot_deadline = budget.elapsed + remaining/(count-index)
        try:
            with budget.scope(f'p{stage}:{sid}', slot_deadline, kind='slot') as scope:
                record['scope'] = scope
                record['deadline_elapsed_s'] = slot_deadline
                condition = make_condition(config, instance, anchor['candidate'], out['D0'],
                                           sid, block['open_ids'], phase=stage)
                record['condition'] = deepcopy(condition)
                budget.check()
                model = backend.build(config, instance, condition, budget)
                view = make_model_view(instance, sid, out['D0'])
                if canonical_hash(model.instance) != canonical_hash(view):
                    raise ValueError('MODEL_VIEW_MISMATCH')
                record['model_completed'] = True
                record['status'] = 'MODEL_COMPLETED'
                budget.check()
                scene_anchor = {'scenes': {sid: deepcopy(anchor['candidate']['scenes'][sid])}}
                prepared = backend.prepare(model, scene_anchor, budget)
                view_result = bridge.validate_model_view(model.instance, scene_anchor,
                                                         prepared['evaluation'], scope=scope)
                record['warm_start'] = deepcopy({k:v for k,v in prepared.items() if k != 'x0'})
                if view_result.get('state') in ('THERMAL_VIOLATION','INVALID_SCHEDULE'):
                    raise ArithmeticError('CERTIFIED_ANCHOR_MODEL_VIEW_CONFLICT')
                if view_result.get('state') != 'SAFE':
                    record['status'] = 'WARM_VIEW_UNRESOLVED_SKIP'
                    idle()
                    return
                if prepared.get('state') != 'INITIAL_POINT_READY' and prepared.get('x0') is not None:
                    raise ValueError('UNADMITTED_WARM_VECTOR')
                # Rejected numerical vectors may continue bare; thermal SAFE
                # membership of the inherited anchor is not revoked.
                budget.check()
                record['solver_entered'] = True
                record['status'] = 'SOLVER_ENTERED'

                def emit(candidate, evaluation):
                    previous = archive.best
                    changed = bridge.publish_local(sid, candidate, evaluation, condition,
                        model_instance=model.instance, source=f'phase{stage}:{sid}', scope=scope)
                    after = archive.best
                    record['complete_updates'] += int(after is not None and
                        (previous is None or after['generation_sha256'] != previous['generation_sha256']))
                    return changed

                record['search'] = deepcopy(backend.search(model, prepared.get('x0'), budget, emit))
                # A callback may have committed a timely result before this check.
                budget.check()
                record['status'] = 'COMPLETED'
                idle()
        except ScopeExhausted as error:
            record.update(status=error.kind.upper()+'_CUTOFF', stop_kind=error.kind)
            idle()
            if error.kind != 'slot':
                raise
        finally:
            record['block'] = deepcopy(block)
            record['finished_s'] = budget.elapsed

    try:
        config, instance = input_loader()
        validate_inputs(config, instance)
        budget.check()
        out['input_sha256'], out['config_sha256'] = canonical_hash(instance), canonical_hash(config)
        archive = Archive(config, instance, budget, backend.source_hashes, manual=True)
        bridge = ReceiptBridge(config, instance, budget, archive, backend.receipt_dependencies,
                               manual=True)
        ids = sorted(scenes(instance))
        phase1_end = float(seconds)/2
        try:
            with budget.scope('phase1', phase1_end, kind='phase') as phase_scope:
                event('INITIALIZATION_START')
                try:
                    out['initialization'] = backend.initializer(instance, config, budget,
                        lambda candidate, source='initialization': bridge.assess(candidate, source, scope=phase_scope))
                finally:
                    idle()
                    # A timed-out initializer may still have committed complete
                    # evidence. Its mutable latest candidate is never used.
                    out['S0'] = archive.freeze('S0')
                    event('INITIALIZATION_END', has_safe=out['S0'] is not None)
                if out['S0'] is not None:
                    out['D0'] = deepcopy(out['S0']['d0'])
                    for index, sid in enumerate(ids):
                        budget.check()
                        block = select_block(config, instance, out['S0']['candidate'], out['D0'],
                                             sid, 2, phase=1, budget=budget)
                        b1[sid] = block
                        out['blocks']['1'][sid] = block
                        local(1, sid, out['S0'], block, phase1_end, index, len(ids))
        except ScopeExhausted as error:
            event('PHASE1_CUTOFF', stop_kind=error.kind)
            idle()
        if out['S0'] is None:
            status=(out.get('initialization') or {}).get('status')
            out.update(reason='CONSTRUCTOR_UNSUPPORTED' if status=='CONSTRUCTOR_UNSUPPORTED'
                       else 'NO_COMPLETE_SAFE_INITIALIZATION')
        else:
            if out['D0'] is None:
                out['D0'] = deepcopy(out['S0']['d0'])
            idle()
            out['S1'] = archive.freeze('S1')
            event('S1_FROZEN', candidate_sha256=canonical_hash(out['S1']['candidate']))
            budget.check()
            with budget.scope('phase2', float(seconds), kind='phase'):
                # All B2 choices are frozen atomically before the first model.
                draft = {}
                for sid in ids:
                    draft[sid] = select_block(config, instance, out['S1']['candidate'], out['D0'],
                        sid, 4, previous_open=b1.get(sid, {'scene_id':sid,'state':'NOT_DECLARED','open_ids':[]}),
                        phase=2, budget=budget)
                budget.check()
                out['blocks']['2'] = draft
                event('B2_ALL_DECLARED', scene_ids=ids)
                for index, sid in enumerate(ids):
                    budget.check()
                    local(2, sid, out['S1'], draft[sid], float(seconds), index, len(ids))
    except ScopeExhausted as error:
        out.update(reason=error.kind.upper()+'_CUTOFF')
        try:
            idle()
        except CleanupFailure as cleanup:
            out['failure'] = dict(kind='CLEANUP_FAILURE', message=str(cleanup))
    except Exception as error:
        out['failure'] = dict(kind='CLEANUP_FAILURE' if isinstance(error, CleanupFailure)
                              else 'TECHNICAL_FAILURE', error_type=type(error).__name__,
                              message=str(error))
        out['reason'] = out['failure']['kind']
    finally:
        if out['failure'] is not None:
            try:
                confirmed = backend.is_idle() is True
                out['cleanup'] = {'idle_confirmed':confirmed}
                if not confirmed:
                    out['cleanup']['reason']='WORKER_IDLE_NOT_CONFIRMED'
            except Exception as error:
                out['cleanup']={'idle_confirmed':False,'error_type':type(error).__name__,'message':str(error)}
        if archive is not None:
            out['final'] = archive.snapshot()
            out['archive_records'] = deepcopy(archive.records)
            out['first_legal_s'] = archive.first_legal_elapsed_s
            out['first_safe_s'] = archive.first_safe_elapsed_s
            out['violations'] = deepcopy(archive.violations)
        if out['final'] is not None:
            out['state'] = 'MANUAL_SAFE_WITNESS_RETAINED'
        if instance is not None:
            for sid in scenes(instance):
                blocks=[]
                for p in (1,2):
                    if sid not in out['blocks'][str(p)]:
                        continue
                    statistics_view=deepcopy(out['blocks'][str(p)][sid])
                    records=[r for r in out['stages'][str(p)] if r['scene_id']==sid]
                    statistics_view.update(model_completed=any(r['model_completed'] for r in records),
                                           solver_entered=any(r['solver_entered'] for r in records))
                    blocks.append(statistics_view)
                out['coverage'][sid] = coverage(instance, sid, blocks)
        out['stopped_s'] = budget.elapsed
        out['budget'] = budget.summary(stopped_s=budget.elapsed)
        out['scope_records'] = deepcopy(budget.scope_records)
        if out['reason'] is None:
            out['reason'] = 'DECLARED_MANUAL_LIFECYCLE_COMPLETED'
    return out
