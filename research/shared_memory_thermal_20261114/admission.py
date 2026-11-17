"""Data gate only. Missing joint parameters cannot launch a numerical experiment."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent;O=R/'results';O.mkdir(exist_ok=True)
p=json.loads((R/'parameter_contract.json').read_text(encoding='utf-8'));missing=[r['id'] for r in p['parameters'] if r['required_for_numeric'] and r['model_value'] is None]
out={'stage':'SMT20261114','status':'NO_NUMERIC_ADMISSION' if missing else 'REVIEW_REQUIRED_NOT_AUTOMATIC_RUN','missing_required':missing,'scope':'This file gates data sufficiency only; it is not a scheduler. No automatic experiment path exists.','numerical_schedule_evaluations':0,'synthetic_parameter_fills':0,'energy_improvement_pct':None,'reason':'Same-platform effective bandwidth/arbitration, task progress, full power and thermal-cap joint parameterization not identified.'}
(O/'admission.json').write_text(json.dumps(out,indent=2)+'\n')
ablations=[{'model':m,'memory_contention':b,'thermal_cap':h,'status':'NOT_RUN_DATA_GATE','selected_schedule':None,'full_model_energy':None,'full_model_feasible':None,'gain_pct':None} for m,b,h in [('M00',False,False),('M10',True,False),('M01',False,True),('M11',True,True)]]
baselines=[{'method':m,'information':i,'status':'NOT_RUN_DATA_GATE','schedule':None,'energy_in_M11':None,'feasible_in_M11':None,'gain_pct':None} for m,i in [('best_fixed_mapping_and_opps','offline_known_parameters_and_arrivals'),('memory_only_optimized','offline_known_memory_model'),('thermal_fixed_overlap','offline_known_model_fixed_eager_or_serial_overlap'),('best_at_most_one_template_switch','offline_known_future_and_initial_state'),('full_finite_legal_catalogue','offline_known_future_and_initial_state')]]
(O/'ablation_status.json').write_text(json.dumps(ablations,indent=2)+'\n');(O/'baseline_status.json').write_text(json.dumps(baselines,indent=2)+'\n')
print(json.dumps(out))
