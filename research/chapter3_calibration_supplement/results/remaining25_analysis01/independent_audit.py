"""Independent archive arithmetic and graph audit. No scheduler/solver/heat imports.

Run only after the unique continuation exits. --exit-code is its observed code.
Writes one new audit receipt; cannot overwrite an earlier audit.
"""
import argparse
from collections import Counter
from fractions import Fraction as F
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'research/chapter3_calibration_supplement/results'
NEW = BASE / 'remaining25_execution01'
OLD = BASE / 'supplement_execution01'
FREEZE = BASE / 'frozen_remaining25_01'
BETAS = ('1', '13/10', '8/5', '2')
OPPS = ('H', 'M', 'L')


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if Path(path).suffix == '.gz' else raw)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def direction(value):
    return 'improved' if value > 0 else 'worsened' if value < 0 else 'unchanged'


def graph(spec):
    nodes, edges = spec['nodes'], spec['edges']
    pred, succ = {n: set() for n in nodes}, {n: set() for n in nodes}
    require(len(pred) == len(nodes) and len({tuple(e) for e in edges}) == len(edges), 'GRAPH_IDENTITIES')
    for a, b in edges:
        require(a in pred and b in pred and a != b, 'GRAPH_EDGE')
        pred[b].add(a); succ[a].add(b)
    order, depths = [], {}
    while len(order) != len(nodes):
        ready = sorted(n for n in nodes if n not in depths and pred[n].issubset(depths))
        require(ready, 'GRAPH_CYCLE')
        for n in ready:
            depths[n] = 1 + max((depths[p] for p in pred[n]), default=0)
            order.append(n)
    reachable = {}
    for n in reversed(order):
        reachable[n] = set(succ[n])
        for k in succ[n]:
            reachable[n].update(reachable[k])
    incomparable = sum(a not in reachable[b] and b not in reachable[a]
                       for i, a in enumerate(nodes) for b in nodes[i + 1:])
    # Dilworth: width = |V| - maximum matching of the strict reachability relation.
    matched = {}
    def augment(a, seen):
        for b in sorted(reachable[a]):
            if b in seen:
                continue
            seen.add(b)
            if b not in matched or augment(matched[b], seen):
                matched[b] = a
                return True
        return False
    matching = sum(augment(a, set()) for a in nodes)
    return {'nodes': len(nodes), 'edges': len(edges), 'longest_path_nodes': max(depths.values()),
            'incomparable_pairs': incomparable, 'partial_order_width': len(nodes) - matching}


def metrics(raw, beta, opp, stats):
    checks = raw['reference']['checks'][opp]
    require(checks['state'] == 'TIME_STRUCTURAL_VALID', 'TIME_CHECK')
    releases = {s['id']: {r['id']: F(r['release_ms']) for r in s['requests']}
                for s in raw['workload']['time_contract']['scenarios']}
    deadlines = raw['deadlines'][beta]['requests']
    require(set(releases) == set(deadlines) == set(checks['completions_ms']), 'SCENE_COVERAGE')
    rows, scene_hits, request_hits, min_eta, arithmetic = {}, 0, 0, [], 0
    for sid, due_rows in deadlines.items():
        require(set(due_rows) == set(releases[sid]) == set(checks['completions_ms'][sid]), 'REQUEST_COVERAGE')
        rows[sid] = {}
        for rid, due_row in due_rows.items():
            due, release, relative = [F(due_row[k]) for k in ('deadline_ms', 'release_ms', 'relative_deadline_ms')]
            finish = F(checks['completions_ms'][sid][rid])
            require(release == releases[sid][rid] and due == release + relative and relative > 0, 'DUE_ARITHMETIC')
            slack, response = due - finish, finish - release
            eta, on_time = slack / relative, slack >= 0
            reported = stats['scenes'][sid]['requests'][rid]
            require((F(reported['slack_ms']), F(reported['response_ms']), F(reported['eta']), reported['on_time'])
                    == (slack, response, eta, on_time), 'METRIC_ARITHMETIC')
            rows[sid][rid] = {'slack': slack, 'response': response, 'eta': eta,
                              'on_time': on_time, 'relative': relative}
            request_hits += on_time; min_eta.append(eta); arithmetic += 1
        scene_hits += all(r['on_time'] for r in rows[sid].values())
    count = sum(map(len, rows.values()))
    require((stats['requests_on_time'], stats['request_count'], stats['scenes_on_time'], stats['scene_count'],
             stats['family_all_on_time'], F(stats['minimum_eta'])) ==
            (request_hits, count, scene_hits, len(rows), scene_hits == len(rows), min(min_eta)), 'METRIC_COUNTS')
    require(F(stats['maximum_lateness_ms']) == max(F(0), max(-r['slack'] for v in rows.values() for r in v.values())),
            'MAXIMUM_LATENESS')
    return rows, {'conditions': 1, 'families_on_time': int(scene_hits == len(rows)), 'scenes': len(rows),
                  'scenes_on_time': scene_hits, 'requests': count, 'requests_on_time': request_hits}, arithmetic


