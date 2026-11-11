"""Read-only source/log extraction. No project module imports or scientific calls."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = 'research/chapter3_experiments/'
LOCAL = 'research/chapter3_support_local_migration_20261110/run_local_pair.py'
OLD = 'research/chapter3_support_propagation_20261110/'


def utc():
    return datetime.now(timezone.utc).isoformat()


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, text):
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write(text)


def item(topic, files_fields, supports, does_not_support, source):
    return dict(topic=topic, files_fields=files_fields, supports=supports,
                does_not_support=does_not_support, source=source)


def main():
    started, tick = utc(), time.perf_counter()
    plan = read(OLD + 'native_pair_plan_NOT_RUN.json')
    source_checks = [dict(path=name, expected=expected, actual=sha(ROOT / name))
                     for name, expected in sorted(plan['runtime_source_sha256'].items())]
    if len(source_checks) != 217 or any(row['expected'] != row['actual'] for row in source_checks):
        raise ValueError('Frozen 217 source identity drift; stop contract extraction')
    rows = [
        item('Python worker process launched',
             'batch/events.jsonl: WORKER_STARTED; off|on_worker_return.json: argv,pid/returncode,wall_s',
             'Launcher created the independent Python child; return record describes that process lifetime.',
             'Not MATLAB ready, not a native solver request or entry. Exit0 alone does not establish a valid pair.',
             LOCAL + ':372-392'),
        item('MATLAB worker ready',
             'method/matlab/ready.json: status,release,intlinprog_path,license_checkout; session.json: startup_outcome,ready_publication_read,startup_wall_seconds; method/result.json: matlab_worker_ready,solver_started',
             'Worker published READY after toolbox checkout/path check; bridge read it within its original deadline and checked release2023b before method flags become true.',
             'Legacy solver_started means ready only. A ready file alone does not prove Python accepted it in time or intlinprog was called.',
             BASE + 'solve_model.m:6-15; ' + BASE + 'matlab_bridge.py:521-535; ' + BASE + 'method_runner.py:51-53,86-94'),
        item('Native entry notification',
             'request_N.event_*.json: kind=solver_entered; method/diagnostic_events.jsonl: worker_event_received with same request/event_number and method_elapsed_s; result.diagnostic.solver_entered_received_s; response.intlinprog_entered; result.integer_solver_entered',
             'Worker reached the native-entry branch immediately before intlinprog; Recorder receipt adds a strict in-budget Python receive time. A response true or timely entry event supports the aggregate true.',
             'The flag/event is set/published just before the function call, so it does not prove rootLP, any numerical iteration or successful return. No event/response after a request is UNKNOWN, not confirmed no-entry.',
             BASE + 'solve_model.m:133-150; ' + BASE + 'diagnostic_search.py:38-57; ' + BASE + 'method_runner.py:143-152'),
        item('No-entry versus unknown',
             'method/result.json: solver_request_attempts,integer_solver_entered (true/false/null),integer_solver_entry_evidence; slot_result.json.native_entry_confirmed; off|on_worker_return.json',
             'False means no request attempts or every returned entry flag explicitly false; true may come from a timely immutable event; null preserves unconfirmed entry. Launcher crash/watchdog yields null.',
             'Request attempts, guard native_request_attempts, a .request.json file, crash or timeout do not prove native entry or non-entry. A guard count increments before native forwarding; it is not a solver-call completion count.',
             BASE + 'method_runner.py:143-152; ' + LOCAL + ':284-285,333-341,388-391'),
        item('Fresh physical SAFE seed and same physical candidate',
             'method/initial_receipt_checkpoint.json.initialisation: witness.candidate/evaluation,completion; initial_guard.json: status,candidate_sha256,input_sha256,SAFE_formed_at_s,x0_formed_at_s,guard_completed_at_s,actual_vector_length',
             'Full matching in-budget SAFE witness, numerical completion/decode roundtrip, frozen expected candidate/input identity and actual decodedx0 guard before first native request. OFF/ON vector lengths may differ for the same physical schedule.',
             'SAFE may remain the initial constructor solution even if native work fails. This is the common evaluator, not a second independent implementation; guard PASSED is not native x0 acceptance or proof of improvement.',
             BASE + 'initial_point.py:101-128,131-172,230-244; ' + LOCAL + ':216-285'),
        item('Python numerical x0 admission',
             'request_N.initial.json and request_N.input.json.initial_point: provided,accepted_numerically,length,inequality/equality/lower/upper/integer violations,tolerances; initialisation.completion.numerical_acceptance',
             'The actual full floating vector satisfied the exported row/bound/integer checks without rounding/repair under ConstraintTolerance1e-9 and IntegerTolerance1e-6.',
             'No exact feasibility/thermal certificate and no MATLAB acceptance. An .initial.json rejected record also exists on admission failure; inspect accepted_numerically, not file existence.',
             BASE + 'matlab_bridge.py:127-192,195-219,598-605'),
        item('x0 request prepared/published',
             'request_N.input.json.initial_point; request_N.mat contains x0 and x0_validation; request_N.request.json published last; .python.json may say BUDGET_EXHAUSTED_BEFORE_PUBLICATION',
             'Numerical payload was prepared; published MAT plus request indicates this request was offered to the worker. Original _InitialSession injects x0 into first solve only.',
             'Input metadata or MAT alone is not worker receipt. Counter increments before conversion/publication, so it can count an aborted attempt. Later rounds do not automatically receive the initial vector.',
             BASE + 'initial_point.py:175-193; ' + BASE + 'matlab_bridge.py:583-605,608-655'),
        item('Worker received x0',
             'request_N.response.json.initial_point: provided=true,length,initial_objective,python_admission; request_N.native.mat: initialPoint',
             'MATLAB loaded this request\'s x0 and passed initialPoint as the explicit argument if the native call branch was reached.',
             'The worker deliberately sets solver_acceptance=not_independently_observed and thermal_safe_claim=false. Merely received, returnedx matchingx0, or finite fval is not proof intlinprog adopted it as incumbent.',
             BASE + 'solve_model.m:36-45,149-150,160-168'),
        item('Native x0 acceptance / rejection',
             'response.initial_point.solver_acceptance; solver_warning_identifier/message,error_identifier/message,exitflag,output; python numerical_consistency',
             'Keep any explicit native diagnostics and exact same-request context. A Python-admittedx0 plus native SOLVED/exitflag-2 forms a separate engineering status-conflict diagnostic.',
             'Current worker does not independently observe native x0 acceptance; no existing field can upgrade not_independently_observed to accepted. The status conflict is not a mathematical contradiction or infeasibility proof.',
             BASE + 'solve_model.m:40-45,151-158,171-185; ' + BASE + 'matlab_bridge.py:222-245,692-703'),
        item('RootLP/preprocessing progress',
             'Raw callback state/values and callback_fields; final output/message/native.mat if present; MATLAB log may contain explicit diagnostic text',
             'Only actual published raw solver-reported fields/text support the progress they explicitly describe. Preserve exact names/values and request identity.',
             'No dedicated rootLP-entered/completed flag or rootLP duration is instrumented. Native entry, zero callbacks/nodes, sparse log or waiting duration cannot distinguish rootLP from preprocessing/other native work or prove rootLP finished.',
             BASE + 'solve_model.m:89-94,137-158,179-214; ' + BASE + 'diagnostic_search.py:49-57,125-136'),
        item('Nodes, lower bound and gaps',
             'request_N.event_*.json.values; response.callbacks/callback_fields; response.output and native.mat output; diagnostic.solver_progress raw copies. Inspect only fields actually present (for example numnodes/lowerbound/relativegap/absolutegap).',
             'They are solver-reported snapshots; event request_wall_seconds is native request-relative, Recorder method_elapsed_s is Python receive time. Keep objective/bound units and raw gap conventions intact.',
             'No callbacks/field is missing evidence, not numeric0. Generic Recorder does not derive/certify bounds or gaps. Never combine fullSAFE physicalUB with native fval/relativegap to reconstructLB: they may refer to different objectives/receipts. No global optimum, physicalenergy lower certificate, or rootLP completion follows from those numbers alone.',
             BASE + 'solve_model.m:155-167,179-214; ' + BASE + 'diagnostic_search.py:49-57,125-136; ' + BASE + 'matlab_bridge.py:699-704'),
        item('Native call elapsed time',
             'response.phase_seconds.intlinprog_call; native.mat output/opts; other phases request_and_mat_load,options_preparation,native_result_archive',
             'intlinprog_call measures MATLAB wall time around the call on a normal return; includes native callbacks/publications within that interval. Native MaxTime allocation is a limit, not observed duration.',
             'No completed timer if the call never returned/threw before assignment. Not CPUtime, not method wall time, and not rootLPtime. MaxTime may be much less than300 after prior costs.',
             BASE + 'solve_model.m:47-52,108-132,147-169'),
        item('Waiting/transport elapsed time',
             'method.timing.phase_records/phases_exclusive_s.solver_wait_and_response_read; request_N.python.json.wall_seconds/publication_read; response.matlab_request_wall_seconds,worker_elapsed_seconds; session.startup_wall_seconds',
             'Python requestwall includes transport+waiting+response read/archive context; wait phase polls Recorder, which may decode/evaluate callback candidates while MATLAB continues. Native requestwall includes MAT/options/call/archive; workerelapsed includes worker idle/other requests.',
             'Waiting phase is not pure solver or CPUtime and cannot identify a rootLP bottleneck. Timers overlap/nest; do not sum inclusive parents and children or cross-clock origins.',
             BASE + 'matlab_bridge.py:59-99,531,608-611,635-662,690-715; ' + BASE + 'solve_model.m:180-181; ' + BASE + 'timing.py:38-71'),
        item('300s method budget and outer process time',
             'method/result.json.timing.limit_s/method_elapsed_s/deadline_overshoot_s/cleanup_s; off|on_worker_return.json.wall_s/watchdog_expired; slot_result.process_body_wall_s',
             'Original absolute MethodBudget starts before inputread, shares construction/MATLABstartup/freshinitialization/export/native work/full evaluation/feedback with no round reset. Imports precede it; cleanup/report are separate. Launcher has a420s watchdog.',
             '300s is not native MaxTime300, a hard realtime process kill, or whole launched-Python walltime. Cleanup/archive are not additional search. Late native files remain diagnostics; in-budget receipts require timely full completion.',
             BASE + 'timing.py:9-36,60-71; ' + BASE + 'method_runner.py:44,114-159; ' + LOCAL + ':372-391'),
        item('Returned native vector versus complete physical SAFE receipt',
             'request_N.python.json: budget_valid,accepted_for_evaluation,x; diagnostic.evaluations[*].accepted_safe/evaluation; result.safe_solution_source,milp_improved_initial_upper_bound',
             'Only timely SOLVED nonemptyvector without status conflict becomes eligible for the common evaluator; full SAFE/rankable receipt completed before deadline establishes accepted physicalenergy. Candidate receipt/decode and evaluation have separate stamps.',
             'Native fval/incumbent or accepted_for_evaluation is not thermal SAFE. Top-level SAFE may come from initial_constructor; it alone cannot establish MILP improvement, native success or optimality.',
             BASE + 'matlab_bridge.py:684-715; ' + BASE + 'diagnostic_search.py:61-123; ' + BASE + 'initial_point.py:230-244'),
        item('Pair and cleanup status',
             'slot_result.json: guard,cleanup,cleanup_complete,native_entry_confirmed,status; method/matlab/closed.json; pair_summary.json.status/results/failure/not_run',
             'COMPLETE requires guardPASSED, native entrytrue, complete cleanup and no flagged interface/numericalerror. OFF invalid/cleanupunconfirmed blocks ON. VALID_PAIR means both bounded one-shot invocations passed the launcher gate.',
             'Not proof of optimization success, improvement, native x0acceptance or globaloptimality. Crash/watchdog preserves unknown nativeentry; no automatic resume/reset or retries; do not infer missing ON ran.',
             BASE + 'matlab_bridge.py:401-438; ' + LOCAL + ':330-344,388-407,411-445')
    ]
    sources = {
        BASE+'matlab_bridge.py': [(59,99),(127,245),(401,438),(454,558),(561,715)],
        BASE+'solve_model.m': [(1,216)],
        BASE+'diagnostic_search.py': [(1,136)],
        BASE+'method_runner.py': [(35,177)],
        BASE+'initial_point.py': [(101,244)],
        BASE+'timing.py': [(9,71)],
        BASE+'run_warm_diagnostic.py': [(67,83)],
        LOCAL: [(216,285),(288,344),(372,456)],
        OLD+'execution_source/milp.py': [(30,33),(413,454),(1100,1107)],
        OLD+'r1_diagnostic/off/result.json': [(220,265),(335,349)],
        OLD+'r1_diagnostic/on/result.json': [(11948,11992),(12068,12077)],
    }
    excerpts=[]
    for path, ranges in sources.items():
        lines=(ROOT/path).read_text(encoding='utf-8-sig').splitlines()
        excerpts.append(path+' SHA256='+sha(ROOT/path))
        for first,last in ranges:
            excerpts += [f'{number:6d}  {lines[number-1]}' for number in range(first,last+1)]
        excerpts.append('')
    old={}
    for variant in ['off','on']:
        result=read(OLD+f'r1_diagnostic/{variant}/result.json')
        old[variant]={
            'source': OLD+f'r1_diagnostic/{variant}/result.json',
            'affine_templates': result['construction']['affine_templates'],
            'affine_miss_binding': result['construction']['construction_details']['affine_miss_binding'],
            'method_diagnostic_elapsed_s':result['method_diagnostic_elapsed_s'],
            'started_utc':result['started_utc'],'ended_utc':result['ended_utc'],
            'new_native_solver_calls':result['new_native_solver_calls'],
            'formal_pair_status':result['formal_pair_status'], 'timing_limit':result['timing_limit']}
    report={'scope':'Static/read-only repository logging contract; current local result ZIP inaccessible. No local-run numerical conclusions.',
        'source_count_verified':len(source_checks),'all_frozen_217_match':True,
        'source_checks':source_checks,'launcher_sha256':sha(ROOT/LOCAL),'contract':rows,
        'old_cloud_affine':old,
        'old_cloud_affine_interpretation':'7560 to7494 is current bounded-cache affine-template misses/bindings (66 fewer,0.873015873%); key is interval-coefficient endpoint text plus slot-bound signatures, limit2048, clears3 on each side. Not globallyunique affine states, LP iterations, nodes or native solver work. Both old diagnostics explicitly report0 native calls and NOT_RUN_NO_MATLAB_R2023b.',
        'next_minimal_readonly_steps':[
          'Obtain the existing resultZIP; first list members safely, identify fileplan/launcher/sourcehashes and batchclaim. Do not execute status/run or restart any scientific stage merely to read evidence.',
          'Read pair_summary/slot_result/worker_return/events and method/result/timing/initial_checkpoint/initial_guard; preserve native entry null and any missing ON claim.',
          'Read each MATLAB session/ready/cleanup and request input/initial/request/response/python/event files and existing worker stdout/stderr/matlab.log, associating batch,side,request,eventnumber; if needed inspect existing native.mat data without solver calls.',
          'Compare the complete fresh physicalcandidate/input hashes and fullSAFE/x0 evidence, then read callback/output fields actually present and distinguish native objective from complete physicalenergy.',
          'If rootLP/acceptance/progress fields were never published (Displayoff is fixed), report the precise gap and propose prospective logging observation only; do not diagnose rootLP, symmetry or numerical trouble from silence. Staticreading cannot retroactively recover them or justify a new call.'],
        'project_module_imports':0,'model_construction_calls':0,'thermal_evaluator_calls':0,'matlab_launches':0,'native_solver_calls':0}
    write_new(OUT/'logging_contract.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    with (OUT/'logging_contract.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_new(OUT/'source_excerpts.txt','\n'.join(excerpts)+'\n')
    text=['# OFF/ON 原生日志读取合同（仅源码核查）','',
        '当前本机结果 ZIP 尚不可访问。本记录只定义冻结代码的证据能力，不包含本机数值结论。核对旧217文件全部一致；launcher SHA256为`'+report['launcher_sha256']+'`。','',
        '关键边界：`solver_started`只代表MATLAB ready；原生入口通知在实际函数调用前发出，不能替代LP/节点进展；Python数值接纳、worker收到x0和原生接纳是三件事。当前原生接纳明确记为`not_independently_observed`。无entry事件/响应时保留UNKNOWN。完整SAFE物理UB不得与native fval/relativegap混算LB；必须读取同一原生请求的output/callback原字段与计时。','',
        '|要核的问题|读取证据|可支持|不能支持/缺项|源码行|','|---|---|---|---|---|']
    for row in rows:
        text.append('|'+ '|'.join(str(row[key]).replace('|','/').replace('\n',' ') for key in row)+'|')
    text += ['', '旧云端affine miss：OFF7560、ON7494，少66（约0.873%）；两侧cache clears均3，因此不是全局唯一状态数。旧数据为2026-11-10构模/现场初解诊断，均new_native_solver_calls=0，不能用作本机根LP、节点、下界或solver耗时证据。原始数值/精确来源见logging_contract.json及source_excerpts.txt。','',
        '下一最小行动是只读已有ZIP的计划/身份、批次/slot收据、ready/session/cleanup及逐request/event记录；缺失的rootLP/原生x0接纳字段只能列为证据缺口。不要重新初始化或重开原slot来补日志。','',
        '本次脚本仅使用Python标准库读源码、哈希和旧JSON，写入本contract目录；没有导入研究模块、构模、热评价或MATLAB/求解器调用。']
    write_new(OUT/'README.md','\n'.join(text)+'\n')
    ended=utc()
    record={'started_utc':started,'ended_utc':ended,'elapsed_s':time.perf_counter()-tick,
        'cwd':str(ROOT),'argv':[sys.executable,'-B',str(Path(__file__).relative_to(ROOT))],
        'python':sys.version,'platform':platform.platform(),'script_sha256':sha(Path(__file__)),
        'scope':'Read frozen source bytes and old cloudJSON; generate contract only. No project modules imported or scientific calls.',
        'source_count_verified':len(source_checks),'contract_rows':len(rows),
        'outputs':{p.name:sha(p) for p in [OUT/'logging_contract.json',OUT/'logging_contract.csv',OUT/'source_excerpts.txt',OUT/'README.md']},
        'native_solver_calls':0,'matlab_launches':0,'model_construction_calls':0,'thermal_evaluator_calls':0}
    write_new(OUT/'execution.json',json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:record[key] for key in ['started_utc','ended_utc','elapsed_s','source_count_verified','contract_rows','native_solver_calls']},indent=2))


if __name__=='__main__':
    main()
