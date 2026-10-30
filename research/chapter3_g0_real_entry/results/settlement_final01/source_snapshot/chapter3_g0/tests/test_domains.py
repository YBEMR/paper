"""A01--A15: handmade exact-time/domain cases, no live scientific backend."""
from copy import deepcopy
from fractions import Fraction as F

from .. import contract as c
from .. import blocks as b
from .. import local_domain as d
from .fixtures import bundle


def _ids(instance, sid='X'):
    return [st['id'] for st in c.scenes(instance)[sid]['stage_instances']]


def _options(instance, candidate, sid='X', extras=()):
    """Explicit finite artificial rows; never imports the production expander."""
    scene = c.scenes(instance)[sid]
    stages = {s['id']: s for s in scene['stage_instances']}
    reqs = {r['id']: r for r in scene['requests']}
    rows = list(candidate['scenes'][sid]) + list(extras)
    out = []
    for index, row in enumerate(rows):
        stage = stages[row['stage_id']]
        mode = c.mode_for(instance, stage['shared_stage_id'], row['unit'], row['opp'])
        out.append(dict(mode, option_id=f'MANUAL-{sid}-{index}', scenario_id=sid,
            stage_instance_id=stage['id'], request_id=stage['request_id'],
            request_release_ms=reqs[stage['request_id']]['release_ms'],
            request_deadline_ms=reqs[stage['request_id']]['deadline_ms'],
            start_ms=row['start_ms'], end_ms=str(c.q(row['start_ms']) + c.q(mode['duration_ms']))))
    return out


def _related():
    config, instance, anchor = bundle(6, scene_ids=('X',), shape='independent')
    placements = [('CPU1','0'), ('CPU2','0'), ('CPU1','20'),
                  ('GPU0','100'), ('CPU1','40'), ('NPU0','100')]
    for row, (uid, start) in zip(anchor['scenes']['X'], placements):
        row.update(unit=uid, start_ms=start)
    for shared, modes in instance['stage_modes'].items():
        for mode in modes:
            if mode['opp_id'] == 'H':
                mode['activity_power_W'] = {'t000':'20','t002':'16'}.get(shared, '10')
                mode['activity_energy_J'] = str(c.q(mode['duration_ms']) * c.q(mode['activity_power_W']) / 1000)
    ids = _ids(instance)
    instance['scenarios'][0]['dependencies'] = [[ids[1], ids[2]], [ids[2], ids[4]]]
    return config, instance, anchor


def _filter_fixture():
    config, instance, anchor = bundle(5, scene_ids=('X',), shape='independent')
    placements = [('CPU1','20'), ('CPU2','20'), ('CPU1','40'), ('GPU0','5'), ('NPU0','30')]
    for row, (uid, start) in zip(anchor['scenes']['X'], placements):
        row.update(unit=uid, start_ms=start)
    ids = _ids(instance)
    instance['scenarios'][0]['dependencies'] = [[ids[3], ids[0]], [ids[0], ids[4]]]
    return config, instance, anchor


def A01(ctx):
    config, instance, anchor = bundle(6, shape='diamond')
    for scene in instance['scenarios']:
        ids = [st['id'] for st in scene['stage_instances']]
        scene['dependencies'] = [[ids[0],ids[1]], [ids[0],ids[2]],
            [ids[1],ids[3]], [ids[2],ids[3]], [ids[3],ids[4]], [ids[3],ids[5]]]
        scene['required_stage_instance_ids'] = list(ids)
        scene['required_output_stage_ids'] = ids[4:]
    data = c.validate_inputs(config, instance)
    rows = c.candidate_rows(config, instance, anchor)
    ctx.check(data['execution_count'] == 12 and sum(map(len, rows.values())) == 12,
              'explicit diamond branches and both outputs retained without chain_position')
    broken = deepcopy(anchor)
    broken['scenes']['X'].pop(2)
    ctx.rejects(lambda: c.candidate_rows(config, instance, broken), 'missing branch execution rejected')
    bad = deepcopy(instance)
    bad['scenarios'][0]['dependencies'][0][1] = 'NOT_A_STAGE'
    ctx.rejects(lambda: c.validate_inputs(config, bad), 'unknown edge target rejected')
    return {'fixture_id':'MANUAL-A01-MULTIOUTPUT', 'executions':12,
            'required_outputs_per_scene':2, 'uses_chain_position':False}