def pair(current, ref, reported):
    require(set(current) == set(ref), 'PAIR_SCENES')
    counts = {name: Counter(dict.fromkeys(('improved', 'unchanged', 'worsened'), 0))
              for name in ('families', 'scenes', 'requests', 'request_slacks')}
    for sid, rows in current.items():
        require(set(rows) == set(ref[sid]), 'PAIR_REQUESTS')
        sc = direction(int(all(r['on_time'] for r in rows.values())) - int(all(r['on_time'] for r in ref[sid].values())))
        counts['scenes'][sc] += 1
        require(reported['scenes'][sid]['all_on_time_change'] == sc, 'PAIR_SCENE_STATUS')
        for rid, row in rows.items():
            before = ref[sid][rid]
            require(row['relative'] == before['relative'], 'PAIR_RELATIVE_DEADLINE')
            status = direction(int(row['on_time']) - int(before['on_time']))
            delta = row['slack'] - before['slack']
            counts['requests'][status] += 1; counts['request_slacks'][direction(delta)] += 1
            rr = reported['scenes'][sid]['requests'][rid]
            require(rr['on_time_change'] == status and F(rr['slack_change_ms']) == delta and
                    F(rr['response_change_ms']) == row['response'] - before['response'] and
                    F(rr['eta_change']) == row['eta'] - before['eta'], 'PAIR_ARITHMETIC')
    c_family = all(r['on_time'] for rows in current.values() for r in rows.values())
    r_family = all(r['on_time'] for rows in ref.values() for r in rows.values())
    family_change = direction(int(c_family) - int(r_family))
    counts['families'][family_change] += 1
    require(reported['family_all_on_time_change'] == family_change, 'PAIR_FAMILY_STATUS')
    for key, out in (('scenes', 'scene_status_changes'), ('requests', 'request_status_changes'),
                     ('request_slacks', 'request_slack_changes')):
        require(dict(counts[key]) == reported[out], 'PAIR_TOTALS')
    return {k: dict(v) for k, v in counts.items()}


