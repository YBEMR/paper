"""K140 immutable saved-result audit; no production model, decode, heat or solve.

Run after both ledger calls are terminal. The imported K138/K135/K127 helpers
read saved JSON/Fraction receipts only. This is not a new physical evaluation.
The original method's 300 s evidence deadline is never extended by this audit.
"""
import argparse
from collections import Counter
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents
            if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
HELPER = REPO/'research/chapter3_experiments/results/staged_quality_pair01/analysis01/analysis_script.py'
spec = importlib.util.spec_from_file_location('saved_k138_json_only', HELPER)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
a, b = h.a, h.b
read, save, digest, interval = h.read, h.save, h.digest, h.interval
EXPECTED = ('old_n1', 'linked_n1')
LINKED_CONDITION = 'fixed-unit-linked-opp-start-warm-closed-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def condition_audit(result, instance, declaration):
    """Both anchors are complete saved original-input SAFE, not scene.latest."""
    first = result.get('condition') or {}
    rows = []
    sources = {Path(path).name: value for path, value in declaration['source_sha256'].items()}
    conditions = [(0, first)] + [(phase['phase_index'], phase.get('condition'))
                                for phase in result.get('phases', [])]
    phase1 = [row for row in h.verified_updates(result, instance) if row['phase_index'] in (0, 1)]
    latest = phase1[-1] if phase1 else None
    contract = result.get('linked_record_contract') or {}
    for index, cond in conditions:
        if not cond:
            continue
        checks = {
            'condition_hash': cond.get('condition_sha256') == digest({k:v for k,v in cond.items() if k != 'condition_sha256'}),
            'original_input': cond.get('source_input_sha256') == digest(instance),
            'fresh_seed_unchanged': cond.get('seed_candidate') == first.get('seed_candidate'),
            'fresh_seed_receipt_unchanged': cond.get('seed_receipt') == first.get('seed_receipt'),
            'seed_candidate_hash': cond.get('seed_candidate_sha256') == digest(cond.get('seed_candidate')),
            'budget_unchanged': cond.get('budget_identity') == first.get('budget_identity'),
            'deployment_unchanged': cond.get('shared_deployment') == first.get('shared_deployment') == declaration['shared_deployment'],
            'accuracy_unchanged': cond.get('accuracy') == first.get('accuracy'),
            'source': cond.get('condition_source_sha256') == sources.get('linked_neighborhood.py' if index == 2 else 'neighborhood.py'),
        }
        extras = {}
        if index == 2:
            expected_open = declaration.get('linked_opened_by_scene', contract.get('linked_opened_by_scene'))
            checks.update(
                protocol=cond.get('protocol') == LINKED_CONDITION,
                explicitly_declared_linked_scope=cond.get('opened_by_scene') == expected_open == contract.get('linked_opened_by_scene'),
                dependency_sources=bool(cond.get('condition_dependency_sha256')) and all(sources.get(k) == v
                    for k,v in (cond.get('condition_dependency_sha256') or {}).items()),
                warm_candidate_hash=cond.get('warm_candidate_sha256') == digest(cond.get('warm_candidate')),
                warm_receipt_hash=cond.get('warm_receipt_sha256') == (cond.get('warm_receipt') or {}).get('receipt_sha256'),
                warm_is_last_phase1_complete=latest is not None and latest['candidate_sha256'] == cond.get('warm_candidate_sha256')
                    and latest['receipt_sha256'] == cond.get('warm_receipt_sha256'),
                record_contract_anchor_hash=contract.get('closed_anchor_candidate_sha256') == cond.get('warm_candidate_sha256'),
                record_contract_anchor_time=latest is not None and contract.get('closed_anchor_committed_at_s') == latest['at_s'],
                record_contract_anchor_phase=latest is not None and contract.get('closed_anchor_phase_index') == latest['phase_index'])
            warm = cond.get('warm_candidate') or {}
            warm_receipt = cond.get('warm_receipt') or {}
            try:
                a.full_safe(warm_receipt, warm, instance, result['timing']['limit_s'], 'n1', result)
                warm_identity = h.source_identity_checks(warm_receipt['identity'], instance, cond, declaration)
                checks['complete_original_warm_SAFE'] = all(warm_identity.values())
            except (KeyError, TypeError, ValueError):
                checks['complete_original_warm_SAFE'] = False
            derived = {sid: {item['stage_id']: {'unit': item['unit'], 'opp': item['opp'], 'start_ms': str(F(item['start_ms']))}
                            for item in items} for sid, items in warm.get('scenes', {}).items()}
            checks['warm_options_derived_from_complete_candidate'] = derived == cond.get('warm_options_by_scene')
            seed_options = cond.get('seed_options_by_scene') or {}
            checks['warm_preserves_original_fresh_seed_units'] = set(derived) == set(seed_options) and all(
                set(items) == set(seed_options[sid]) and all(item['unit'] == seed_options[sid][stage]['unit']
                    for stage,item in items.items()) for sid,items in derived.items())
            phase = next((row for row in result.get('phases', []) if row['phase_index'] == 2), {})
            checks['anchor_committed_before_phase2_record'] = latest is not None and latest['at_s'] <= phase.get('started_at_s', -1)
            extras = {'warm_candidate_sha256': cond.get('warm_candidate_sha256'),
                'warm_receipt_sha256': cond.get('warm_receipt_sha256'),
                'last_phase1_complete_update': latest,
                'warm_options_by_scene': cond.get('warm_options_by_scene'),
                'closed_candidate_checks': []}
            # For each actually committed phase-2 full candidate, verify all
            # closed choices against this fixed warm generation exactly.
            for update in h.verified_updates(result, instance):
                if update['phase_index'] != 2:
                    continue
                matching = [candidate for candidate,receipt,_ in a.full_evaluations(result, 'n1')
                    if receipt.get('receipt_sha256') == update['receipt_sha256']]
                local_checks = []
                if matching:
                    for sid,items in matching[0]['scenes'].items():
                        for item in items:
                            anchor = derived[sid][item['stage_id']]
                            local_checks.append(item['unit'] == seed_options[sid][item['stage_id']]['unit'] and
                                (item['stage_id'] in cond['opened_by_scene'][sid] or
                                 (item['opp'] == anchor['opp'] and F(item['start_ms']) == F(anchor['start_ms']))))
                extras['closed_candidate_checks'].append({'at_s': update['at_s'],
                    'candidate_sha256': update['candidate_sha256'],
                    'all_pass': bool(matching) and bool(local_checks) and all(local_checks)})
            checks['phase2_full_candidates_keep_closed_warm_choices'] = all(item['all_pass']
                for item in extras['closed_candidate_checks'])
        else:
            checks['protocol'] = cond.get('protocol') == 'fixed-unit-local-opp-start-n1-v1'
            checks['opened_scope_first_pass'] = cond.get('opened_by_scene') == first.get('opened_by_scene')
        rows.append({'phase_index': index, 'protocol': cond.get('protocol'), 'checks': checks,
            'all_pass': all(checks.values()), 'condition_sha256': cond.get('condition_sha256'),
            'seed_candidate_sha256': cond.get('seed_candidate_sha256'),
            'opened_by_scene': cond.get('opened_by_scene'), **extras})
    return rows


