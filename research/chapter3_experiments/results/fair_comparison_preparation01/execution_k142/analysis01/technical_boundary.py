"""Supplement already saved late transport diagnostics, never accept new U."""
from pathlib import Path
import hashlib
import json

REPO = next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
ROOT = REPO/'research/chapter3_experiments/results/fair_comparison_preparation01'
OUT = ROOT/'execution_k142/analysis01'

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

facts, ledger = read(OUT/'facts.json'),read(ROOT/'ledger.json')
linked = read(ROOT/'linked_n1/result.json')
request = linked['augmented_transport']['requests'][1]
native = []
for jid,num in [('whole_milp',1),('linked_n1',4)]:
    path = ROOT/jid/'matlab'/f'request_{num:06d}.response.json'
    response = read(path)
    phases = response.get('phase_seconds') or {}
    maximum = response.get('solver_max_time_s_used')
    actual = phases.get('intlinprog_call')
    native.append({'method':jid,'request_number':num,
        'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),
        'native_status':response.get('status'),'native_exitflag':response.get('exitflag'),
        'native_output_solver_reported_only':response.get('output'),
        'actual_intlinprog_call_s':actual,'MaxTime_used_s':maximum,
        'stop_delay_over_MaxTime_s':None if actual is None or maximum is None else max(0.,actual-maximum),
        'saved_method_status':'BUDGET_EXHAUSTED','new_evidence_accepted':False,
        'scope':'native response left on disk at/after root deadline; timing/status only, never new candidate/thermal/energy proof'})
events = []
for path in sorted((ROOT/'linked_n1/matlab').glob('request_000004.event_*.json')):
    event = read(path)
    events.append({'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),
        **{key:event.get(key) for key in ('kind','event_number','state','request_wall_seconds','values')},
        'consumed_before_cutoff':event.get('event_number') in [e['number'] for e in request.get('events',[])],
        'after_cutoff_event_cannot_create_new_evidence':True})
info = {'protocol':'K142-existing-deadline-boundary-diagnostics-v1',
    'research_call_count':ledger['consumed'],'ledger_state':ledger['state'],
    'ledger_technical_issues':ledger['calls'][1]['technical_issues'],
    'linked_request_2_fields':{key:request.get(key) for key in ('request_index','prepared_at_s',
        'failure_reasons','expected_callback_numbers','checked_callback_numbers','callback_publications_complete',
        'cancel_requested','cancel_published_at_s','native_status','native_exitflag','latched_unresolved',
        'completed_at_s','within_budget')},
    'linked_request_2_saved_numerical_gates':[{'source':row.get('source'),'accepted':row.get('accepted'),
        'started_at_s':row.get('started_at_s'),'completed_at_s':row.get('completed_at_s'),
        'within_budget':row.get('within_budget')} for row in request.get('numerical_checks',[])],
    'linked_request_4_immutable_events':events,'native_post_deadline_diagnostics':native,
    'safety_receipts_remain_valid':all(c.get('final_SAFE_receipt_verified') for c in facts['calls'][:2]),
    'four_method_comparison_complete':False,'remaining_methods':'HEFT and SA101 NOT_RUN; no retry',
    'interpretation':'deadline exhausted before final augmented candidate/publication/archive admission; observed saved gates all pass, but entire late request coverage is unresolved. Existing prior complete SAFE is retained. This does not demonstrate a rejected numerical candidate or unsafe incumbent.',
    'new_research_heat_decode_calls':0}
target = OUT/'technical_boundary.json'
assert not target.exists()
target.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# Clarify generated reader-facing state labels; original facts/raw are intact.
summary = OUT/'summary.md'
text = summary.read_text(encoding='utf-8')
text = text.replace('完整四方法对照有效：False。','四方法对照未完成，不能形成四法排名；已经核实的完整安全输出保留。')
text = text.replace('热反馈行 | 状态 |','热反馈行 | 方法／调用状态 |')
text = text.replace('| 0 | SAFE |','| 0 | SAFE／COMPLETED |',1)
text = text.replace('| 0 | SAFE |','| 0 | SAFE／TECHNICAL_BLOCK |',1)
text += '\n联动版末轮AC在300秒截止前未完成完整数值门与回调发布覆盖核对，因此按预先规则停止后续HEFT和SA；已有完整SAFE保留。该轮已存两项数值门均accepted=True，尚无数值拒绝证据。原生终态晚回执只作耗时／退出诊断，不能补作预算内方案。详见technical_boundary.json。\n'
summary.write_text(text,encoding='utf-8')
(OUT/'analysis_script.py').write_bytes((REPO/'.runtime/k142_analysis/analysis_script.py').read_bytes())
(OUT/'technical_boundary.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'technical_boundary_saved':True,'existing_SAFE_preserved':info['safety_receipts_remain_valid'],
    'native_delays':native},ensure_ascii=False,indent=2))
