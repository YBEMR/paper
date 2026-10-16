"""One fault-isolation run: original model, IntegerPreprocess='none' only.

This script does not alter active sources or any research input. It is not a
performance comparison and does not feed a known candidate to the solver.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys

import numpy as np
from scipy.io import loadmat

OUT = Path(__file__).resolve().parent
PACKAGE = OUT.parents[1]
sys.path.insert(0, str(PACKAGE))
import matlab_bridge as bridge


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


source = PACKAGE / 'results/milp_precheck03/matlab/request_000005.mat'
active = {p.name: digest(p) for p in [PACKAGE/'matlab_bridge.py', PACKAGE/'solve_model.m']}
temporary_source = OUT / 'worker_source'
temporary_source.mkdir(exist_ok=False)
original_text = (PACKAGE/'solve_model.m').read_text(encoding='utf-8')
needle = "'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6, ..."
assert original_text.count(needle) == 1
diagnostic_text = original_text.replace(needle, needle + "\n            'IntegerPreprocess','none', ...", 1)
(temporary_source/'solve_model.m').write_text(diagnostic_text, encoding='utf-8')
info = {
    'scope': 'single_solver_integer_preprocess_fault_isolation_not_formal_experiment',
    'original_model_path': str(source), 'original_model_sha256': digest(source),
    'active_source_sha256_before': active,
    'temporary_worker_sha256': digest(temporary_source/'solve_model.m'),
    'only_solver_option_change': {'IntegerPreprocess': {'before': 'basic', 'after': 'none'}},
    'model_transformation': None, 'known_candidate_injected': False,
    'formal_performance_comparison': False,
}
save(OUT/'diagnostic_manifest.json', info)
shutil.copy2(source, OUT/'original_model.mat')
p = loadmat(source)
model = {name: p[name] for name in ['A', 'Aeq']}
for name in ['c', 'b', 'beq', 'lb', 'ub']:
    model[name] = p[name].reshape(-1)
model['intcon'] = p['intcon'].reshape(-1)-1
model['metadata'] = info
# Only this Python process launches the isolated worker copy. The imported
# bridge implementation and repository preference directory are unchanged.
bridge.HERE = temporary_source
with bridge.MatlabSession(OUT/'matlab', total_budget_s=180) as session:
    result = session.solve(model, remaining_s=60)
summary = {key: result.get(key) for key in [
    'status', 'exitflag', 'fval', 'budget_valid', 'accepted_for_evaluation',
    'output', 'wall_seconds']}
if result.get('x'):
    x = np.asarray(result['x'])
    summary['original_max_row_residual'] = float(np.max(p['A'] @ x-p['b'].reshape(-1)))
    summary['original_max_bound_residual'] = float(max(
        np.max(p['lb'].reshape(-1)-x), np.max(x-p['ub'].reshape(-1))))
    indices = model['intcon'].astype(int)
    summary['integer_residual'] = float(np.max(abs(x[indices]-np.round(x[indices]))))
    summary['original_complete_objective'] = float(p['c'].reshape(-1) @ x)
    # References are read strictly after solving and never sent to MATLAB.
    from inputs import load_config
    from run_milp_precheck import fixtures, candidate_key
    from milp import build_model, decode
    from thermal import Budget
    cfg = load_config()
    instance, starts = fixtures(cfg)['one_stage_energy']
    original_model = build_model(instance, cfg, starts=starts, budget=Budget(seconds=120))
    candidate = decode(original_model, x)
    summary['decoded_candidate'] = candidate
    oracle = json.loads((PACKAGE/'results/milp_precheck03/complete_thermal_oracle.json').read_text(encoding='utf-8'))
    matched = [r for r in oracle if candidate_key(r['candidate']) == candidate_key(candidate)]
    assert len(matched) == 1
    evaluation = matched[0]['evaluation']
    summary['postsolve_matching_oracle_state'] = evaluation['state']
    summary['postsolve_matching_oracle_energy_J'] = evaluation['weighted_energy_J']
    summary['postsolve_all_six_oracle_energies_J'] = [r['evaluation']['weighted_energy_J'] for r in oracle]
active_after = {p.name: digest(p) for p in [PACKAGE/'matlab_bridge.py', PACKAGE/'solve_model.m']}
summary['active_sources_unchanged'] = active == active_after
save(OUT/'summary.json', summary)
print(json.dumps(summary, ensure_ascii=False))
