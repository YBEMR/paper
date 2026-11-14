"""Non-simulation checks of evidence, gate states, symbols and archive integrity."""
import ast,csv,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent;C=R.parent/'shared_memory_sources';checks=[]
def check(n,b):
    checks.append({'name':n,'passed':bool(b)})
    if not b:raise AssertionError(n)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
check('protocol_identity',hashlib.sha256((R/'PROTOCOL.md').read_bytes()).hexdigest()==read(R/'protocol_freeze.json')['sha256'])
for p in R.glob('*.py'):
    if p.name in ['fetch_evidence.py','fetch_archive.py']:continue
    ast.parse(p.read_text(encoding='utf-8'));check('syntax/'+p.name,True)
for r in read(R/'source_manifest.json'):
    if r['status']=='UNAVAILABLE':continue
    p=C/r['id'];check('source/'+r['id'],p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'])
contract=read(R/'parameter_contract.json');check('all_missing_inputs_remain_null',all(x['model_value'] is None for x in contract['parameters']));check('no_numeric_fills',contract['synthetic_numeric_parameter_fills']==0)
gate=read(R/'results/admission.json');check('admission_not_granted',gate['status']=='NO_NUMERIC_ADMISSION' and gate['energy_improvement_pct'] is None and gate['numerical_schedule_evaluations']==0)
abl=read(R/'results/ablation_status.json');check('four_not_run_models',len(abl)==4 and all(x['status']=='NOT_RUN_DATA_GATE' and x['gain_pct'] is None for x in abl))
bas=read(R/'results/baseline_status.json');check('five_not_run_baselines',len(bas)==5 and all(x['energy_in_M11'] is None and x['feasible_in_M11'] is None for x in bas))
sym=read(R/'results/symbolic_checks.json');check('symbolic_checks_only',len(sym['checks'])==14 and all(x['passed'] for x in sym['checks']) and sym['numerical_schedule_evaluations']==0)
audit=read(R/'results/artifact_audit.json');check('negative_differences_retained',len(audit['negative_derived_differences'])==3 and all(x['layer_diff_ms']<0 for x in audit['negative_derived_differences']))
with (R/'results/hax_extracted_summaries.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
check('65_source_summary_rows',len(rows)==65)
check('paper_preflight_honest',all(read(p)['verdict']=='UNAVAILABLE' for p in (R/'provenance').glob('*.json')))
html=(R/'report.html').read_text(encoding='utf-8');check('report_contains_all_sections',all('id="'+s+'"' in html for s in ['report','sources','model','review']))
out={'status':'PASS_ARCHIVE_AND_SYMBOLIC_CONSISTENCY','checks':len(checks),'detail':checks,'numerical_model_status':'NOT_ADMITTED_NOT_RUN','scope':'File identity and internal consistency only; no real hardware, joint model calibration, or external review.'}
(R/'archive_validation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':out['status'],'checks':len(checks)}))
