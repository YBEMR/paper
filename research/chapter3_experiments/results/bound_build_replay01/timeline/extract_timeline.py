"""K171: stdlib-only historical U-at-build ledger replay; no scientific imports."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
RESULTS = ROOT / 'research/chapter3_experiments/results'
CANON = dict(ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(json.dumps(value, **CANON).encode('utf-8')).hexdigest()


def filehash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def q(value):
    return Fraction(str(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def extract():
    watched = {}
    checks = []

    def read(path):
        watched[relative(path)] = filehash(path)
        return json.loads(path.read_text(encoding='utf-8'))

    def source(name):
        folder = RESULTS / 'p0_batch_preparation01/source_snapshot/research'
        path = folder / ('v1_evaluator/interval.py' if name == 'interval.py'
                         else 'chapter3_experiments/' + name)
        require(path.is_file(), 'missing original source: ' + str(path))
        watched[relative(path)] = filehash(path)
        return path

    source_paths = {name: source(name) for name in (
        'linked_method.py', 'neighborhood_method.py', 'scene_adapter.py',
        'build_observer.py', 'timing.py', 'schedules.py', 'thermal.py',
        'start_domain.py', 'interval.py', 'control_policy.py')}
    cases = []
    for index in range(1, 6):
        base = RESULTS / ('p0_execution01' if index == 1 else 'p0_resume01')
        folder = base / 'calls' / ('base__R' + str(index)) / 'anchor_linked4'
        result = read(folder / 'result.json')
        raw = read(folder / 'wrapper_raw_result.json')
        instance = read(folder / 'input_instance.json')
        config = read(folder / 'input_config.json')
        require(result == raw, 'result/raw disagreement')
        identity = result['identity']
        require(identity['full_input_sha256'] == digest(instance), 'input hash')
        require(identity['config_sha256'] == digest(config), 'config hash')
        require(result['timing']['limit_s'] == 300, 'budget limit')
        require(result['state'] == 'SAFE' and result['rankable_energy'], 'historical final SAFE')
        order = result['original_scene_order']
        scene_map = {s['id']: s for s in instance['scenarios']}
        require(order == list(scene_map), 'scene order')
        weights = {sid: q(scene_map[sid]['weight']) for sid in order}
        aggs = result['aggregation_attempts']
        budget_id = aggs[0]['identity']['budget']
        require(q(budget_id['seconds']) == 300, 'receipt budget limit')

        def receipt_common(receipt, candidate, *, sid=None):
            require(receipt['state'] == 'SAFE' and receipt['rankable_energy'], 'not SAFE receipt')
            require(receipt['receipt_sha256'] == digest({k: v for k, v in receipt.items()
                                                       if k != 'receipt_sha256'}), 'receipt hash')
            ident = receipt['identity']
            require(ident['full_input_sha256'] == identity['full_input_sha256'], 'receipt input')
            require(ident['budget'] == budget_id, 'mixed method budget')
            require(ident['candidate_sha256'] == digest(candidate), 'receipt candidate')
            require(ident['shared_deployment_sha256'] == digest(result['shared_deployment']),
                    'receipt shared deployment')
            require(ident['platform_sha256'] == digest(instance['platform']), 'receipt platform')
            require(ident['execution_rules_sha256'] == digest(instance['execution_rules']), 'receipt rules')
            require(ident['accuracy_sha256'] == identity['accuracy_sha256'], 'receipt accuracy')
            require(ident['control_policy'] == result['control_policy'] == 'auto_low_immediate_v1',
                    'receipt policy')
            require(all(ident['source_sha256'][name] == filehash(source_paths[name])
                        for name in ident['source_sha256']), 'receipt original source')
            require(0 <= q(receipt['completed_at_elapsed_s']) < 300, 'receipt time')
            require(receipt['shared_deployment'] == result['shared_deployment'], 'receipt shared units')
            if sid is not None:
                require(receipt['scenario_id'] == ident['scenario_id'] == sid, 'scene id')
                require(ident['scenario_sha256'] == digest(scene_map[sid]), 'scene input')
                require(ident['entry_sha256'] == digest(scene_map[sid]['entry']), 'scene entry')
                require(receipt['unweighted'] is True, 'local energy already weighted')
                physical = receipt['result']
                require(physical['state'] == 'SAFE' and physical['complete'] is True
                        and physical['rankable_energy'] is True
                        and physical['energy_accuracy_met'] is True, 'incomplete physical SAFE')
                require(physical['scene_id'] == sid
                        and q(physical['covered_until_s']) == q(instance['window_ms']) / 1000,
                        'incomplete scene/window')
                require(physical['energy_J'] == receipt['energy_J']
                        and q(receipt['safe_upper_bound_J']) == q(receipt['energy_J'][1]), 'local energy')
                require(0 <= q(physical['completed_at_elapsed_s']) <=
                        q(receipt['completed_at_elapsed_s']), 'physical receipt time')

        valid_aggs = []
        for ai, agg in enumerate(aggs):
            receipt_common(agg, agg['safe_candidate'])
            require(set(agg['scenes']) == set(order)
                    and set(agg['safe_candidate']['scenes']) == set(order), 'all scenes required')
            require(not agg['receipt_errors'] and not agg['violations']
                    and agg['deployment_feasibility'] == 'ALL_SCENES_SAFE_WITNESS', 'aggregate admission')
            require(agg['legality']['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED', 'aggregate legality')
            sums = [Fraction(0), Fraction(0)]
            scene_facts = {}
            for sid in order:
                rec = agg['scenes'][sid]
                local = {'scenes': {sid: agg['safe_candidate']['scenes'][sid]}}
                receipt_common(rec, local, sid=sid)
                require(q(rec['completed_at_elapsed_s']) <= q(agg['completed_at_elapsed_s']),
                        'scene formed after aggregate')
                for j in (0, 1):
                    sums[j] += weights[sid] * q(rec['energy_J'][j])
                scene_facts[sid] = {
                    'receipt_sha256': rec['receipt_sha256'],
                    'candidate_sha256': rec['identity']['candidate_sha256'],
                    'completed_at_s': rec['completed_at_elapsed_s'],
                    'energy_J': rec['energy_J'],
                    'safe_upper_bound_J': rec['safe_upper_bound_J'],
                }
            # Original interval operations outward-round; exact endpoints must be enclosed.
            require(q(agg['weighted_energy_J'][0]) <= sums[0] <= sums[1]
                    <= q(agg['weighted_energy_J'][1]) == q(agg['safe_upper_bound_J']),
                    'weighted full aggregate energy')
            valid_aggs.append({'aggregation_index': ai, 'receipt_sha256': agg['receipt_sha256'],
                'candidate_sha256': agg['identity']['candidate_sha256'],
                'formed_at_s': agg['completed_at_elapsed_s'],
                'safe_upper_bound_J': agg['safe_upper_bound_J'], 'scene_receipts': scene_facts,
                'exact_fraction_weighted_scene_endpoints_J': [str(value) for value in sums],
                'outward_rounding_upper_slack_J': str(q(agg['safe_upper_bound_J']) - sums[1])})

        updates = []
        previous_u = None
        for ui, update in enumerate(result['global_updates']):
            matches = [a for a in valid_aggs if a['safe_upper_bound_J'] == update['safe_upper_bound_J']
                       and a['formed_at_s'] == update['committed_at_s']]
            require(len(matches) == 1, 'global update has no unique complete aggregate')
            agg = matches[0]
            require(q(update['committed_at_s']) <= q(update['transferred_at_s'])
                    <= q(update['observer_completed_at_s']) < 300, 'update publication order')
            if previous_u is not None:
                require(q(update['safe_upper_bound_J']) < previous_u, 'updates not strictly improving')
            previous_u = q(update['safe_upper_bound_J'])
            updates.append(dict(agg, case_id=instance['id'], input_sha256=identity['full_input_sha256'],
                call_directory=relative(folder), state='SAFE', complete_global=True, evidence_verified=True,
                upper_J=agg['safe_upper_bound_J'],
                committed_at_s=update['committed_at_s'], source_update_index=ui,
                source_aggregation_index=agg['aggregation_index'],
                update_index=ui, phase_index=update['phase_index'],
                trigger_scene=update['trigger_scene'], trigger_source=update['trigger_source'],
                scene_sources=update['scene_sources'], transferred_at_s=update['transferred_at_s'],
                observer_completed_at_s=update['observer_completed_at_s'],
                available_by_s=max(update['committed_at_s'], update['transferred_at_s'],
                                   update['observer_completed_at_s']),
                provenance='COMPLETE_FRESH_SEED' if update['phase_index'] == 0
                           else 'COMPLETE_ORIGINAL_INPUT_MERGED_SAFE'))
        seed = result['seed_attempts'][0]
        require(seed['state'] == 'SAFE' and seed['reason'] == 'COMPLETE_SAFE_SEED'
                and seed['aggregation'] == aggs[updates[0]['aggregation_index']], 'fresh seed binding')
        require(seed['scene_evaluations'] == seed['aggregation']['scenes'], 'seed all-scene receipts')

        frames = [p for p in result['timing']['phase_records'] if p['phase'] == 'model_construction']
        require(len(frames) == 4 and len(result['phases']) == 2, 'four historical builds required')
        builds = []
        for bi, frame in enumerate(frames):
            phase_no, scene_index = divmod(bi, len(order))
            phase = result['phases'][phase_no]
            sid = order[scene_index]
            phase_folder = folder if phase_no == 0 else folder / 'pass_02'
            log_path = phase_folder / ('build_scene_%03d.jsonl' % scene_index)
            watched[relative(log_path)] = filehash(log_path)
            log = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
            initial_path = phase_folder / ('initial_scene_%03d.json' % scene_index)
            initial = read(initial_path)
            scene_record = phase['scenes'][sid]
            start, end = q(frame['start_s']), q(frame['end_s'])
            require(start <= q(log[0]['method_elapsed_seconds']) <=
                    q(log[-1]['method_elapsed_seconds']) <= end, 'build log/frame time containment')
            require(log[-1]['status'] == 'MODEL_CONSTRUCTED'
                    and scene_record['model_complete'] is True, 'build completion')
            require(q(scene_record['model_completed_at_s']) <= end
                    and q(scene_record['model_completed_at_s']) >=
                    q(log[-1]['method_elapsed_seconds']), 'model timestamp/frame')
            require(initial == scene_record['initialisation'], 'initial file/phase binding')
            eligible = [u for u in updates if q(u['available_by_s']) < start]
            require(eligible, 'no provably available complete U')
            chosen = min(eligible, key=lambda u: q(u['safe_upper_bound_J']))
            warm_hash = initial['snapshot_candidate_sha256']
            if phase_no:
                require(warm_hash == chosen['candidate_sha256'], 'phase2 latest committed warm binding')
                expected_candidate = aggs[chosen['aggregation_index']]['safe_candidate']
            else:
                require(initial['source'] == 'initial_constructor' and warm_hash is None,
                        'first pass fresh constructor source')
                expected_candidate = seed['aggregation']['safe_candidate']
            require(initial['candidate'] == {'scenes': {sid: expected_candidate['scenes'][sid]}},
                    'initial per-scene candidate/complete generation binding')
            builds.append({
                'build_index': bi, 'phase_index': phase['phase_index'], 'phase_name': phase['name'],
                'case_id': instance['id'], 'scene_id': sid,
                'build_started_at_s': frame['start_s'], 'build_ended_at_s': frame['end_s'],
                'root_start_s': frame['start_s'], 'root_end_s': frame['end_s'],
                'duration_s': frame['wall_s'],
                'root_monotonic_start_exact_s': str(q(budget_id['start']) + start),
                'root_monotonic_end_exact_s': str(q(budget_id['start']) + end),
                'first_progress_s': log[0]['method_elapsed_seconds'],
                'final_progress_s': log[-1]['method_elapsed_seconds'],
                'model_completed_at_s': scene_record['model_completed_at_s'],
                'build_log': relative(log_path), 'initial_scene_file': relative(initial_path),
                'initial_scene_completed_at_s': initial['completed_at_s'],
                'condition_sha256': phase['condition_sha256'],
                'initial_source': initial['source'], 'warm_snapshot_sha256': warm_hash,
                'timeline_status': 'RESOLVED_COMPLETE_SAME_CALL_U_BEFORE_BUILD',
                'available_safe_upper_bound_J': chosen['safe_upper_bound_J'],
                'eligible_update_indices': [u['update_index'] for u in eligible],
                'chosen_update_index': chosen['update_index'],
                'chosen_aggregation_index': chosen['aggregation_index'],
                'chosen_candidate_sha256': chosen['candidate_sha256'],
                'chosen_receipt_sha256': chosen['receipt_sha256'],
                'chosen_U_available_by_s': chosen['available_by_s'],
                'chosen_provenance': chosen['provenance'],
                'timely_upper': chosen,
                'scene_receipts_in_complete_U': chosen['scene_receipts'],
                'not_available_at_build_update_indices': [u['update_index'] for u in updates
                                                          if q(u['available_by_s']) >= start],
                'final_U_not_backfilled': result['safe_upper_bound_J'] != chosen['safe_upper_bound_J'],
            })

        phase_summaries = []
        for ph in result['phases']:
            eligible = [u for u in updates if q(u['available_by_s']) <= q(ph['completed_at_s'])]
            best = min(eligible, key=lambda u: q(u['safe_upper_bound_J']))
            phase_summaries.append({'phase_index': ph['phase_index'], 'started_at_s': ph['started_at_s'],
                'completed_at_s': ph['completed_at_s'], 'best_U_at_phase_end_J': best['safe_upper_bound_J'],
                'best_update_index': best['update_index'],
                'not_a_license_to_use_at_earlier_builds': True})
        local_only = []
        for sid, sc in result['scenes'].items():
            for ei, evaluation in enumerate(sc.get('original_scene_evaluations', [])):
                rec = evaluation.get('receipt')
                if not rec or rec.get('state') != 'SAFE':
                    continue
                local_only.append({'scene_id': sid, 'evaluation_index': ei,
                    'source': evaluation['source'], 'receipt_sha256': rec['receipt_sha256'],
                    'completed_at_s': rec['completed_at_elapsed_s'],
                    'unweighted_scene_U_J': rec['safe_upper_bound_J'],
                    'appears_in_aggregation_indices': [a['aggregation_index'] for a in valid_aggs
                        if a['scene_receipts'][sid]['receipt_sha256'] == rec['receipt_sha256']],
                    'alone_is_not_full_weighted_U': True})
        contract = result['linked_record_contract']
        frozen = [u for u in updates if u['phase_index'] <= 1][-1]
        require(contract['closed_anchor_candidate_sha256'] == frozen['candidate_sha256']
                and contract['closed_anchor_committed_at_s'] == frozen['formed_at_s'], 'closed anchor binding')
        condition = result['phases'][1]['condition']
        frozen_agg = aggs[frozen['aggregation_index']]
        require(condition['warm_candidate'] == frozen_agg['safe_candidate']
                and condition['warm_receipt'] == frozen_agg
                and condition['warm_candidate_sha256'] == frozen['candidate_sha256']
                and condition['warm_receipt_sha256'] == frozen['receipt_sha256'],
                'phase2 condition warm receipt/full first-pass SAFE binding')
        checks.append({'case': instance['id'], 'status': 'PASS', 'builds': len(builds),
                       'validated_complete_updates': len(updates), 'result_equals_wrapper_raw': True})
        cases.append({'problem_id': instance['id'], 'result_path': relative(folder / 'result.json'),
            'wrapper_raw_path': relative(folder / 'wrapper_raw_result.json'),
            'input_path': relative(folder / 'input_instance.json'),
            'input_sha256': identity['full_input_sha256'], 'budget_identity': budget_id,
            'clock_origin': result['timing']['clock_origin'], 'limit_s': result['timing']['limit_s'],
            'method_elapsed_s': result['timing']['method_elapsed_s'],
            'complete_updates': updates, 'builds': builds, 'phase_end_best': phase_summaries,
            'verified_updates': updates,
            'scene_local_receipts_not_directly_usable_as_full_U': local_only,
            'closed_anchor': {'update_index': frozen['update_index'],
                'candidate_sha256': contract['closed_anchor_candidate_sha256'],
                'formed_at_s': contract['closed_anchor_committed_at_s'],
                'phase2_condition_warm_receipt_sha256': condition['warm_receipt_sha256'],
                'phase2_condition_warm_receipt_equals_original_aggregate': True,
                'safe_upper_bound_J': frozen['safe_upper_bound_J'],
                'frozen_for_both_phase2_models': True,
                'distinct_from_latest_complete_U_at_phase2_AC_build':
                    frozen['candidate_sha256'] != builds[3]['chosen_candidate_sha256']},
            'final_U_J_for_comparison_only': result['safe_upper_bound_J']})

    require(all(filehash(ROOT / p) == sha for p, sha in watched.items()), 'original evidence changed')
    loaded = [name for name in sys.modules if name.split('.')[0] in {
        'numpy', 'scipy', 'milp', 'thermal', 'formal_milp', 'linked_method', 'scene_adapter', 'matlab_bridge'}]
    require(not loaded, 'scientific modules imported')
    return {'schema': 'K171_same_call_complete_U_at_build_readonly_v1',
        'status': 'PASS', 'research_calls': 0, 'thermal_integrations': 0, 'model_builds': 0,
        'scientific_modules_loaded': loaded, 'all_read_originals_unchanged': True,
        'availability_rule': 'matching complete original-input aggregate and publication/observer completion all strictly precede model_construction phase start',
        'timing_rule': 'phase_records start/end are exact recorded root-relative intervals; first/last progress logs corroborate but do not define build start',
        'safety_scope': 'replay of historical complete SAFE receipts; no new thermal proof or production pruning',
        'checks': checks, 'cases': cases, 'original_file_sha256': watched,
        'extractor_sha256': filehash(Path(__file__))}


def render(facts):
    lines = ['# K171：实际构模前的同次安全U时间线', '',
        '5题共20次实际构模，全部找到构模开始前已经完整接纳并发布的同次安全U。第一阶段两次构模均只能使用fresh seed；第二阶段AB使用第一阶段末完整U，AC仅R3仍沿用该U，其余4题可用第二阶段AB已合并的新U。不能用方法最终U回填。', '',
        '| 题目 | 构模 | 根时钟区间/s | 构模前可用完整U/J | 来源 |', '|---|---|---:|---:|---|']
    for case in facts['cases']:
        for build in case['builds']:
            lines.append('| %s | P%d %s | %.3f—%.3f | %.12f | update%d／agg%d，%s |' % (
                case['problem_id'], build['phase_index'], build['scene_id'].split('_')[0],
                build['root_start_s'], build['root_end_s'], float(build['available_safe_upper_bound_J']),
                build['chosen_update_index'], build['chosen_aggregation_index'], build['chosen_provenance']))
    lines += ['', '## 证据规则', '',
        '- 根时钟零点为linked入口lazy imports之前。同一budget token/start/300秒贯穿fresh seed、两阶段、两个场景。事实文件同时给出原始monotonic绝对时间的精确有理数。',
        '- 构模区间取`timing.phase_records[phase=model_construction]`，按原始phase及场景顺序绑定。`build_scene`首条可能晚于真正开始，末条及`model_completed_at_s`可能早于phase退出，均单列保留。',
        '- 每个U均绑定唯一`global_updates`与`aggregation_attempts`；逐项核对完整AB/AC、原输入、候选、同次预算、源hash、receipt hash、窗口覆盖及加权能量包络。可用时刻保守取formed／transferred／observer completed的最大值，严格早于build开始。',
        '- 单场景SAFE只证明该场景；即使已经形成，也不直接当完整加权U。事实文件保留其是否进入完整aggregate的索引。',
        '- phase末最佳只用于核对；phase2固定闭锚来自第一阶段末完整SAFE。phase2 AC启动点可来自更晚的完整合并，不等于闭锚被更新。',
        '- 结果与wrapper_raw逐对象相等；所有读取原件前后hash一致。本脚本仅stdlib读取及算术，不调用生产函数、构模、优化或热积分。', '',
        '## 供主回放使用的字段', '',
        '`facts.json → cases[].builds[]`保存准确起止、可用U、chosen_update_index／chosen_aggregation_index、完整候选hash及各场景receipt／能量。主回放必须使用该build的U，不能读取`final_U_J_for_comparison_only`替代。', '',
        '## 源码定位', '',
        '- `neighborhood_method.py:183—247`：完整aggregate提交与global_updates／snapshot／observer。',
        '- `neighborhood_method.py:339—343`：单场景更新后另行完整聚合。',
        '- `neighborhood_method.py:345—396`：BuildObserver、model_construction及initial_scene记录。',
        '- `neighborhood_method.py:604—620`：第一阶段先构造两个场景，再进入求解。',
        '- `neighborhood_method.py:638—688`：第二阶段清除未提交局部代、逐场景取latest完整snapshot后构模。',
        '- `linked_method.py:91—127`：只捕获完整第一阶段SAFE，第二阶段一次冻结闭锚。',
        '- `scene_adapter.py:493—607`：单场景完整能量要求与全场景聚合身份／预算／能量接纳。',
        '以上行号均以facts绑定的P0准备源码快照为准。', '',
        '本回放只证明U当时已可用；不证明下界实际删项、构模/求解加速或新的节能收益。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    facts = extract()
    text = json.dumps(facts, ensure_ascii=False, indent=2) + '\n'
    if args.check_only:
        require((OUT / 'facts.json').read_text(encoding='utf-8') == text, 'facts replay changed')
        require((OUT / 'summary.md').read_text(encoding='utf-8') == render(facts), 'summary replay changed')
    else:
        (OUT / 'facts.json').write_text(text, encoding='utf-8')
        (OUT / 'summary.md').write_text(render(facts), encoding='utf-8')
    print(json.dumps({'status': facts['status'], 'cases': len(facts['cases']),
        'builds': sum(len(c['builds']) for c in facts['cases']),
        'complete_updates': sum(len(c['complete_updates']) for c in facts['cases']),
        'read_original_files': len(facts['original_file_sha256']), 'research_calls': 0,
        'facts_sha256': filehash(OUT / 'facts.json'), 'check_only': args.check_only}))


if __name__ == '__main__':
    main()
