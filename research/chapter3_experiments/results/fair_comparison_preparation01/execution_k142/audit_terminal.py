"""K142 independent saved-result audit. No production/test/model/heat/native/Git."""
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime, timezone
import hashlib
import importlib.util
import json

OUT = Path(__file__).resolve().parent
ROOT = next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
FROZEN = OUT.parent
helper = ROOT/'research/chapter3_experiments/results/linked_quality_pair01/analysis01/analysis_script.py'
spec = importlib.util.spec_from_file_location('k140_saved_json_only_independent', helper)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
h, a, b = c.h, c.a, c.b
read, digest = c.read, c.digest
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
save = lambda p, v: p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
checks, errors = {}, {}


def check(name, value):
    checks[name] = bool(value)


def exact_legal(candidate, instance):
    """Independent rational grid/dependency/unit/domain/deployment check."""
    shared, report = {}, {}
    units = {u['id']:u for u in instance['platform']['units']}
    assert set(candidate)=={'scenes'}
    assert set(candidate['scenes'])=={s['id'] for s in instance['scenarios']}
    for scene in instance['scenarios']:
        rows = candidate['scenes'][scene['id']]
        stages = {s['id']:s for s in scene['stage_instances']}
        requests = {r['id']:r for r in scene['requests']}
        assert len(rows)==len(stages)==len({r['stage_id'] for r in rows})
        assert set(r['stage_id'] for r in rows)==set(stages)
        timed = {}
        activity = F(0)
        for row in rows:
            stage = stages[row['stage_id']]
            modes = [m for m in instance['stage_modes'][stage['shared_stage_id']]
                if (m['unit_id'],m['opp_id'])==(row['unit'],row['opp'])]
            assert len(modes)==1 and not isinstance(row['start_ms'],float)
            mode = modes[0]
            start = F(row['start_ms']); end = start+F(mode['duration_ms'])
            req = requests[stage['request_id']]
            assert start>=F(req['release_ms']) and (start/F(instance['start_grid_ms'])).denominator==1
            assert end<=F(req['deadline_ms']) and end<=F(instance['window_ms'])
            sid = stage['shared_stage_id']
            assert sid not in shared or shared[sid]==row['unit']
            shared[sid] = row['unit']
            timed[row['stage_id']] = (start,end,row['unit'],row['opp'],units[row['unit']]['domain_id'])
            activity += F(mode['activity_power_W'])*F(mode['duration_ms'])/1000
        for left,right in scene['dependencies']:
            assert timed[left][1]<=timed[right][0]
        times = list(timed.values())
        for i,left in enumerate(times):
            for right in times[i+1:]:
                if max(left[0],right[0])<min(left[1],right[1]):
                    assert left[2]!=right[2]
                    assert left[4]!=right[4] or left[3]==right[3]
        report[scene['id']] = {'stage_count':len(rows),'finish_ms':str(max(t[1] for t in times)),
            'exact_activity_energy_J':str(activity), 'passed':True}
    return {'passed':True,'shared_deployment':shared,'scenes':report}


