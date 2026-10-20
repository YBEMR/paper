"""Read-only K141 freeze/delivery checks. Never import or call a method."""
import ast
from pathlib import Path
import hashlib
import json

OUT=Path(__file__).resolve().parent
ROOT=next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    d=read(OUT/'declaration.json'); gate=read(OUT/'wrapper_checks.json')
    context=read(OUT/'phase_context.json'); review=read(OUT/'verification.json')
    l=read(OUT/'ledger.json'); audit=read(OUT/'source_audit.json')
    checks={}
    def check(name,value):
        checks[name]=bool(value)
        if not value: raise AssertionError(name)
    check('prepared_not_executed',l['state']=='DECLARED' and l['consumed']==0
          and l['method_budget_s_reserved']==0 and not l['calls'])
    check('claims_absent',not list((OUT/'claims').iterdir()) and not (OUT/'launcher_claim.json').exists()
          and not (ROOT/'research/chapter3_experiments/results/minimal_comparison_claim01.json').exists())
    check('four_independent_planned_jobs',[j['id'] for j in d['jobs']]==['whole_milp','linked_n1','heft','sa101']
          and d['method_call_limit']==4 and d['per_method_budget_s']==300 and d['jobs'][-1]['seed']==101)
    check('no_retries_or_extension',d['retry_allowed'] is False and d['extend_budget_allowed'] is False)
    check('source159_current_snapshot',len(d['source_sha256'])==159
          and all(sha(ROOT/p)==h and sha(OUT/'source_snapshot'/p)==h for p,h in d['source_sha256'].items()))
    base=read(ROOT/'research/chapter3_experiments/results/linked_quality_pair01/declaration.json')
    check('inherited157_unchanged',len(base['source_sha256'])==157
          and all(d['source_sha256'].get(p)==h for p,h in base['source_sha256'].items()))
    check('input_bytes_unchanged',all(sha(OUT/p)==h for p,h in d['input_file_sha256'].items()))
    check('mock_gate03_matches',gate['passed'] and gate['tests_run']==25 and gate['source_sha256']==d['source_sha256']
          and not any(gate['blocked_calls'].values())
          and all(gate[k]==0 for k in ['native_calls','research_calls','physical_models','thermal_evaluations']))
    check('inherited_evidence_scoped',audit['passed'] and audit['old_unchanged_count']==122
          and audit['old_changed_source_count']==3 and audit['no_current_whole_67_matching_claim'])
    check('context_hashes',all(context[k+'_sha256']==sha(OUT/p) for k,p in
          [('protocol','protocol.md'),('launcher','launcher.py'),('declaration','declaration.json'),('source_audit','source_audit.json')]))
    launcher=(OUT/'launcher.py').read_text(encoding='utf-8')
    ast.parse(launcher)
    check('future_launcher_bound','run_minimal_comparison.py' in launcher
          and "'--execution-authorized'" in launcher and "'research_call_limit':4" in launcher)
    check('independent_review_passed',review['passed'] and review['count']==24
          and all(item['passed'] for item in review['checks']))
    check('original_problem_unchanged',d['window_ms']==400 and d['start_grid_ms']==5
          and d['entry_temperature_degC']==50 and d['maximum_temperature_degC']==80
          and d['idle_policy']=='auto_low_immediate_v1')
    check('only_linked_has_fixed_units',d['shared_deployment_linked_only']==
          {'A.pre':'CPU1','A.main':'NPU0','A.post':'CPU1'} and
          d['whole_builder_options']=={'prefilter_deadlines':True,'cumulative_precedence':False})
    result={'stage':'K141','scope':'saved freeze and zero-consumption delivery identity only',
        'passed':all(checks.values()),'count':len(checks),'checks':checks,
        'new_model_thermal_native_research_calls':0}
    (OUT/'delivery_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'count':result['count'],'research_calls':0}))

if __name__=='__main__': main()