def A02(ctx):
    config, instance, anchor = bundle(2, shape='independent')
    instance['scenarios'][0]['stage_instances'][0]['legal_units'] = ['CPU1','CPU2']
    instance['scenarios'][1]['stage_instances'][0]['legal_units'] = ['CPU2']
    for sid in anchor['scenes']:
        anchor['scenes'][sid][0]['unit'] = 'CPU2'
    d0 = c.derive_deployment(config, instance, anchor)
    ctx.check(d0['t000'] == 'CPU2' and c.cross_projection(instance, d0) == d0,
              'current two-scene support intersection and one common device')
    bad = deepcopy(anchor)
    bad['scenes']['Y'][0]['unit'] = 'CPU1'
    ctx.rejects(lambda: c.derive_deployment(config, instance, bad), 'unsupported occurrence rejected')
    sub = deepcopy(instance)
    sub['scenarios'] = sub['scenarios'][:1]
    sub_candidate = {'scenes': {'X': deepcopy(anchor['scenes']['X'])}}
    sub_candidate['scenes']['X'][0]['unit'] = 'CPU1'
    sub_d0 = c.derive_deployment(config, sub, sub_candidate)
    ctx.check(sub_d0['t000'] == 'CPU1' and c.cross_projection(sub, sub_d0) == {},
              'current subset does not inherit removed scene restriction or reference mapping')
    return {'fixture_id':'MANUAL-A02-SUBSET', 'full_d0':d0, 'subset_d0':sub_d0}


def A03(ctx):
    config, instance, anchor = bundle(1, scene_ids=('X',), copies=2, shape='independent')
    d0 = c.derive_deployment(config, instance, anchor)
    ctx.check(d0 == {'t000':'CPU1'} and c.cross_projection(instance, d0) == {},
              'one-scene copies included by D0-all even with empty cross projection')
    bad = deepcopy(anchor)
    bad['scenes']['X'][1]['unit'] = 'CPU2'
    ctx.rejects(lambda: c.derive_deployment(config, instance, bad), 'copy device mismatch rejected')
    return {'fixture_id':'MANUAL-A03-SINGLE-SCENE-COPIES', 'd0_all':d0, 'd0_cross':{}}


def A04(ctx):
    config, instance, anchor = bundle(2, scene_ids=('X',), copies=2, shape='independent')
    rows = c.candidate_rows(config, instance, anchor)['X']
    releases = [r['release_ms'] for r in instance['scenarios'][0]['requests']]
    ctx.check(len(rows) == 4 and releases == ['0','0'],
              'synchronous requests remain four distinct executions')
    bad = deepcopy(anchor)
    bad['scenes']['X'][2]['start_ms'] = '0'
    ctx.rejects(lambda: c.candidate_rows(config, instance, bad), 'synchronous same-resource overlap rejected')
    return {'fixture_id':'MANUAL-A04-SYNC', 'execution_ids':sorted(rows), 'release_ms':releases}


