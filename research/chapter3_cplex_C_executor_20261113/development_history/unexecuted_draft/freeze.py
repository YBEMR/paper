"""Freeze D283 code, prior inputs and pure controls. Never loads a native model."""
import argparse,ast,copy,importlib,sys
from pathlib import Path
from core import read,save,sha,verify
from environment import snapshot

def main():
    a=argparse.ArgumentParser();a.add_argument('--workspace',type=Path,required=True);a.add_argument('--controls',type=Path,required=True);args=a.parse_args()
    root=args.workspace.resolve();here=Path(__file__).resolve().parent;controls=args.controls.resolve()
    base=root/'work/publish_repo/research/chapter3_cplex_full_C_preflight_20261113'
    prior=read(base/'D283_candidate.json');tests=read(controls/'results.json')
    assert tests['passed'] and tests['CPLEX_imported'] is False and tests['optimization_calls']==tests['thermal_evaluations']==0
    source_hashes={p.name:sha(p) for p in sorted(here.glob('*.py'))}
    assert tests['code_hashes']==source_hashes,'Controls not run against final source'
    verify(root,prior['input_hashes']);verify(root,prior['evaluation_source_hashes']);verify(Path('/'),prior['runtime_hashes'])
    # D282 files remain byte-for-byte frozen, including its consumed one-use record.
    prior_manifest=read(base/'manifest.json');verify(base,prior_manifest['files'])
    plan=copy.deepcopy(prior)
    plan.update(protocol='D283-CPLEX-saved-C-executor-v1',status='FROZEN_AWAITING_NEW_APPROVAL',execution_authorized=False,
        base_commit='01c419220c0507a6d63119ede62b96c8ba985e57',D282_candidate_sha256=sha(base/'D283_candidate.json'),
        scientific_solver_driver_delivered=True,ready_to_execute=False,ready_to_execute_after_new_approval=True,
        ready_to_request_independent_scientific_authorization=True,
        remaining_execution_condition='New direct user approval binding this plan and frozen commit; no scientific calls in preparation phase',
        repository_package='research/chapter3_cplex_C_executor_20261113/executor',execution_directory='work/cplex_C_scientific_execution_v1',
        code_hashes=source_hashes,environment=snapshot(),bound_objective_consistency_tolerance=1e-7,
        scene_ids=[x['id'] for x in read(root/'work/stable_expression/full/input_instance.json')['scenarios']],
        controls=dict(path=controls.relative_to(root).as_posix(),results_sha256=sha(controls/'results.json'),tests_run=tests['tests_run']),
        approval_schema=dict(protocol='D283-CPLEX-one-solve-approval-v1',decision='APPROVE',plan_sha256='must match this frozen plan',maximum_solve_calls=1,total_window_s=600,response_cutoff_s=550,retries=0,scope='SAVED_COMPLETE_C_CPLEX_ONE_SOLVE',approval_id='new unique user decision',user_message_reference='actual new user message, not an inherited authorization',frozen_commit='40 hex SHA containing this plan and source'),
        clarification_from_candidate=['Complete final response must be parent-read and hash-verified before 550; no worker-timestamp substitution',
            'Scientific snapshot must be parent-read and verified before 590, archive/cleanup before 600; delayed control results can only revoke credit',
            'Native errors, memory-limit status and numerical-failure status stop before final thermal evaluation; preserve raw receipt/vector separately',
            'Numerical bound/objective inconsistency threshold 1e-7 * max(1,abs(objective),abs(lower),abs(upper)); this is not an exact infeasibility proof',
            'Information callback vector only on first/changed objective; not guaranteed to expose all internal incumbents or equal-objective schedule changes'])
    limits=dict(prior['resource_limits']);limits.update(total_window_s=600,native_response_cutoff_s=550,scientific_seal_s=590,emergency_cleanup_only_cutoff_s=620)
    plan['limits']=limits
    # Hash active numerical extension binaries as well as package versions; no solver imports.
    for name in ('numpy','numpy.core._multiarray_umath','scipy','scipy.sparse._sparsetools','scipy.io.matlab._mio5_utils','_decimal','psutil'):
        module=importlib.import_module(name);p=Path(module.__file__).resolve();plan['runtime_hashes'][p.as_posix()]=sha(p)
    for p in sorted(base.rglob('*')):
        if p.is_file():plan['input_hashes'][p.relative_to(root).as_posix()]=sha(p)
    # Static check against locally installed 22.2 public API source, without creating an environment.
    api_root=Path('F:/Anaconda3/Lib/site-packages/cplex')
    source=(api_root/'callbacks.py').read_text(encoding='utf-8')
    needed=['MIPInfoCallback','get_incumbent_values','get_MIP_relative_gap','get_num_nodes','get_num_iterations','has_incumbent']
    assert all(name in source for name in needed)
    tree=ast.parse((here/'native.py').read_text(encoding='utf-8'))
    solve_sites=[x.lineno for x in ast.walk(tree) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='solve']
    assert len(solve_sites)==1
    save(here/'static_compatibility.json',dict(installed_API='22.2.0.0',CPLEX_imported='cplex' in sys.modules,native_objects=0,
        callback_symbols=needed,callback_source_sha256=sha(api_root/'callbacks.py'),one_solve_source_line=solve_sites[0],
        real_runtime_limit='Parameter ranges/defaults from D282; actual new parameters/search/acceptance untested until separately approved call'))
    save(here/'plan.json',plan);save(here/'plan.identity.json',dict(sha256=sha(here/'plan.json'),execution_authorized=False))
    print(sha(here/'plan.json'))
if __name__=='__main__':main()
