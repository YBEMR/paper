"""Static K143 delivery: no method import, optimization, decoding or heat."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'AGENTS.md').is_file())
OLD=HERE.parent/'fair_comparison_preparation01'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    audit=read(HERE/'audit.json');timing=read(HERE/'timing_metrics.json')
    review=read(HERE/'verification.json');protocol=read(HERE/'followup_protocol.json')
    d=read(OLD/'declaration.json');ledger=read(OLD/'ledger.json')
    context=read(HERE/'phase_context.json');rev=read(HERE/'audit_revision_log.json')
    allowed={'__future__','ast','copy','fractions','hashlib','json','math','pathlib','csv'}
    imports=[]
    for name in ['review_budget_end.py','timing_audit.py','verify_delivery.py']:
        tree=ast.parse((HERE/name).read_text(encoding='utf-8'))
        imports.extend(n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom))
        imports.extend(a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names)
    checks={
        'source159_unchanged':len(d['source_sha256'])==159 and all(sha(REPO/n)==h for n,h in d['source_sha256'].items()),
        'K142_original301_unchanged':len(audit['raw_artifact_sha256'])==301 and all(sha(OLD/n)==h for n,h in audit['raw_artifact_sha256'].items()),
        'old_execution_not_rewritten':ledger['state']=='BLOCKED' and ledger['consumed']==2,
        'HEFT_SA_not_started':all(not (OLD/'claims'/(n+'.json')).exists() for n in ['heft','sa101']),
        'offline22_cases_pass':audit['passed'] is True and len(audit['data_only_cases'])==22 and all(c['passed'] for c in audit['data_only_cases']),
        'derived_status_preserves_SAFE_and_pending':audit['derived_interpretation']['execution_status']=='NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST' and audit['derived_interpretation']['safe_witness_preserved'] is True and audit['derived_interpretation']['last_request']=='UNRESOLVED',
        'old19_revision_preserved':read(HERE/'audit_revision01.json')['data_only_case_count']==19 and rev['revision02_case_count']==22,
        'independent_static_review8_pass':review['passed'] is True and review['checks_count']==8,
        'timing_data_checks6_pass':timing['passed'] is True and len(timing['checks'])==6 and all(timing['checks'].values()),
        'timing_sources13_unchanged':len(timing['sources_sha256'])==13 and all(sha(REPO/n)==h for n,h in timing['sources_sha256'].items()),
        'timing_extractor_identity_matches':sha(HERE/'timing_audit.py')==timing['extraction_script_sha256'],
        'first_strict_is160344_and_phase2_unobserved':timing['methods']['linked_n1']['first_strict_improvement_at_s']==audit['first_strict_improvement_vs_initial_at_s'] and audit['phase2_strict_improvement_at_s'] is None,
        'followup_protocol_md_matches':protocol['protocol_md_sha256']==sha(HERE/'followup_protocol.md'),
        'followup_input_identities_match':protocol['input_identities']==d['input_identities'],
        'followup_only_HEFT_SA_once300':protocol['method_order']==[{'id':'heft','method':'heft','seed':None},{'id':'sa101','method':'sa','seed':101}] and protocol['method_call_limit']==2 and protocol['per_method_root_budget_s']==300,
        'no_followup_execution_authorization_or_claim':protocol['execution_authorized_this_stage'] is False and protocol['claims_created_this_stage'] is False and not (HERE.parent/protocol['planned_run_id']).exists(),
        'no_production_change_or_experiment':context['research_calls']==context['native_solver_calls']==context['thermal_evaluations']==context['production_source_changes']==0,
        'only_stdlib_audit_imports':set(imports)<=allowed,
        'four_project_records_synced':all('K.143' in (REPO/n).read_text(encoding='utf-8') for n in ['RESEARCH_BRIEF.md','research/03_证据与检索记录.md','research/第三章当前进展与正式实验推进计划_审查稿.md','research/chapter3_experiments/README.md'])}
    report={'stage':'K143','passed':all(checks.values()),'check_count':len(checks),'checks':checks,
        'scope':'static delivery only; no production/runtime fix or new research execution',
        'new_research_calls':0,'new_thermal_evaluations':0}
    (HERE/'delivery_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return report['passed']

if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