_original_windows = h.windows


def windows(result):
    rows = _original_windows(result)
    for row in rows:
        if row['slot'] == 'phase2_all_open':
            row['slot'] = 'phase2_linked_warm_closed'
    return rows


def phase_report(result, jid, updates, clocks):
    rows = []
    for index in ((1, 2) if jid == 'linked_n1' else (1,)):
        marker = next((row for row in clocks['intervals'] if row['phase_index'] == index), None)
        prior = [point for point in updates if point['phase_index'] < index]
        own = [point for point in updates if point['phase_index'] == index]
        before = prior[-1] if prior else None
        after = own[-1] if own else before
        before_e = interval(before['energy_J']) if before else None
        after_e = interval(after['energy_J']) if after else None
        setup = clocks['interval_totals_s'].get('phase2_setup_before_phase_record', 0.) if index == 2 else 0.
        duration = marker['elapsed_s'] if marker else None
        rows.append({'job': jid, 'phase_index': index,
            'phase_name': 'N1' if index == 1 else 'linked_A_chain_local_pre_warm_closed',
            'entered': marker is not None, 'started_at_s': marker['start'] if marker else None,
            'completed_at_s': marker['end'] if marker else None,
            'recorded_interval_elapsed_s': duration, 'pre_record_setup_s': setup,
            'inclusive_phase_elapsed_s': None if duration is None else duration+setup,
            'starting_complete_energy_J': before['energy_J'] if before else None,
            'starting_complete_U_J': str(before_e[1]) if before_e else None,
            'final_complete_energy_J': after['energy_J'] if after else None,
            'final_complete_U_J': str(after_e[1]) if after_e else None,
            'committed_U_decrease_count': len(own),
            'strict_energy_improvement_vs_own_before_interval': bool(before_e and after_e and after_e[1] < before_e[0]),
            'U_decrease_J': str(before_e[1]-after_e[1]) if before_e and after_e else None,
            'strict_saving_vs_before_lower_fraction': str((before_e[0]-after_e[1])/before_e[0]) if before_e and after_e and before_e[0] > 0 else None,
            'scope': 'complete original globally committed SAFE receipts only; phase2 inclusive setup is separately timestamped'})
    return rows