def audit(exit_code):
    plan, freeze = read(FREEZE / 'plan.json'), read(FREEZE / 'freeze.json')
    inventory = read(FREEZE / 'inventory.json')
    oldplan = read(BASE / 'frozen_supplement01/plan.json')
    oldbatch = read(OLD / 'batch_result.json')
    terminal = NEW / ('terminal_failure.json' if (NEW / 'terminal_failure.json').exists() else 'batch_result.json')
    batch = read(terminal)
    if batch['state'] == 'COMPLETE':
        require(exit_code == 0, 'COMPLETE_EXIT_CODE')
    else:
        require(exit_code != 0 and batch['state'].startswith('STOPPED_'), 'FAILURE_EXIT_CODE')
    require(digest(FREEZE / 'plan.json') == freeze['plan_sha256'] == batch['plan_sha256'], 'PLAN_BINDING')
    require(plan['calls'] == oldplan['calls'][3:], 'REMAINING_SUFFIX')
    require(oldbatch['state'] == 'STOPPED_EXCEPTION' and oldbatch['completed_conditions'] == 3, 'OLD_ACCOUNT')
    require([r['condition_id'] for r in batch['rows']] == [c['condition_id'] for c in plan['calls']], 'ROW_ORDER')
    require(batch['limits'] == plan['limits'] and batch['elapsed_s'] <= 1620, 'BATCH_LIMIT')
    approval, claim = read(NEW / 'approval.json'), read(FREEZE / 'execution_claim.json')
    require(approval['approved'] is True and approval['limits'] == plan['limits'] and
            approval['plan_sha256'] == freeze['plan_sha256'], 'APPROVAL')
    require(claim == read(ROOT / plan['consumption_claim_path']) and
            claim['approval_sha256'] == digest(NEW / 'approval.json'), 'CONSUMPTION')
    for rel, sha in {**freeze['protected_files'], **plan['source_files']}.items():
        require(digest(ROOT / rel) == sha, 'CURRENT_OR_PROTECTED_SOURCE:' + rel)
    for rel, sha in read(FREEZE / 'prior_history.json').items():
        require(digest(ROOT / rel) == sha, 'PRIOR_ARCHIVE:' + rel)
    current_source = plan['source_files']
    all_rows = [(OLD, oldplan, r) for r in oldbatch['rows'][:3]] + [(NEW, plan, r) for r in batch['rows']]
    sums, pairs, structures, shifts, windows, compact = {}, {}, {}, {}, {}, {}
    arithmetic, timetable_count, counters = 0, 0, Counter()
    for run, binding_plan, row in all_rows:
        if row['state'] != 'COMPLETE':
            continue
        cid = row['condition_id']; directory = run / cid
        receipt, call_claim = read(directory / 'result.json'), read(directory / 'call_claim.json')
        call = call_claim['call']; axis = call['axis']; scale = str(call['scale'])
        require(receipt['state'] == 'COMPLETE' and row['returncode'] == 0 and
                receipt['elapsed_s'] <= row['elapsed_s'] <= 60, 'CONDITION_STATE_OR_TIME')
        require(receipt['token'] == call_claim['token'] and receipt['condition'] == call, 'CONDITION_IDENTITY')
        require(receipt['source_files'] == binding_plan['source_files'], 'CONDITION_SOURCES')
        require(digest(directory / 'result.json') == row['result_sha256'], 'RESULT_HASH')
        for stem, file in (('evidence', 'evidence.json.gz'), ('workload', 'generated_workload.json.gz'), ('summary', 'summary.json')):
            require(digest(directory / file) == receipt[stem + '_sha256'], 'PAYLOAD_HASH')
        require(not receipt['denied_events'] and not receipt['denied_imports'] and receipt['beta_selected'] is None, 'SCOPE')
        evidence, summary = read(directory / 'evidence.json.gz'), read(directory / 'summary.json')
        require(evidence['workload'] == read(directory / 'generated_workload.json.gz') and summary == row['summary'], 'PAYLOAD_LINK')
        roles = {'branch_multi' if axis == 'S4' else 'staggered': evidence}
        archive_roles = [('branch_join' if axis == 'S4' else 'single', call['parent_id'])]
        archive_roles += (list(zip(('serial', 'layered'), call['comparison_ids'])) if axis == 'S4'
                          else [('synchronous', call['comparison_ids'][0])])
        for role, key in archive_roles:
            ref = inventory['archive_references'][key]['files']['evidence']
            require(digest(ROOT / ref['path']) == ref['sha256'], 'COMPARISON_HASH')
            roles[role] = read(ROOT / ref['path'])
        parent = roles['branch_join' if axis == 'S4' else 'single']
        require(evidence['workload']['time_contract']['stage_profiles'] == parent['workload']['time_contract']['stage_profiles'],
                'PROFILES_UNCHANGED')
        require(evidence['reference']['mapping_origin_hash'] == parent['reference']['mapping_origin_hash'], 'MAPPING_ORIGIN')
        counters.update(receipt['counters'])
        timetable_count += sum(len(c['completions_ms']) for c in evidence['reference']['checks'].values())
        structures[cid] = {}
        for role, raw in roles.items():
            structures[cid][role] = {}
            for app, spec in raw['workload']['applications'].items():
                gs = graph(spec); structures[cid][role][app] = gs
                reported = summary['structure_by_role'][role]['applications'][app]
                require(all(reported[k] == gs[k] for k in reported), 'STRUCTURE_REPORT')
                if role == 'branch_multi':
                    ns = spec['nodes']; edges = []
                    if len(ns) == 2:
                        edges = [[ns[0], ns[1]]]
                    else:
                        require(len(ns) % 4 == 0, 'DIAMOND_SIZE')
                        for j in range(0, len(ns), 4):
                            a,b,c,d = ns[j:j+4]
                            edges += [[a,b],[a,c],[b,d],[c,d]]
                            if j:
                                edges += [[ns[j-1],a]]
                    require(sorted(edges) == spec['edges'], 'DIAMOND_EDGES')
                    require(gs['partial_order_width'] == (1 if len(ns) == 2 else 2), 'DIAMOND_WIDTH')
        if axis == 'S7':
            shifts[cid] = {}
            originals = {s['id']: s for s in parent['workload']['time_contract']['scenarios']}
            for scene in evidence['workload']['time_contract']['scenarios']:
                sid=scene['id']; refs=originals[sid]; reqs={r['id']:r for r in scene['requests']}
                finish=max(F(x) for x in parent['reference']['checks']['H']['completions_ms'][sid].values())
                shift=5*(-(-(finish/F(2))//5))
                require(F(evidence['workload']['transform']['scene_shifts_ms'][sid]) == shift, 'STAGGER_SHIFT')
                shifts[cid][sid]=str(shift)
                for req in refs['requests']:
                    require(reqs[req['id']] == req, 'ORIGINAL_RELEASE')
                    require(F(reqs[req['id'][:-1]+'2']['release_ms']) == F(req['release_ms'])+shift, 'SECOND_RELEASE')
        windows[cid] = {}; compact[cid] = {}
        for beta in BETAS:
            wr=evidence['window_receipts'][beta]
            latest=max(F(r['deadline_ms']) for role in wr['members'] for rows in roles[role]['deadlines'][beta]['requests'].values() for r in rows.values())
            win=5*(-(-latest//5))
            require(F(wr['latest_deadline_ms'])==latest and F(wr['window_ms'])==win, 'WINDOW_RULE')
            require({F(m['window_ms']) for m in wr['members'].values()}=={win}, 'COMMON_WINDOW')
            windows[cid][beta]=str(win)
            for opp in OPPS:
                computed={}; compact_row={}
                for role, raw in roles.items():
                    stats=summary['by_beta'][beta][opp]['roles'][role]
                    rr, total, count=metrics(raw,beta,opp,stats); computed[role]=rr; arithmetic+=count
                    for group in ('all',scale):
                        key='|'.join((axis,group,beta,opp,role)); sums.setdefault(key,Counter()).update(total)
                    compact_row[role]=total
                for role, reported in summary['by_beta'][beta][opp]['paired'].items():
                    child='branch_multi' if axis=='S4' else 'staggered'
                    pc=pair(computed[child],computed[role],reported)
                    for group in ('all',scale):
                        key='|'.join((axis,group,beta,opp,role))
                        target=pairs.setdefault(key,{level:Counter() for level in pc})
                        for level, val in pc.items(): target[level].update(val)
                if beta=='13/10': compact[cid][opp]=compact_row
    require(counters['mapping_constructions']==counters['formal_method_calls']==counters['thermal_integrations']==0,'FORBIDDEN_COUNTS')
    expected=3+batch['completed_conditions']
    require(counters['timetable_constructions']==3*expected and len(compact)==expected,'COMPLETION_COUNTS')
    return {'state':'INDEPENDENT_READ_ONLY_AUDIT_PASS','observed_exit_code':exit_code,
            'old_execution':{k:oldbatch[k] for k in ('state','elapsed_s','completed_conditions','consumed_conditions')},
            'new_execution':{k:batch[k] for k in ('state','elapsed_s','completed_conditions','consumed_conditions')},
            'combined_complete_conditions':expected,'exact_request_arithmetic_checks':arithmetic,
            'family_timetables':counters['timetable_constructions'],'scenario_schedules':timetable_count,
            'aggregate_counts':{k:dict(v) for k,v in sums.items()},
            'aggregate_pairs':{k:{a:dict(b) for a,b in v.items()} for k,v in pairs.items()},
            'structure':structures,'stagger_shifts_ms':shifts,'windows_ms':windows,'beta_1_3_conditions':compact,
            'source_files_verified':len(current_source),'protected_files_verified':len(freeze['protected_files']),
            'prior_archive_files_verified':len(read(FREEZE/'prior_history.json')),
            'read_only_scope':'stdlib file reads, exact arithmetic, dependency graph analysis; no schedule construction, optimization or thermal integration',
            'new_reference_calls':0,'new_thermal_calls':0,'audit_source_sha256':digest(Path(__file__)),
            'evidence_hashes':{str(path.relative_to(ROOT)).replace('\\','/'):digest(path)
                               for run in (OLD,NEW) for path in sorted(run.rglob('*')) if path.is_file()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--exit-code',type=int,required=True)
    args=parser.parse_args(); result=audit(args.exit_code)
    output=Path(__file__).with_suffix('.json')
    with output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2); handle.write('\n')
    print(json.dumps({k:result[k] for k in ('state','combined_complete_conditions','exact_request_arithmetic_checks','family_timetables','scenario_schedules')},ensure_ascii=False))
