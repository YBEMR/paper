"""Independent arithmetic and artifact-consistency checks, not physical validation."""
import csv,hashlib,json,math
from pathlib import Path
root=Path(__file__).resolve().parent
checks=[]
def check(name,condition):
    checks.append({'check':name,'passed':bool(condition)})
    assert condition,name
def readcsv(name):
    with (root/'results'/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
summary=json.loads((root/'results/audit_summary.json').read_text(encoding='utf-8'))
for manifest_name in ['source_manifest.json','auxiliary_manifest.json']:
    for e in json.loads((root/manifest_name).read_text(encoding='utf-8')):
        raw=(root/e['local_path']).read_bytes()
        check('sha256:'+e['path'],hashlib.sha256(raw).hexdigest()==e['sha256'])
p=readcsv('agx_profile_audited.csv')
check('all_1772_profile_rows',len(p)==1772)
check('preserved_214_label_mismatches',sum(r['label_matches_performance']=='False' for r in p)==214)
check('14_frequencies',len({r['frequency_Hz'] for r in p})==14)
for r in p:
    w=float(r['rail_sum_mean_W']);q=float(r['throughput_inferences_per_s']);l=float(r['server_latency_including_queue_s'])
    assert math.isclose(w*l,float(r['reported_P_times_L_J']),rel_tol=1e-12)
    assert math.isclose(w/q,float(r['steady_state_P_over_throughput_J_per_inference_PROXY']),rel_tol=1e-12)
check('energy_identities_all_rows_not_sensor_accuracy',True)
rs=readcsv('formula_residuals.csv')
check('all_throughput_residuals_zero',all(float(r['throughput_residual_per_s'])==0 for r in rs))
logs=readcsv('log_summary.csv');requests=readcsv('request_summary.csv')
check('nine_preselected_schedulers',len(logs)==len(requests)==9)
check('9749_samples',sum(int(r['samples']) for r in logs)==9749)
check('reported_energy_reproducible_with_nominal_200ms',all(abs(float(r['integral_residual_J']))<1e-9 for r in logs))
check('observed_intervals_differ_from_nominal',all(float(r['mean_interval_from_endpoints_s'])>0.22 for r in logs))
check('same_468_frames_31_requests',all(int(r['frame_rows'])==468 and int(r['unique_requests'])==31 for r in requests))
check('do_not_assume_all_deadlines_met',sum(int(r['late_frames']) for r in requests)>0)
contract=json.loads((root/'simulation_parameter_contract.json').read_text(encoding='utf-8'))
check('unknowns_stay_null',all(v is None for v in contract['unidentified_parameters'].values()))
check('no_hardware_claim',summary['decision']['temperature_dependent_policy_reversal']=='NOT_IDENTIFIED')
batch=json.loads((root/'results/batchdvfs_summary.json').read_text(encoding='utf-8'))
check('batchdvfs_80_tables_30_native',batch['members']==80 and batch['native_csv_files']==30)
check('batchdvfs_no_temperature_columns_in_examined_archive',batch['temperature_columns_found']==0)
check('duplicate_reports_not_repetitions',summary['exp1_duplicate_full_records']==54)
# Recheck the stated symbolic boundary on the PREVIOUS synthetic constants only.
K,dt=0.006,0.014
contrast=lambda T,beta:0.17+0.17*math.exp(beta*(T-40))
check('synthetic_constant_T_contrast_no_flip',K-dt*contrast(40,0)==K-dt*contrast(60,0))
check('synthetic_boundary_example',dt*contrast(40,.035)<K<dt*contrast(60,.035))
check('synthetic_effect_power_conversion',math.isclose(1.1960717464395/.4,summary['previous_synthetic_effect']['warm_effect_equivalent_average_power_mW']))
result={'status':'PASS_ARTIFACT_CHECKS_ONLY','passed':len(checks),'checks':checks,'not_validated':['hardware','causal_temperature_effect','thermal_model','power_calibration','statistical_significance']}
(root/'results/validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'passed':len(checks)}))