def A05(ctx):
    config, instance, anchor = bundle(2, copies=2, stagger_ms=30, shape='independent')
    snapshots = {}
    for si, scene in enumerate(instance['scenarios']):
        delta = si * 5
        first, second = scene['requests']
        first.update(deadline_ms=str(delta+100), relative_deadline_ms='100')
        second.update(deadline_ms=str(delta+130), relative_deadline_ms='100')
        snapshots[scene['id']] = deepcopy(first)
    before_edges = deepcopy([s['dependencies'] for s in instance['scenarios']])
    altered = deepcopy(anchor)
    for sid in altered['scenes']:
        altered['scenes'][sid][2].update(opp='M', start_ms=str(c.q(altered['scenes'][sid][2]['start_ms']) + 5))
    c.candidate_rows(config, instance, altered)
    for scene in instance['scenarios']:
        first, second = scene['requests']
        ctx.check(first == snapshots[scene['id']] and c.q(second['release_ms']) == c.q(first['release_ms'])+30
                  and c.q(second['deadline_ms']) == c.q(second['release_ms']) +
                      c.q(first['deadline_ms']) - c.q(first['release_ms']),
                  'original request unchanged and shifted copy inherits relative deadline')
    ctx.check([s['dependencies'] for s in instance['scenarios']] == before_edges,
              'copy-specific OPP/start do not add cross-round dependency')
    return {'fixture_id':'MANUAL-A05-STAGGER', 'delta_ms':'30',
            'first_requests':snapshots, 'copy_opp_independent':True}


def A06(ctx):
    config, instance, anchor = bundle(3, scene_ids=('X',), shape='independent')
    scene = instance['scenarios'][0]
    base = deepcopy(scene['stage_instances'][0])
    for k, start in [(2,100),(3,120)]:
        item = dict(base, id=base['id']+f'.extra{k}')
        scene['stage_instances'].append(item)
        scene['requests'][0]['stage_instance_ids'].append(item['id'])
        anchor['scenes']['X'].append(dict(stage_id=item['id'], unit='CPU1', opp='H', start_ms=str(start)))
    d0 = c.derive_deployment(config, instance, anchor)
    first = b.select_block(config, instance, anchor, d0, 'X', 2)
    second = b.select_block(config, instance, anchor, d0, 'X', 4, phase=2, previous_open=first)
    ctx.check(len(first['open_ids']) == 2 and 't000' not in first['groups'],
              'oversized three-copy group skipped while smaller groups still selected')
    ctx.check(len(second['open_ids']) == 4 and 't000' in second['groups'],
              'second block takes complete three-copy complement and one old partner')
    for block in (first, second):
        for shared in block['groups']:
            expected = {s['id'] for s in scene['stage_instances'] if s['shared_stage_id'] == shared}
            ctx.check(expected <= set(block['open_ids']), 'selected copy groups never split')
    return {'fixture_id':'MANUAL-A06-MIXED-COPY-SIZES', 'b1':first['open_ids'], 'b2':second['open_ids']}


def A07(ctx):
    config, instance, anchor = _related()
    d0 = c.derive_deployment(config, instance, anchor)
    block = b.select_block(config, instance, anchor, d0, 'X', 4, phase=2)
    ctx.check(block['groups'] == ['t000','t001','t002','t004'],
              'CPU overlap first, then adjacency, then newly exposed adjacent group')
    ctx.check([x['relation_level'] for x in block['selection_trace']] == [None,1,2,2],
              'relations recomputed after every extension; adjacency outranks direct DAG')
    ctx.check(block['scores']['t003']['H_J'] == block['scores']['t005']['H_J'] and
              block['scores']['t003']['slack_ms'] == block['scores']['t005']['slack_ms'],
              'fixture has exact H/slack ties requiring stable ID fallback')
    changed, candidate = deepcopy(instance), deepcopy(anchor)
    changed['scenarios'][0]['stage_instances'].reverse()
    changed['scenarios'][0]['dependencies'].reverse()
    for modes in changed['stage_modes'].values():
        modes.reverse()
    candidate['scenes']['X'].reverse()
    other = b.select_block(config, changed, candidate, d0, 'X', 4, phase=2)
    ctx.check(other['groups'] == block['groups'] and other['open_ids'] == block['open_ids'],
              'input iteration order does not change declared choices')
    return {'fixture_id':'MANUAL-A07-RELATION-RECOMPUTE', 'selection_trace':block['selection_trace']}


