"""K178 terminal JSON analysis only. No scientific code imports or calls."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
BASE = REPO/'research/chapter3_experiments/results'
OLD = BASE/'response_information_execution01'
NEW = BASE/'response_information_resume01'
PRE = BASE/'response_information_resume_precheck01'
SUPER = BASE/'response_information_resume01_supervision'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def norm(candidate):
    return {'scenes':{sid:sorted([dict(row,start_ms=str(F(row['start_ms']))) for row in rows],
        key=lambda row:row['stage_id']) for sid,rows in candidate['scenes'].items()}}


def energy_interval(value):
    return [F(v) for v in value]


def serial_interval(value):
    return [str(v) for v in value]


def changes(h,r):
    out=[]
    for sid,hrows in h['scenes'].items():
        rm={v['stage_id']:v for v in r['scenes'][sid]}
        for a in sorted(hrows,key=lambda v:v['stage_id']):
            b=rm[a['stage_id']]
            fields=[key for key in ('unit','opp') if a[key]!=b[key]]
            if F(a['start_ms'])!=F(b['start_ms']):fields.append('start_ms')
            if fields:out.append({'scene':sid,'stage_id':a['stage_id'],'fields':fields,'H':a,'R':b})
    return out


def run(destination):
    # Terminal receipts must preexist before any analysis reads a result.
    terminal=read(NEW/'terminal.json'); outer=read(SUPER/'terminal.json')
    if outer['status'] not in ('COMPLETED','CONTROLLER_STOPPED','CONTROLLER_NONZERO_EXIT',
        'CALENDAR_DEADLINE','SUPERVISOR_TECHNICAL_FAILURE'):
        raise RuntimeError('Terminal archive required; never analyze live planning')
    destination.mkdir(parents=True,exist_ok=False)
    declaration=read(PRE/'execution_declaration.json')
    checks=[]
    def check(name,value,evidence=None):
        checks.append({'name':name,'passed':bool(value),'evidence':evidence})
    check('declaration_bytes_bound',digest(PRE/'execution_declaration.json')==outer['declaration_sha256'])
    drift=[p for p,s in declaration['expected_sha'].items() if digest(REPO/p)!=s]
    check('all_frozen_sources_unchanged',not drift,{'files':len(declaration['expected_sha']),'drift':drift})
    original_drift=[p for p,s in declaration['prior_sha256'].items() if digest(REPO/p)!=s]
    check('original_K177_evidence_preserved',not original_drift,original_drift)
    supplement=read(PRE/'review/final_static_gate03.json')
    mismatched=[p for p,s in supplement['source_sha256'].items() if digest(REPO/p)!=s or declaration['expected_sha'].get(p)!=s]
    check('supplement03_matches_frozen_current_sources',supplement['passed'] and not mismatched,mismatched)
    old_outer=read(BASE/'response_information_execution01_supervision/terminal.json')
    check('old_120_slot_still_consumed',declaration['prior_method_budget_consumed_s']==120
        and old_outer['controller_ledger']['reserved_scientific_budget_s']==120)
    ledger=outer.get('controller_ledger',{})
    check('combined_budget_no_more_than720',ledger.get('reserved_scientific_budget_s',601)+120<=720,ledger)
    check('new_plan_calls_at_most_three',ledger.get('plan_calls_consumed',4)<=3)
    check('post_calls_at_most_four',ledger.get('audit_calls_consumed',5)<=4)
    check('no_new_plan1',not (NEW/'ledger/slot_1.claim.json').exists())
    check('combined_active_calendar_within1200',old_outer['calendar_elapsed_s']+outer['calendar_elapsed_s']<=1200,
          {'old':old_outer['calendar_elapsed_s'],'new':outer['calendar_elapsed_s'],
           'repair_and_human_gap_excluded_and_separately_disclosed':True})
    check('unique_no_retry',terminal['no_automatic_retry'] and not outer['automatic_retry'])
    slots=[]
    for slot in declaration['slots']:
        ordinal=slot['ordinal']; folder=NEW/f'slot_{ordinal}'
        plan_folder=OLD/'slot_1' if ordinal==1 else folder
        raw_path=plan_folder/'planner_public/method/result.json'
        item={'slot':slot,'planning_source':str(raw_path.relative_to(REPO)),
              'new_plan_started':(folder/'planner_public/job.json').exists(),
              'audit_started':(folder/'H_audit_private/job.json').exists()}
        if not raw_path.exists():
            item['planning_result_present']=False; slots.append(item); continue
        raw=read(raw_path); job=read(plan_folder/'planner_public/job.json'); packet=job['packet']
        item.update(planning_result_present=True,planning_state=raw.get('state'),planning_reason=raw.get('reason'),
            planning_elapsed_s=raw['timing']['method_elapsed_s'],first_planning_safe_s=raw.get('first_safe_at_s'),
            candidate_count=raw.get('candidate_count'),planning_internal_thermal_evaluations=raw.get('thermal_evaluations'),
            planning_weighted_energy_J=raw.get('evaluation',{}).get('weighted_energy_J'),
            candidate=raw.get('safe_candidate'),planning_input_sha256=raw.get('input_sha256'))
        check(f'slot{ordinal}_same_heft',raw['method']=='heft' and raw['seed'] is None)
        check(f'slot{ordinal}_plan_limit120',raw['timing']['limit_s']==120)
        check(f'slot{ordinal}_public_input_identity',raw['input_sha256']==canonical(packet['planner']['instance'])
            and packet['view']==slot['view'] and packet['problem_id']==slot['problem_id'])
        postpath=folder/'H_audit_private/worker_return.json'
        if postpath.exists():
            returned=read(postpath); post=returned['payload']; postjob=read(folder/'H_audit_private/job.json')
            check(f'slot{ordinal}_post_job_hash',returned['job_sha256']==canonical(postjob))
            check(f'slot{ordinal}_post_fixed_original_candidate',json.loads(postjob['token']['candidate_json'])==raw['safe_candidate'])
            check(f'slot{ordinal}_post_true_H',postjob['truth']['instance']['response_variant']=='H'
                and postjob['truth']['instance']['settings']['response_variant']=='H')
            check(f'slot{ordinal}_post_limit60',postjob['limit_s']==60 and post.get('root',{}).get('limit_s')==60)
            check(f'slot{ordinal}_post_model_input_identity',postjob['token']['truth_H_sha256']==canonical(postjob['truth']['instance']))
            item.update(post_status=post.get('audit_status'),real_safe=post.get('real_safe'),post_elapsed_s=post.get('root',{}).get('method_elapsed_s'),
                post_root=post.get('root'),post_stop_required=post.get('stop_required'),post_reason=post.get('reason'),
                truth_H_input_sha256=canonical(postjob['truth']['instance']),truth_H_config_sha256=canonical(postjob['truth']['config']),
                candidate_sha256=canonical(norm(raw['safe_candidate'])))
            receipt=post.get('raw_receipt',{})
            if post.get('audit_status')=='TRUE_H_SAFE' and post.get('real_safe') is True:
                item['true_H_weighted_energy_J']=receipt['weighted_energy_J']
                item['true_H_safe_U_J']=receipt['safe_upper_bound_J']
                item['true_H_scene_components_J']={sid:v['energy_components_J'] for sid,v in receipt['scenes'].items()}
                item['true_H_scene_peaks_degC']={sid:v['peaks_degC'] for sid,v in receipt['scenes'].items()}
                item['true_H_request_completion_ms']={sid:v['request_completion_ms'] for sid,v in receipt['legality']['scenes'].items()}
                item['true_H_deadlines_ms']={scene['id']:{req['id']:req.get('deadline_ms') for req in scene.get('requests',[])} for scene in postjob['truth']['instance']['scenarios']}
                check(f'slot{ordinal}_true_H_SAFE_timely',0<=receipt['completed_at_elapsed_s']<60
                    and receipt['evidence_identity']=={'input_sha256':canonical(postjob['truth']['instance']),
                        'candidate_sha256':canonical(raw['safe_candidate'])})
                check(f'slot{ordinal}_all_scenes_full_window',all(v['state']=='SAFE' and v['complete'] is True
                    and F(v['covered_until_s'])==F(postjob['truth']['instance']['window_ms'])/1000 for v in receipt['scenes'].values()))
        slots.append(item)
    pairs=[]
    for problem in ('base__R1','base__R2'):
        pair={v['slot']['view']:v for v in slots if v['slot']['problem_id']==problem}
        entry={'problem_id':problem,'both_true_H_SAFE':all(pair.get(k,{}).get('real_safe') is True for k in ('H','R'))}
        if entry['both_true_H_SAFE']:
            h,r=pair['H'],pair['R']; hl,hh=energy_interval(h['true_H_weighted_energy_J']);rl,rh=energy_interval(r['true_H_weighted_energy_J'])
            diff=[rl-hh,rh-hl];rate=[100*(1-hh/rl),100*(1-hl/rh)]
            edits=changes(h['candidate'],r['candidate'])
            entry.update(same_true_H_inputs=h['truth_H_input_sha256']==r['truth_H_input_sha256'] and h['truth_H_config_sha256']==r['truth_H_config_sha256'],
                same_schedule=h['candidate_sha256']==r['candidate_sha256'],changed_stage_instances=len(edits),changes=edits,
                differing_device_rows=sum('unit' in x['fields'] for x in edits),differing_opp_rows=sum('opp' in x['fields'] for x in edits),
                differing_start_rows=sum('start_ms' in x['fields'] for x in edits),
                H_energy_J=h['true_H_weighted_energy_J'],R_energy_J=r['true_H_weighted_energy_J'],
                R_minus_H_J=serial_interval(diff),H_saving_relative_to_R_percent=serial_interval(rate),
                R_minus_H_J_float=list(map(float,diff)),H_saving_relative_to_R_percent_float=list(map(float,rate)),
                strict_winner='H' if diff[0]>0 else 'R' if diff[1]<0 else 'NOT_SEPARATED_BY_ENCLOSURES')
            check(problem+'_both_use_same_true_H',entry['same_true_H_inputs'])
        pairs.append(entry)
    actual_plan_s=sum(v.get('planning_elapsed_s',0) for v in slots)
    actual_post_s=sum(v.get('post_elapsed_s',0) for v in slots)
    facts={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Terminal stored JSON and exact Fraction arithmetic only. No optimization, candidate evaluation, schedule validator or thermal integration.',
        'passed':all(v['passed'] for v in checks),'checks':checks,'declaration_sha256':digest(PRE/'execution_declaration.json'),
        'scientific_source_files':len(declaration['expected_sha']),'source_drift':drift,'slots':slots,'pairs':pairs,
        'budget':{'old_plans':1,'new_plans_consumed':ledger.get('plan_calls_consumed'),'audits_consumed':ledger.get('audit_calls_consumed'),
             'reserved_old_and_new_s':120+ledger.get('reserved_scientific_budget_s',0),'actual_recorded_plan_elapsed_s':actual_plan_s,
             'actual_recorded_post_elapsed_s':actual_post_s,'old_calendar_s':old_outer['calendar_elapsed_s'],'new_calendar_s':outer['calendar_elapsed_s'],
             'repair_gap_excluded':True,'no_first_plan_refund':True},
        'source_gate_note':'Frozen before supplementary gate03 arrival; gate01 was passed but bound the pre-schema-compatibility freeze. Frozen declaration binds actual final52 sources. Supplement03 independently binds actual same sources; only static status-format probe changed, no scientific source/budget/algorithm difference.',
        'terminal':terminal,'outer_terminal':outer}
    (destination/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=[]
    for s in slots:
        energy=s.get('true_H_safe_U_J','未取得真H SAFE')
        rows.append(f"|{s['slot']['problem_id']}/{s['slot']['view']}|{s.get('planning_state','未运行')}|{s.get('planning_elapsed_s','—')}|{s.get('post_status','未后验')}|{energy}|")
    note='# K178终态内部独立只读审查\n\n'+('核查通过。' if facts['passed'] else '存在未通过核查，先解释具体项。')+' 本报告只读归档，不替代实际独立真实H后验。\n\n|槽|规划状态|规划秒|真H后验|完整能耗上界J|\n|---|---|---:|---|---:|\n'+'\n'.join(rows)+'\n\n'
    for p in pairs:
        if p['both_true_H_SAFE']:
            note+=f"- {p['problem_id']}：调度{'相同' if p['same_schedule'] else '不同'}；严格较低能耗={p['strict_winner']}；相对R节能{p['H_saving_relative_to_R_percent_float']}%；设备/OPP/起点变化行数={p['differing_device_rows']}/{p['differing_opp_rows']}/{p['differing_start_rows']}。\n"
        else:note+=f"- {p['problem_id']}缺少双方完整真H安全结果，不能作成对能耗判断。\n"
    note+='\n旧首槽只恢复原已存最终best，未重跑、不改候选，唯一后验计入60秒。原异常、STOP和claim保持。新增最多3规划及4后验600秒，加旧已消费120秒总上限720；修复等待间隔与两段实际运行日历分别披露。\n\n结果只回答声明抽象H真值、两题及既定HEFT下响应信息的决策价值，不证明实机精度、公式原创、普遍节能或最优性。\n'
    (destination/'independent_review.md').write_text(note,encoding='utf-8')
    print(json.dumps({'passed':facts['passed'],'checks':len(checks),'pairs':[{k:v for k,v in p.items() if k not in ('changes',)} for p in pairs],
        'budget':facts['budget'],'failed':[v['name'] for v in checks if not v['passed']]},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=NEW/'analysis01');args=parser.parse_args();run(args.out.resolve())