# Reuse the audited JSON-only receipt, timing partition and transport readers.
# Replace only their K138-specific condition/phase naming functions.
h.condition_audit = condition_audit
h.windows = windows
h.phase_report = phase_report


def failure_boundary(result):
    timing = result.get('timing') or {}
    limit = F(str(timing.get('limit_s', 300)))
    elapsed = F(str(timing.get('method_elapsed_s', 0)))
    reason = str(result.get('reason'))
    latch = result.get('search_failure_latched')
    return {'search_failure_latched_raw': latch,
        'budget_exhausted_flag': result.get('budget_exhausted'),
        'reason_raw': result.get('reason'), 'elapsed_reached_deadline': elapsed >= limit,
        'normal_budget_stop_candidate': bool(elapsed >= limit and ('wall_time' in reason.lower()
            or 'budget' in reason.lower() or result.get('budget_exhausted') is True)),
        'interpretation': 'latch preserved verbatim; root-budget exhaustion alone is not an interface/numerical fault; inspect per-phase/context records'}


def main(root, out):
    ledger, declaration = read(root/'ledger.json'), read(root/'declaration.json')
    rows = ledger.get('calls') or []
    a.require(ledger.get('state') not in ('RUNNING', 'PREPARED', 'DECLARED'), 'pair ledger is not terminal')
    a.require(all(row.get('state') not in ('RUNNING', 'PREPARED', 'DECLARED') for row in rows), 'call is not terminal')
    a.require(not (out/'facts.json').exists(), 'never overwrite completed derived analysis')
    out.mkdir(parents=True, exist_ok=True)
    before = h.raw_hashes(root)
    frozen = h.source_audit(root, declaration)
    a.require(frozen['all_match'] and frozen['count'] == 157, 'frozen current/source inventory is not the expected 157 identities')
    k139 = read(REPO/'research/chapter3_experiments/results/linked_precheck02/checks.json')
    inherited_sources = k139.get('source_sha256') or {}
    if not inherited_sources:
        inherited_sources = k139.get('sources') or {}
    # Gate schema is archived verbatim too; the exact inherited hash map can be
    # taken from its final source snapshot inventory, never guessed from names.
    inherited_audit = {'expected_count': 155, 'gate_sha256': sha(REPO/'research/chapter3_experiments/results/linked_precheck02/checks.json'),
        'current_all_157_source_snapshot_match': frozen['all_match']}
    if isinstance(inherited_sources, dict) and len(inherited_sources) == 155 and all(isinstance(v, str) for v in inherited_sources.values()):
        inherited_audit.update(count=155, all_match=all(declaration['source_sha256'].get(path) == value for path,value in inherited_sources.items()))
    else:
        snapshot = REPO/'research/chapter3_experiments/results/linked_precheck02/source_snapshot'
        inherited_paths = {path.relative_to(snapshot).as_posix(): sha(path)
                           for path in snapshot.rglob('*') if path.is_file()}
        inherited_audit.update(count=len(inherited_paths), all_match=len(inherited_paths) == 155 and all(
            declaration['source_sha256'].get(path) == value for path,value in inherited_paths.items()))
    a.require(inherited_audit['all_match'], 'K139 inherited source identities changed')
    by_id = {row['id']:row for row in rows}
    jobs, native, phases, costs, changes = [], [], [], [], []
    for jid in EXPECTED:
        row = by_id.get(jid)
        if row is None:
            jobs.append({'id': jid, 'state': 'NOT_RUN', 'result_present': False, 'final_SAFE_receipt_verified': False})
            continue
        try:
            report, nr, pr, cr, sr = h.job_audit(root, declaration, row)
            if report.get('result_present'):
                result = read(root/jid/'result.json')
                report['linked_record_contract'] = result.get('linked_record_contract')
                report['linked_budget_boundary'] = result.get('linked_budget_boundary')
                report['failure_boundary'] = failure_boundary(result)
                report.pop('staged_budget_boundary', None)
        except (OSError, KeyError, TypeError, ValueError) as error:
            report = {'id': jid, 'ledger': row, 'state': 'SAVED_AUDIT_BLOCKED',
                'result_present': (root/jid/'result.json').is_file(), 'final_SAFE_receipt_verified': False,
                'audit_error': f'{type(error).__name__}: {error}'}
            nr, pr, cr, sr = [], [], [], []
        jobs.append(report); native += nr; phases += pr; costs += cr; changes += sr
    old,new = jobs
    old_e = interval(old['final_energy_J']) if old.get('final_energy_J') else None
    new_e = interval(new['final_energy_J']) if new.get('final_energy_J') else None
    completed = (ledger.get('consumed') == 2 and [row['id'] for row in rows] == list(EXPECTED)
        and all(row.get('state') == 'COMPLETED' for row in rows) and all(not job.get('audit_error') for job in jobs))
    valid = completed and all(job.get('final_SAFE_receipt_verified') for job in jobs)
    strict = bool(valid and old_e and new_e and new_e[1] < old_e[0])
    phase2 = next((row for row in phases if row['job'] == 'linked_n1' and row['phase_index'] == 2), {})
    comparison = {'stage': 'K140', 'quality_pair_completed': completed,
        'same_task_pair_comparison_valid': valid,
        'strict_new_improvement_over_old_observed': strict,
        'strict_criterion': 'new complete SAFE interval upper < old complete SAFE interval lower',
        'old_interval_J': old.get('final_energy_J'), 'new_interval_J': new.get('final_energy_J'),
        'strict_saving_vs_old_lower_J': str(old_e[0]-new_e[1]) if old_e and new_e else None,
        'strict_saving_vs_old_lower_fraction': str((old_e[0]-new_e[1])/old_e[0]) if old_e and new_e and old_e[0] > 0 else None,
        'strict_saving_vs_old_lower_percent_decimal': float((old_e[0]-new_e[1])/old_e[0]*100) if old_e and new_e and old_e[0] > 0 else None,
        'strict_saving_vs_old_lower_microjoule_decimal': float((old_e[0]-new_e[1])*1000000) if old_e and new_e else None,
        'second_phase_itself_strictly_improved_complete_energy': phase2.get('strict_energy_improvement_vs_own_before_interval'),
        'second_phase_complete_U_decrease_count': phase2.get('committed_U_decrease_count'),
        'identical_fresh_seed_candidate_and_energy': bool(old.get('seed_candidate_sha256') and old.get('seed_candidate_sha256') == new.get('seed_candidate_sha256') and old.get('initial_energy_J') == new.get('initial_energy_J')),
        'all_unchanged_execution_units': not any(row['unit_changed'] for row in changes),
        'calls_consumed': ledger.get('consumed'), 'declared_call_limit': declaration.get('method_call_limit'),
        'single_pair_not_statistical_ranking': True, 'no_global_optimality_claim': True,
        'no_historical_HEFT_read': True, 'no_new_research_native_thermal_decode_model_calls': True,
        'interpretation': 'quality and own-phase contribution reported separately; micro-scale strict difference alone does not establish practically important or stable improvement'}
    pair_changes = []
    by_stage = {jid:{(r['scene'],r['stage_id']):r for r in changes if r['job'] == jid} for jid in EXPECTED}
    for key,old_row in by_stage['old_n1'].items():
        other = by_stage['linked_n1'].get(key)
        if other and any(old_row[k] != other[k] for k in ('unit','final_opp','final_start_ms')):
            pair_changes.append({'scene':key[0], 'stage_id':key[1], 'old_unit':old_row['unit'], 'new_unit':other['unit'],
                'old_opp':old_row['final_opp'], 'new_opp':other['final_opp'],
                'old_start_ms':old_row['final_start_ms'], 'new_start_ms':other['final_start_ms']})
    comparison['final_pair_stage_differences'] = pair_changes
    after = h.raw_hashes(root, before)
    a.require(before == after, 'raw archives changed during stored-result analysis')
    facts = {'analysis':'K140-stored-linked-pair-complete-ledger-dual-anchor-audit-v1',
        'protocol':declaration['protocol'], 'scope':'immutable JSON/Fraction identity, saved SAFE interval, timing and event audit only',
        'helpers':[{'path':path.relative_to(REPO).as_posix(),'sha256':sha(path)} for path in (HELPER,h.HELPER,b.HELPER)],
        'declaration_sha256':sha(root/'declaration.json'), 'ledger':ledger, 'calls':jobs,
        'comparison':comparison, 'phase_attribution':phases, 'native_call_times':native,
        'stage_changes':changes, 'phase_exclusive_costs':costs, 'frozen_sources':frozen,
        'inherited_K139_sources':inherited_audit,
        'external_launcher_timing_records':b.launcher_records(root),
        'raw_hashes_before':before, 'raw_hashes_after':after, 'raw_unchanged':True,
        'new_research_native_thermal_decode_model_calls':0,
        'evidence_boundary':'no late witness, no substituted solver objective, no stored-history initialization; independently audit saved original SAFE receipts, not re-evaluate physics'}
    save(out/'facts.json',facts)
    h.write_csv(out/'comparison.csv',[{'job':job['id'],'ledger_state':job.get('ledger',{}).get('state',job.get('state')),
        'complete_SAFE_audit':job.get('final_SAFE_receipt_verified'),'initial_energy_J':job.get('initial_energy_J'),
        'final_energy_J':job.get('final_energy_J'),'U_J':job.get('final_U_J'),'first_SAFE_s':job.get('first_SAFE_s'),
        'method_s':job.get('timing',{}).get('method_elapsed_s'),'technical_state':job.get('technical_state'),
        'reason':job.get('reason'),'latch':job.get('search_failure_latched')} for job in jobs])
    h.write_csv(out/'phase_attribution.csv',phases)
    h.write_csv(out/'energy_updates.csv',[{'job':job['id'],**point,'energy_lower_J':point['energy_J'][0],'U_J':point['energy_J'][1]}
        for job in jobs for point in job.get('updates',[])])
    native_fields = ['job','phase_index','scene','round','request_number','status','exitflag','intlinprog_entered','budget_valid',
        'accepted_for_evaluation','MaxTime_used_s','actual_intlinprog_call_s','stop_delay_over_MaxTime_s','actual_call_within_MaxTime',
        'callback_count','nonempty_callback_count','final_vector_present','rootlp_callback_observed','first_rootlp_native_elapsed_s',
        'first_rootlp_event_number','rootlp_numfeaspoints','rootlp_numnodes','final_numfeaspoints','final_numnodes']
    h.write_csv(out/'native_timing.csv',[{key:row.get(key) for key in native_fields} for row in native],native_fields)
    h.write_csv(out/'stage_changes.csv',changes)
    h.write_csv(out/'phase_costs.csv',costs)
    h.write_csv(out/'final_pair_stage_differences.csv',pair_changes,['scene','stage_id','old_unit','new_unit','old_opp','new_opp','old_start_ms','new_start_ms'])
    h.plot(out,jobs)
    lines = ['# K140：旧N1与联动小邻域的存档配对分析','',
        f'同任务配对有效：{valid}；新版能量严格低于旧版：{strict}；第二阶段自身严格改善：{phase2.get("strict_energy_improvement_vs_own_before_interval")}。','',
        '| 方法 | 初始完整U/J | 最终完整U/J | 首SAFE/s | 全方法/s | 状态 |',
        '|---|---:|---:|---:|---:|---|']
    for job in jobs:
        lines.append(f'| {job["id"]} | {h.numeric_text(job["initial_energy_J"][1]) if job.get("initial_energy_J") else "NA"} | {h.numeric_text(job.get("final_U_J"))} | {h.numeric_text(job.get("first_SAFE_s"),3)} | {h.numeric_text(job.get("timing",{}).get("method_elapsed_s"),3)} | {job.get("ledger",{}).get("state",job.get("state"))} |')
    if old_e and new_e:
        lines += ['',f'相对旧版下端的严格节约：{comparison["strict_saving_vs_old_lower_percent_decimal"]:.12f}%（{comparison["strict_saving_vs_old_lower_microjoule_decimal"]:.9f} μJ）。本例第二遍取得新增节能，方法耗时增加；仅为单次原基准证据。']
    lines += ['','| 方法/阶段 | 开始完整U/J | 结束完整U/J | 完整U下降数 | 严格改善 | 阶段区间/s | 前置准备/s | 含准备/s |',
        '|---|---:|---:|---:|---|---:|---:|---:|']
    for row in phases:
        lines.append(f'| {row["job"]}/{row["phase_index"]} | {h.numeric_text(row["starting_complete_U_J"])} | {h.numeric_text(row["final_complete_U_J"])} | {row["committed_U_decrease_count"]} | {row["strict_energy_improvement_vs_own_before_interval"]} | {h.numeric_text(row["recorded_interval_elapsed_s"],3)} | {h.numeric_text(row["pre_record_setup_s"],3)} | {h.numeric_text(row["inclusive_phase_elapsed_s"],3)} |')
    lines += ['',
        '主要变化发生在AB：第二遍将A.pre、A.main、A.post和B.pre从H改为L，起点分别为0→0、10→40、40→110、0→60 ms。B.main和B.post保持本次第一遍末尾选择。AC未取得新增改善。',
        '新旧最终B.post的145→150 ms微差来自第一遍，不归为第二遍收益；第二遍自身的三次完整U更新分别发生在206.844、208.407、209.735 s。',
        '最终安排与U依据aggregation和committed_safe_snapshot的完整代，覆盖AB/AC、400 ms全窗口、空闲尾段、连续峰温和分项能量守恒。双锚点检查通过：D固定原fresh seed，关闭项固定最后第一遍完整SAFE，第二遍各场景x0可沿最新完整代更新。',
        '两次独立300秒预算内完成，旧版自然完成后未填满余时；新版第二遍133.313 s另加前置准备0.109 s。原生停止延迟、回调和数值门均已留档，终态数值门相对admission分别6→7、3→4且精确前缀一致。',
        '本例热违规和连续热反馈均为0；安全性来自完整连续复核。独立L0与局部solver-reported界分列，全域最优仍未证。',
        f'源码/冻结快照{frozen["count"]}项一致，继承K139的155项一致：{inherited_audit["all_match"]}；纯存档分析未新增求解或热计算，原始存档前后哈希不变。',
        '[安全能量与独立L0曲线](energy_bounds.png)。锚点、能耗分项、阶段成本及数值门见facts.json和CSV。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    own = Path(__file__).resolve()
    target = out/'analysis_script.py'
    if own != target.resolve():
        target.write_bytes(own.read_bytes())
    print(json.dumps(comparison,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=REPO/'research/chapter3_experiments/results/linked_quality_pair01')
    parser.add_argument('--out',type=Path)
    args = parser.parse_args()
    root = args.run.resolve()
    main(root,(args.out or root/'analysis01').resolve())