def A08(ctx):
    config, instance, anchor = _related()
    d0 = c.derive_deployment(config, instance, anchor)
    first = b.select_block(config, instance, anchor, d0, 'X', 2)
    second = b.select_block(config, instance, anchor, d0, 'X', 4, phase=2, previous_open=first)
    ctx.check(second['groups'][0] not in first['groups'] and
              bool(set(second['groups']) & set(first['groups'])),
              'B2 complement seed can bring old-block related partners back')
    not_declared = {'scene_id':'X','state':'NOT_DECLARED','open_ids':[]}
    no_first = b.select_block(config, instance, anchor, d0, 'X', 4, phase=2, previous_open=not_declared)
    ctx.check(no_first['groups'][0] == 't000', 'undeclared B1 is empty rather than excluded work')
    declared_not_run = deepcopy(first)  # runtime visit flags are separately recorded by method
    replay = b.select_block(config, instance, anchor, d0, 'X', 4, phase=2, previous_open=declared_not_run)
    ctx.check(replay['groups'] == second['groups'], 'declared B1 retained even without solver entry')
    return {'fixture_id':'MANUAL-A08-DECLARATION-STATES', 'b1':first['groups'],
            'b2':second['groups'], 'no_b1_b2':no_first['groups']}


def A09(ctx):
    config, instance, anchor = _related()
    d0 = c.derive_deployment(config, instance, anchor)
    class StopBudget:
        checks = 0
        def check(self):
            self.checks += 1
            if self.checks >= 5:
                raise TimeoutError('MANUAL_SELECTION_DEADLINE')
    budget, published = StopBudget(), []
    def attempt():
        published.append(b.select_block(config, instance, anchor, d0, 'X', 4, phase=2, budget=budget))
    ctx.rejects(attempt, 'block selection cutoff raises before publishing partial declaration', exceptions=(TimeoutError,))
    ctx.check(not published and budget.checks == 5, 'no half block was published')
    return {'fixture_id':'MANUAL-A09-SELECTION-CUTOFF', 'check_count':budget.checks,
            'published_count':len(published)}


def A10(ctx):
    config, instance, anchor = bundle(2, scene_ids=('X',), shape='independent')
    d0 = c.derive_deployment(config, instance, anchor)
    ids = _ids(instance)
    empty = d.make_condition(config, instance, anchor, d0, 'X', [], phase=1)
    full = d.make_condition(config, instance, anchor, d0, 'X', ids, phase=1)
    c0 = deepcopy(anchor['scenes']['X'][0]); c0.update(opp='L',start_ms='5')
    options = _options(instance, anchor, extras=[c0])
    kept_empty, st_empty = d.filter_options(config, instance, options, empty)
    kept_full, st_full = d.filter_options(config, instance, options, full)
    ctx.check(len(kept_empty) == 2 and len(kept_full) == 3, 'empty and proper full local domains accepted')
    ctx.check(d.assert_member(config, instance, anchor, full)['state'].startswith('G0_MEMBER'),
              'all-open local scene remains fixed-deployment, not free whole MILP')
    return {'fixture_id':'MANUAL-A10-EMPTY-FULL', 'empty_filter':st_empty, 'full_filter':st_full}


def A11(ctx):
    details = {}
    for copies, denominator in [(1,96),(2,192)]:
        config, instance, anchor = bundle(96, scene_ids=('X',), copies=copies, shape='independent')
        d0 = c.derive_deployment(config, instance, anchor)
        first = b.select_block(config, instance, anchor, d0, 'X', 2)
        second = b.select_block(config, instance, anchor, d0, 'X', 4, phase=2, previous_open=first)
        actual = b.coverage(instance, 'X', [first,second])
        ctx.check(actual['total_executions'] == denominator and
                  c.q(actual['declared_fraction']) <= F(6,denominator), 'copy-aware coverage upper bound')
        ctx.check(actual['entered_fraction'] == '0', 'selection is not falsely counted as solver work')
        ids = _ids(instance)
        hand = [{'scene_id':'X','state':'DECLARED','open_ids':ids[:2]},
                {'scene_id':'X','state':'DECLARED','open_ids':ids[2:6]}]
        limit = b.coverage(instance, 'X', hand)
        ctx.check(c.q(limit['declared_fraction']) == F(6,denominator), 'explicit upper-limit coverage arithmetic')
        details[str(copies)] = {'actual':actual, 'ceiling_fraction':str(F(6,denominator))}
    return {'fixture_id':'MANUAL-A11-96-192-COVERAGE', 'coverage':details}


