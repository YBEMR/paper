"""Freeze the user-authorized one no-solve load after pure controls pass."""
from pathlib import Path
import json,subprocess
from common import read,save,sha
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
repo=ROOT/'work/publish_repo'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()=='0432540d7ce80abf49475647139bc7afe5ca2acf'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD^'],text=True).strip()=='9b68ccb33bf200a15be8e5993fa298d27b666320'
controls=read(ROOT/'work/cplex_C_controls_v1/results.json')
assert controls['passed'] and controls['CPLEX_objects']==0 and controls['tests_run']==22
audit=read(repo/'research/chapter3_solver_port_preparation_20261113/evidence/saved_transport_audit.json')
inputs=dict(audit['source_hashes']);matrices={}
for label,name,base in [('original','original_zero_based.mat',0),('complement','matlab/request_000001.mat',1)]:
    r=audit['records'][name];path='work/mechanism_trials_execution_v1/C_noheur/'+name
    inputs[path]=r['file_sha256'];matrices[label]=dict(path=path,intcon_base=base,canonical_arrays_sha256=r['canonical_arrays_sha256'])
prior={}
for folder,manifest,key in [('chapter3_solver_port_preparation_20261113','release_manifest.json','files'),
                           ('chapter3_cplex_environment_setup_20261113','manifest.json','files')]:
    location=repo/'research'/folder
    for path,h in read(location/manifest)[key].items():
        assert sha(location/path)==h;prior[str((location/path).relative_to(ROOT)).replace('\\','/')]=h
inputs.update(prior)
for path,h in inputs.items():assert sha(ROOT/path)==h,path
runtime_files=[Path('F:/CPLEX/CPLEX_Studio222/cplex/bin/x64_win64/cplex2220.dll'),Path('F:/Anaconda3/python.exe')]
cplex=Path('F:/Anaconda3/Lib/site-packages/cplex')
runtime_files+=sorted(cplex.rglob('*.py'))+sorted(cplex.rglob('*.pyd'))+sorted(cplex.rglob('*.dll'))
limits=dict(total_window_s=300,worker_deadline_s=280,cleanup_reserve_s=20,worker_hard_commit_bytes=2*2**30,
    worker_soft_private_bytes=int(1.8*2**30),parent_private_bytes=512*2**20,
    minimum_available_at_entry_bytes=3*2**30,system_available_floor_bytes=2**30,
    sample_period_s=.1,evidence_cap_bytes=64*2**20)
parameters={'threads':1,'randomseed':0,'parallel':1,'clocktype':2,'timelimit':'N(t)',
    'lpmethod':0,'mip.strategy.search':0,'preprocessing.presolve':1,
    'simplex.tolerances.feasibility':1e-9,'simplex.tolerances.optimality':1e-7,
    'mip.tolerances.integrality':1e-6,'mip.tolerances.mipgap':0.,'mip.tolerances.absmipgap':0.,
    'mip.limits.nodes':10000000,'workmem':1024.,'mip.limits.treememory':1024.,
    'mip.strategy.file':0,'mip.display':4,'simplex.display':1,'barrier.display':1,'mip.interval':100}
plan=dict(protocol='D282-CPLEX-C-native-load-no-solve-v1',date='2026-11-13',
    base_commit='0432540d7ce80abf49475647139bc7afe5ca2acf',parent_commit='9b68ccb33bf200a15be8e5993fa298d27b666320',
    user_decision_reference='Current D282 request explicitly permits one bounded full saved C native-object load/readback after pure controls; forbids all optimization',
    native_load_authorized=True,optimization_authorized=False,maximum_native_model_loads=1,retries=0,
    maximum_optimization_calls=0,maximum_MATLAB_sessions=0,maximum_full_R1_rebuilds=0,maximum_thermal_evaluations=0,
    python='F:/Anaconda3/python.exe',cplex_version='22.2.0.0',
    python_dll='F:/Anaconda3/Lib/site-packages/cplex/_internal/cplex2220.dll',
    execution_directory='work/cplex_C_load_execution_v1',block_rows=2048,
    limits=limits,code_hashes={p.name:sha(p) for p in sorted(HERE.glob('*.py'))},
    input_hashes=inputs,runtime_hashes={str(p).replace('\\','/'):sha(p) for p in runtime_files},matrices=matrices,
    projection_certificate='work/mechanism_trials_execution_v1/C_noheur/representation_certificate.json',
    expected=dict(variables=23780,integer_variables=1125,inequalities=94958,equalities=6860,nnz=1004625),
    MIP_start=dict(length=23780,effort='check_feasibility=1',policy='store/read only; no optimizer acceptance claim'),
    original_matrix_policy='Read/check every saved original array; one native object uses complement matrix. Original relation is by existing hash-bound exact projection certificate plus native bitwise equality; no second original-model native object',
    coordinate_policy='Keep row/column IDs unchanged; sparse storage may be traversed in canonical row order only with every coordinate-value tuple preserved and certified by D281 array hashes. Native readback ordering must match exactly; no repair',
    D283_proposed_parameters=parameters,
    D283_note='Only read supported ranges/defaults now. No parameter changes or native optimization. D283 candidate may be issued only after D282 PASS',
    controls=dict(result_path='work/cplex_C_controls_v1/results.json',sha256=sha(ROOT/'work/cplex_C_controls_v1/results.json'),tests=22),
    stop_rules=['Any input/code/runtime mismatch stops before native model',
        'Worker dispatched only after Windows Job hard cap/active-process=1/kill-on-close readback',
        'Below3GiB free at entry => consume attempt, no model; never auto-retry',
        'At280 seconds or resource threshold => terminate owned Job, at most20 seconds cleanup; no late evidence credit',
        'At300 seconds => total-budget failure; cleanup still mandatory and overrun reported',
        'Any load/readback/permission/license/memory error => preserve failure, never alter matrix to pass',
        'Start roundtrip never means solver acceptance',
        'No solve/presolve/LP/MILP/IIS/conflict/feasopt/tuning or thermal evaluation; no D283 auto-execution'],
    science_boundary='Model size and binary64 transport proof only; root LP, optimization, full SAFE and energy improvement remain untested')
save(HERE/'plan.json',plan);save(HERE/'plan.identity.json',dict(sha256=sha(HERE/'plan.json')))
print(json.dumps(dict(plan_sha256=sha(HERE/'plan.json'),input_files=len(inputs),runtime_files=len(runtime_files),controls=22)))