def main():
    d = read(FROZEN/'declaration.json')
    ledger = read(FROZEN/'ledger.json')
    assert ledger['state'] not in ('DECLARED','RUNNING'), 'Do not audit unfinished research execution'
    allowed = ['whole_milp','linked_n1','heft','sa101']
    observed = [r['id'] for r in ledger['calls']]
    expected_block = (ledger['state']=='BLOCKED' and observed==allowed[:2]
        and ledger['calls'][-1]['state']=='TECHNICAL_BLOCK')
    complete_four = ledger['state']=='COMPLETED' and observed==allowed
    check('terminal_frozen_prefix_or_complete_four_no_retry', (expected_block or complete_four)
        and ledger['consumed']==len(observed)
        and ledger['method_budget_s_reserved']==300*len(observed))
    check('unstarted_methods_have_no_claim_or_result',all(
        not (FROZEN/'claims'/(j+'.json')).exists() and not (FROZEN/j).exists()
        for j in allowed[len(observed):]))
    check('source159_current_snapshot_unchanged',len(d['source_sha256'])==159
        and all(sha(ROOT/p)==v==sha(FROZEN/'source_snapshot'/p) for p,v in d['source_sha256'].items()))
    check('input_three_bytes_and_semantics_unchanged', all(sha(FROZEN/p)==v
        for p,v in d['input_file_sha256'].items()) and all(digest(read(FROZEN/p))==d[k]
        for p,k in [('input_raw.json','raw_config_sha256'),('input_config.json','config_sha256'),
            ('input_instance.json','input_sha256')]))
    context = read(FROZEN/'phase_context.json')
    check('frozen_context_protocol_launcher_gate_intact', all(sha(FROZEN/p)==context[k+'_sha256']
        for k,p in [('protocol','protocol.md'),('launcher','launcher.py'),
            ('declaration','declaration.json'),('source_audit','source_audit.json')])
        and sha(FROZEN/'wrapper_checks.json')==d['wrapper_checks_sha256'])
    check('launcher_exit_matches_declared_stop_no_retry', read(FROZEN/'launcher_timing.json')['returncode']==(1 if expected_block else 0)
        and read(FROZEN.parent/'minimal_comparison_claim01.json')['no_retry'] is True)
    declared_at = datetime.fromisoformat(d['declared_at_utc'])
    check('declaration_precedes_unique_four_claims', all(datetime.fromisoformat(
        read(FROZEN/'claims'/(j+'.json'))['claimed_at_utc'])>declared_at for j in observed))
    calls, native_all, events_sha, phase_details = {}, [], {}, {}
    bound_values = []
    for row in ledger['calls']:
        jid = row['id']; folder = FROZEN/jid
        result = read(folder/'result.json'); instance = read(folder/'input_instance.json')
        kind = 'n1' if jid=='linked_n1' else row['method']
        check(jid+'/claim_and_terminal_ledger', row['state'] in ('COMPLETED','TECHNICAL_BLOCK')
            and row['seconds']==300 and not row.get('error')
            and row['source_unchanged'] and read(FROZEN/'claims'/(jid+'_result.json'))==row)
        check(jid+'/original_input_budget', digest(instance)==d['input_sha256']
            and digest(read(folder/'input_config.json'))==d['config_sha256']
            and result['timing']['limit_s']==300
            and instance['execution_rules']['idle_policy']=='auto_low_immediate_v1')
        check(jid+'/method_result_U_matches_ledger', row['safe_upper_bound_J']==result.get('safe_upper_bound_J'))
        all_safe, seen = [], set()
        safe_errors = []
        for candidate,receipt,source in a.full_evaluations(result,kind):
            key = digest([candidate,receipt])
            if key in seen or receipt.get('state')!='SAFE': continue
            seen.add(key)
            try:
                energy = a.full_safe(receipt,candidate,instance,300,kind,result)
                legal = exact_legal(candidate,instance)
                all_safe.append({'at_s':receipt['completed_at_elapsed_s'],
                    'candidate_sha256':digest(candidate),'energy_J':list(map(str,energy)),'source':source})
                for scene in instance['scenarios']:
                    local=receipt['scenes'][scene['id']]
                    if kind=='n1': local=local['result']
                    assert local['trace'] and F(local['trace'][-1]['time_s'])==F(2)/5
                    assert list(map(lambda x:F(x['time_s']),local['trace']))==sorted(F(x['time_s']) for x in local['trace'])
                    assert local['final_temperature_degC']==local['trace'][-1]['temperature_degC']
                    # Pure accounting dual-check; this is not a second thermal solve.
                    activity = a.interval(local['energy_components_J']['activity'])
                    assert activity[0]<=F(legal['scenes'][scene['id']]['exact_activity_energy_J'])<=activity[1]
            except Exception as exc:
                safe_errors.append({'source':source,'error':f'{type(exc).__name__}: {exc}'})
        check(jid+'/all_saved_SAFE_full_window_and_exact_legality',bool(all_safe) and not safe_errors)
        errors[jid]=safe_errors
        final=result.get('aggregation') if kind=='n1' else result.get('evaluation')
        energy=a.full_safe(final,result['safe_candidate'],instance,300,kind,result)
        legality=exact_legal(result['safe_candidate'],instance)
        check(jid+'/final_complete_SAFE_and_U',result['state']=='SAFE'
            and F(result['safe_upper_bound_J'])==energy[1]
            and digest(result['safe_candidate']) in {v['candidate_sha256'] for v in all_safe})
        first=min(p['at_s'] for p in all_safe)
        check(jid+'/first_complete_SAFE_record_correct',abs(first-row['first_complete_safe_at_s'])<1e-9
            and 0<=first<300 and all(0<=p['at_s']<300 for p in all_safe))
        bounds,bound_errors=a.read_bound(folder,result,instance,300)
        check(jid+'/independent_L0_scope_time_not_internal',not bound_errors and bounds.get('L0')
            and F(bounds['L0']['lower_bound_J'])<=energy[0])
        bound_values.append(F(bounds['L0']['lower_bound_J']))
        closed_path=folder/'matlab/closed.json'
        if closed_path.is_file():
            closed=read(closed_path)
            check(jid+'/owned_worker_cleanup',closed==row['cleanup']
                and closed['observed_tree_capture_complete'] is True
                and closed['observed_tree_verified_terminated'] is True
                and all(v['state'] in ('EXITED','IDENTITY_REUSED') for v in
                    closed['process_tree_verification']['identities']))
        else:
            check(jid+'/no_worker_no_false_cleanup',jid in ('heft','sa101') and row.get('cleanup') is None)
        updates=[]
        for point in sorted(all_safe,key=lambda p:p['at_s']):
            if not updates or F(point['energy_J'][1])<F(updates[-1]['energy_J'][1]): updates.append(point)
        check(jid+'/saved_final_U_is_best_accepted', F(updates[-1]['energy_J'][1])==energy[1])
        if kind=='n1':
            adapted={**d,'shared_deployment':d['shared_deployment_linked_only']}
            receipts=h.receipt_audit(result,instance,adapted)
            conditions=c.condition_audit(result,instance,adapted)
            committed=h.verified_updates(result,instance)
            warm=h.warm_snapshot_audit(result,instance,committed)
            check('linked/original_receipt_provenance_identity',receipts['all_pass'])
            check('linked/conditions_dual_anchors_closed_choices',all(v['all_pass'] for v in conditions))
            check('linked/phase2_x0_latest_complete_generation',all(v['all_pass'] for v in warm))
            check('linked/two_passes_one_root_no_shared_cache',
                [p['phase_index'] for p in result['phases']]==[1,2]
                and result['candidate_and_cache_shared_between_calls'] is False)
            native,models,solver_bounds,feedback=h.native_and_models(result,jid,folder)
            transport=h.augmented_audit(folder,result)
            resolved = [r for r in transport['requests'] if not r['latched_unresolved']]
            unresolved = [r for r in transport['requests'] if r['latched_unresolved']]
            check('linked/transport_resolved_original_rows_numeric_gates',transport is not None
                and all(not r['failure_reasons'] and r['callback_publications_complete']
                    and r['all_stored_numerical_gates_accepted'] and r['all_retained_rows_marked_bitwise']
                    and r['saved_admission_is_exact_earlier_numerical_check_prefix'] for r in resolved))
            stop_reasons={'CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED',
                'BUDGET_BEFORE_FINAL_ADMISSION','BUDGET_DURING_ADMISSION_ARCHIVE'}
            raw_transport = result['augmented_transport']
            check('linked/unresolved_is_recorded_budget_boundary_not_illegal_candidate',
                (not unresolved and not expected_block) or (expected_block and result['budget_exhausted']
                and result['reason']=='wall_time_limit'
                and set(raw_transport['failure_reasons'])==stop_reasons
                and all(r['all_stored_numerical_gates_accepted']
                    and set(r['failure_reasons'])<=stop_reasons for r in unresolved)
                and all(r['native_status']=='BUDGET_EXHAUSTED' and r['within_budget'] is False
                    and r['completed_at_s']==300 and r['cancel_requested'] is True
                    for r in raw_transport['requests'] if r['latched_unresolved'])))
            clocks,costs=h.clock_audit(result,jid)
            check('linked/exclusive_method_clock_partition',clocks['exclusive_sum_matches_method_elapsed']
                and not clocks['same_depth_collisions'])
            phase_details={'conditions':conditions,'warm_x0':warm,'clocks':clocks,'transport':transport,
                'complete_updates':committed,'models':models,'solver_reported_bounds':solver_bounds}
            phase2updates = [u for u in committed if u['phase_index']==2]
            check('linked/final_SAFE_retains_latest_pre_cutoff_complete_generation',
                committed[-1]['candidate_sha256']==digest(result['safe_candidate'])
                and committed[-1]['at_s']<300
                and result['committed_safe_snapshot']['aggregation']==result['aggregation'])
            phase_details['phase2_complete_U_update_count']=len(phase2updates)
        else:
            solved=result.get('solver_diagnostic') or result
            wrapper={'scenes':{'whole':{'solver_result':solved}}} if jid=='whole_milp' else {}
            native=b.native_records(wrapper,jid,folder) if jid=='whole_milp' else []
            feedback=solved.get('feedback',[])
        for n in native:
            n['job']=jid
            for event in n['immutable_event_audit'].get('callbacks',[]):
                events_sha[jid+'/'+event['file']]=event['sha256']
        native_all+=native
        calls[jid]={'state':result['state'],'reason':result.get('reason'),
            'energy_J':list(map(str,energy)),'U_J':result['safe_upper_bound_J'],
            'first_complete_SAFE_at_s':first,'method_elapsed_s':result['timing']['method_elapsed_s'],
            'cleanup_s':result['timing'].get('cleanup_s',0),
            'saved_full_SAFE_receipts':len(all_safe),
            'distinct_SAFE_candidates':len({v['candidate_sha256'] for v in all_safe}),
            'first_to_final_U_updates':updates,'final_legality':legality,'bounds':bounds,
            'independently_proven_optimal':result.get('independently_proven_optimal'),
            'independently_proven_infeasible':result.get('independently_proven_infeasible'),
            'feedback_records':len(feedback),'native_requests':len(native),
            'method_timing':result['timing'],'ledger_state':row['state'],
            'technical_issues':row.get('technical_issues')}
    check('same_independent_L0_all_consumed',len(set(bound_values))==1)
    check('immutable_callback_publications_unchanged',all(sha(FROZEN/p)==v for p,v in events_sha.items()))
    check('native_timely_records_or_explicit_unaccepted_cutoff',all(
        n['budget_valid'] is True or n['accepted_for_evaluation'] is not True for n in native_all))
    check('no_unearned_global_proof',all(not v['independently_proven_optimal']
        and not v['independently_proven_infeasible'] for v in calls.values()))
    report={'stage':'K142','reviewer':'本线程独立子代理；非主线⑥跨会话审查',
        'review_scope':'saved JSON/Fraction/source/claims consistency; no fresh thermal proof or optimization',
        'passed':all(checks.values()),'check_count':len(checks),'checks':checks,'errors':errors,
        'research_execution_status':ledger['state'],'four_method_comparison_completed':complete_four,
        'consumed_method_calls':len(observed),'not_run_methods':allowed[len(observed):],
        'calls':calls,'linked_phase_details':phase_details,'native_requests':native_all,
        'immutable_callback_sha256':events_sha,'new_research_native_model_thermal_calls':0,
        'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    save(OUT/'verification.json',report)
    lines=['# K142 四方法冻结对照独立终审','',
        f'**结论：{"通过" if report["passed"] else "存在未通过项"}，{len(checks)}项。** '
        '本线程子代理只读159源、冻结输入、账本、JSON与精确分数；不重算热轨迹、不调用求解器、不运行测试或Git。','',
        '| 方法 | 完整安全U/J | 首完整SAFE/s | 方法耗时/s | SAFE安排去重 |',
        '|---|---:|---:|---:|---:|']
    for jid,v in calls.items():
        lines.append(f'| {jid} | {float(F(v["U_J"])):.12f} | {v["first_complete_SAFE_at_s"]:.3f} | '
            f'{v["method_elapsed_s"]:.3f} | {v["distinct_SAFE_candidates"]} |')
    lines+=['','各份已接受SAFE均核输入/候选身份、全部scene、完整400 ms含空闲尾段、'
        '严格预算内形成时刻和原连续热包络。独立Fraction重核模式、5 ms启动、真实结束、依赖、期限、'
        '共享部署、半开区间执行单元/频率域互斥及活动能量。联动双锚、第一遍最后完整SAFE闭合、'
        '第二遍x0代际和原行增广数值门另核。','',
        f'实际消费{len(observed)}次调用，账本{ledger["state"]}，未启动方法：{", ".join(allowed[len(observed):]) or "无"}。'
        '没有补跑、延长预算或借历史见证。首SAFE并非首整数候选；'
        '方法时钟、合作式原生停止延迟、清理和外部封存分列。SAFE U、全域L0、局部/内部界分开，'
        '均未闭合全域最优或无解证明。四方法对照未完成时不作完整排名，未运行方法不借历史填补。','',
        '本次联动的锁存来自根预算到期前后接纳/归档未完成；已保存数值门均通过，'
        '不能据此判候选非法、原问题无解或求解器数值错误。冻结包装保守停止剩余调用，'
        '已成完整SAFE继续保留；研究调用未完成与本存档审计通过分别登记。','',
        f'外层反馈记录合计{sum(v["feedback_records"] for v in calls.values())}，'
        '若未触发，不据此宣称反馈收益。不同搜索覆盖和初始化不能归为单因素收益。','',
        '未通过项：'+(', '.join(k for k,v in checks.items() if not v) or '无')+'。详见verification.json。']
    (OUT/'independent_review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'check_count':len(checks),
        'failed':[k for k,v in checks.items() if not v],'errors':errors},ensure_ascii=False))


if __name__=='__main__':
    main()