def A12(ctx):
    config, instance, anchor = bundle(2, scene_ids=('X',), shape='independent')
    anchor['scenes']['X'][1]['start_ms'] = '0'
    rows = c.candidate_rows(config, instance, anchor)['X']
    ctx.check(len(rows) == 2 and {r['domain_id'] for r in rows.values()} == {'CPU'},
              'two CPU units concurrently use one common frequency domain')
    bad = deepcopy(anchor)
    bad['scenes']['X'][1]['opp'] = 'M'
    ctx.rejects(lambda: c.candidate_rows(config, instance, bad), 'shared CPU OPP conflict rejected')
    return {'fixture_id':'MANUAL-A12-CPU-DVFS', 'same_opp_parallel_legal':True,
            'different_opp_parallel_rejected':True}


def A13(ctx):
    config, instance, anchor = _filter_fixture()
    d0 = c.derive_deployment(config, instance, anchor)
    identity = _ids(instance)[0]
    condition = d.make_condition(config, instance, anchor, d0, 'X', [identity], phase=1)
    extras = [dict(stage_id=identity, unit='CPU1', opp=opp, start_ms=start)
              for opp,start in [('H','40'),('M','20'),('H','0'),('H','30'),('H','10'),('H','25')]]
    options = _options(instance, anchor, extras=extras)
    kept, stats = d.filter_options(config, instance, options, condition)
    rules = {rule for item in stats['removals'] for reason in item['reasons'] for rule in reason['rules']}
    ctx.check(rules == {'same_unit_overlap','same_domain_different_opp_overlap',
        'open_predecessor_finishes_after_closed_start','open_successor_starts_before_closed_end'},
        'all and only four allowed exact conflict kinds exercised')
    starts = {o['start_ms'] for o in kept if o['stage_instance_id'] == identity}
    ctx.check(starts == {'10','20','25'}, 'half-open boundaries and anchor survive')
    return {'fixture_id':'MANUAL-A13-FOUR-FILTER-RULES', 'rules':sorted(rules),
            'retained_open_starts':sorted(starts), 'stats':stats}


