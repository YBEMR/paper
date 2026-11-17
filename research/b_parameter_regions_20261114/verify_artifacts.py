"""Verify the persisted design, outputs and evidence boundaries without rerunning the scan."""
import csv,hashlib,json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
def rows(name):
    with (ROOT/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
checks=[]
def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    assert value,name

freeze=read('design_freeze.json');cfg=read('design.json');env=read('results/run_environment.json')
for name,sha in freeze['files'].items():check('frozen/'+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha)
for name,sha in env['files_sha256'].items():check('executed/'+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha)
check('67_scenarios',len(cfg['scenarios'])==67)
check('21_temperatures',len(cfg['temperatures_C'])==21)
check('92_actions',len(read('results/catalogue.json'))==92)
for file,count in [('scenario_summary.csv',134),('temperature_results.csv',2814),('all_action_aggregates.csv',12328),('analytic_regions.csv',67),('analytic_uncertainty_envelope.csv',21),('dynamic_corner_sign_envelope.csv',42)]:
    check('row_count/'+file,len(rows('results/'+file))==count)
raw=np.load(OUT/'all_candidate_arrays.npz',allow_pickle=False)
check('raw_shape',raw['energy'].shape==(67,2,92,21))
check('finite_energy',np.isfinite(raw['energy']).all())
check('component_balance',np.max(abs(raw['energy']-raw['components'].sum(axis=-1)))<1e-9)
check('cpu_control_shape',np.load(OUT/'cpu_fixed40_arrays.npz',allow_pickle=False)['energy'].shape==(2,92,21))
ledger=read('physical_evidence.json');table=rows('parameter_identifiability.csv')
check('evidence_23',len(ledger['parameters'])==len(table)==23)
check('unknown_16',sum(x['identified_value'] is None for x in ledger['parameters'])==16)
check('CSV_preserves_null',sum(x['identified_value']=='null' for x in table)==16)
check('uncalibrated_status',ledger['not_a_calibrated_AGX_model'])
check('prior_contract_byte_hash',ledger['prior_contract_sha256']==hashlib.sha256((ROOT/'input_evidence_contract.json').read_bytes()).hexdigest())
numerics=read('results/numerical_validation.json')
check('547_numeric_checks',numerics['checks']==547 and all(x['passed'] for x in numerics['checks_detail']))
check('144_independent_trajectories',numerics['independent_DOP853_trajectories']==144)
summary=read('results/interpretation.json')
for horizon,report in summary['overview'].items():
    data=[r for r in rows('results/scenario_summary.csv') if r['horizon']==horizon]
    check(horizon+'/max_gain',abs(max(float(x['oracle_gain_pct']) for x in data)-report['max_oracle_gain_pct'])<1e-12)
    check(horizon+'/39_common_fixed',report['cases_with_common_optimal_action']==39)
    check(horizon+'/23_SQ_flips',report['cases_with_SQ_sign_flip']==23)
    check(horizon+'/no_1pct',report['cases_oracle_meets_1pct']==0)
    check(horizon+'/negative_1pct_budget',all(float(x['oracle_one_percent_overhead_budget_J'])<0 for x in data))
check('dynamic_sign_ambiguity_42',sum(x['both_signs_among_corners']=='True' for x in rows('results/dynamic_corner_sign_envelope.csv'))==42)
report=(ROOT/'REPORT.md').read_text(encoding='utf-8')
for phrase in ['0.1126%','0.0123%','0.417840%','0.058247%','82.28%','89.22%','144条','547项','95%','null']:
    check('report_anchor/'+phrase,phrase in report)
result={'status':'PASS_ARTIFACT_CONSISTENCY','check_count':len(checks),'checks':checks,'scope':'Design, saved-result and evidence consistency only; not external review or hardware validation.'}
(OUT/'artifact_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'checks':len(checks)}))