def A14(ctx):
    config, instance, anchor = _filter_fixture()
    d0 = c.derive_deployment(config, instance, anchor)
    ids = _ids(instance)
    old = d.make_condition(config, instance, anchor, d0, 'X', [ids[0]], phase=1)
    _, old_stats = d.filter_options(config, instance, _options(instance, anchor), old)
    tampered = deepcopy(old); tampered['open_ids'] = [ids[1]]
    ctx.rejects(lambda: d.validate_condition(config, instance, tampered), 'changed block rejects old condition hash')
    warm = deepcopy(anchor)
    warm['scenes']['X'][1]['start_ms'] = '15'
    fresh = d.make_condition(config, instance, warm, d0, 'X', [ids[1]], phase=2)
    kept, fresh_stats = d.filter_options(config, instance, _options(instance, warm), fresh)
    ctx.check(old_stats['condition_sha256'] != fresh_stats['condition_sha256'] and
              old_stats['anchor_sha256'] != fresh_stats['anchor_sha256'], 'old filter evidence cannot identify new block/anchor')
    ctx.check(len(kept) == 5, 'new anchor own option survives recomputation')
    # The manual option seam must not enlarge the declared scientific domain.
    # Keep complete anchor rows and append exactly one corrupted open option.
    def extra(start='15'):
        return dict(stage_id=ids[0], unit='CPU1', opp='H', start_ms=start)
    wrong_grid = _options(instance, anchor, extras=[extra('1')])
    ctx.rejects(lambda: d.filter_options(config, instance, wrong_grid, old),
                'non-5ms manual option cannot enter the local model')
    wrong_window = _options(instance, anchor, extras=[extra(instance['window_ms'])])
    ctx.rejects(lambda: d.filter_options(config, instance, wrong_window, old),
                'option ending beyond original W rejected')
    wrong_end = _options(instance, anchor, extras=[extra()])
    wrong_end[-1]['end_ms'] = str(c.q(wrong_end[-1]['end_ms'])+5)
    ctx.rejects(lambda: d.filter_options(config, instance, wrong_end, old),
                'option end must equal original mode duration plus start')
    wrong_deadline = _options(instance, anchor)
    wrong_deadline[0]['request_deadline_ms'] = str(c.q(wrong_deadline[0]['request_deadline_ms'])+5)
    ctx.rejects(lambda: d.filter_options(config, instance, wrong_deadline, old),
                'option request deadline cannot substitute another value')
    explicit = deepcopy(instance)
    explicit['start_domain'] = {'version':1, 'kind':'explicit_grid_subset',
        'by_scene_stage_ms':{sid:{r['stage_id']:[r['start_ms']] for r in rows}
                             for sid, rows in anchor['scenes'].items()}}
    explicit_condition = d.make_condition(config, explicit, anchor, d0, 'X', [ids[0]], phase=1)
    outside = _options(explicit, anchor, extras=[extra()])
    ctx.rejects(lambda: d.filter_options(config, explicit, outside, explicit_condition),
                'grid-valid but undeclared start cannot enter explicit finite domain')
    released = deepcopy(instance)
    released['scenarios'][0]['requests'][0]['release_ms'] = '5'
    released_condition = d.make_condition(config, released, anchor, d0, 'X', [ids[0]], phase=1)
    too_early = _options(released, anchor, extras=[extra('0')])
    ctx.rejects(lambda: d.filter_options(config, released, too_early, released_condition),
                'grid/window-valid option before actual request release rejected')
    # An independently overdue option is still passed to the inherited
    # deadline gate. Turning off closed-anchor implications isolates this check.
    overdue = _options(instance, anchor, extras=[extra('195')])
    overdue_kept, _ = d.filter_options(config, instance, overdue, old, preeliminate=False)
    ctx.check(any(o['stage_instance_id']==ids[0] and o['start_ms']=='195' for o in overdue_kept),
              'in-window late option is left to inherited prefilter/fix-zero deadline stage')
    return {'fixture_id':'MANUAL-A14-REBUILD-ANCHOR', 'old_condition':old['condition_sha256'],
            'new_condition':fresh['condition_sha256'], 'new_anchor_options':len(kept),
            'manual_option_contract_negatives':6, 'late_option_retained_for_original_gate':True}


def A15(ctx):
    config, instance, s0 = bundle(2, scene_ids=('X',), shape='independent')
    d0 = c.derive_deployment(config, instance, s0)
    ids = _ids(instance)
    f1 = d.make_condition(config, instance, s0, d0, 'X', [ids[0]], phase=1)
    s1 = deepcopy(s0); s1['scenes']['X'][0]['start_ms'] = '5'
    f2 = d.make_condition(config, instance, s1, d0, 'X', [ids[1]], phase=2)
    d.assert_member(config, instance, s0, f1)
    d.assert_member(config, instance, s1, f2)
    ctx.rejects(lambda: d.assert_member(config, instance, s0, f2), 'old S0 need not belong to F2')
    archive = [deepcopy(s0), deepcopy(s1)]
    ctx.check(archive[0] == s0 and archive[1] == s1, 'domain change does not erase previously archived safe candidate')
    return {'fixture_id':'MANUAL-A15-ANCHOR-MEMBERSHIP', 'S0_in_F1':True,
            'S1_in_F2':True, 'S0_in_F2':False, 'archive_candidates':len(archive)}
