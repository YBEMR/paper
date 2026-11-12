"""Freeze only. Does not create an approval, execution claim or scientific process."""
from pathlib import Path
import sys,platform
from guard import read,save,sha,verify_plan

def freeze(workspace):
    package=Path(__file__).resolve().parent
    previous=read(workspace/'work/budget_protocol_v2/candidate_on/plan.json')
    sources=list((workspace/'work/equality_pair_source/research/chapter3_experiments').glob('*.py'))
    sources+=list((workspace/'work/equality_pair_source/research/chapter3_experiments').glob('*.m'))
    sources+=list((workspace/'work/equality_pair_source/research/v1_evaluator').glob('*.py'))
    sources+=[workspace/'work/stable_expression/complement_gate.py',workspace/'work/stable_expression/full/input_instance.json',
              workspace/'work/stable_expression/full/input_config.json',workspace/'work/equality_pair_source/bundle_manifest.json']
    import numpy,scipy,psutil
    plan=dict(protocol='full-R1-fresh-ABC-v1',base_commit='77ecc3d4b2f5a46ac4e806abc6fb9461a20db741',
        execution_authorized=False,arms=['A','B','C'],order_policy='A then B then C; ordinary limits do not gate independent arms',
        maximum_native_calls_per_arm=1,maximum_MATLAB_sessions_per_arm=1,maximum_full_builds_per_arm=1,
        maximum_initial_schedule_attempts_per_arm=3,maximum_complete_evaluations_per_arm=4,
        final_candidate_evaluations_per_arm=1,retries=0,total_window_s=600,response_cutoff_s=550,watchdog_s=680,
        cleanup_monitor_wait_s=10,native_cap_ceiling_s=540,native_cap_minimum_s=30,dispatch_reserve_s=10,validation_reserve_s=50,
        allocation_function='N(t)=floor(min(540,max(0,600-t-10-50))); submit only N>=30; t sampled after MAT serialization before request JSON',
        input_identity=previous['input_identity'],initial_candidate_identity=previous['initial_candidate_identity'],
        baseline_flags=read(workspace/'work/equality_pair_source/bundle_manifest.json')['baseline_flags'],
        arm_switches={'A':dict(propagate_support=False,prune_joint_states=False),
                     'B':dict(propagate_support=True,prune_joint_states=False),
                     'C':dict(propagate_support=True,prune_joint_states=True)},
        native_options=dict(previous['native_options'],MaxTime='N(t), identical allocation function for all arms'),
        matlab=previous['matlab'],representation='complement_gate_split_constant_v1',
        execution_directory='work/formal_abc_execution_v1',
        lifecycle='Fresh Python process, source verification, input, full build, reduction replay, deterministic initial SAFE, continuous x0, exact representation, numerical admission, archive, fresh MATLAB, transport, native solve, original/new admission, legality, full SAFE, cleanup, source recheck',
        scientific_cache_policy='Only intra-arm model-local caches; never load preflight/historical matrices, vectors, evaluations or certificates in formal preparation',
        limits_scope='600 is scientific evidence cutoff, not hard process-wall promise; cleanup and controller overhead are fully reported and charged actual wall',
        initial_policy='Same deterministic initial-schedule-v1 rule, <=3 attempts; first SAFE must match the common schedule identity; no saved witness reuse',
        candidate_policy='Only timely final native vector; callback vectors archived, no callback substitution, repair, second call, or post-window evaluation',
        bound_policy='Native-only finite bound with provenance and consistency against numerically admitted MILP objective; never an independent strict certificate',
        correctness_stop_policy={'shared_input_source_expression_or_unknown':'ALL',
            'independent_support_certificate_failure':['B','C'],'joint_certificate_failure':['C'],
            'native_bound_conflict_with_verified_identity':'current arm; other arms may continue',
            'cleanup_failure_or_untracked_worker_exit':'ALL'},
        ordinary_stop_policy='Budget insufficient, ordinary timeout, no vector, rejected vector, non-SAFE or no improvement stop current arm without retry and continue others after complete cleanup',
        approval_policy='Separate explicit user authorization must bind this plan SHA; old ON approvals are invalid; the whole batch and each arm have exclusive one-use claims',
        software_guard_scope='Local integrity guard, not a cryptographic authorization boundary',
        environment=dict(python=sys.version,python_executable=sys.executable,platform=platform.platform(),
                         numpy=numpy.__version__,scipy=scipy.__version__,psutil=psutil.__version__),
        workspace_files={str(p.relative_to(workspace)).replace('\\','/'):sha(p) for p in sorted(set(sources))},
        package_files={p.name:sha(p) for p in sorted(package.glob('*.py'))},
        preflight_audit_sha256=sha(workspace/'work/formal_abc_preflight_v1/final_audit.json'))
    save(package/'plan.json',plan);identity=sha(package/'plan.json');save(package/'plan.identity.json',dict(sha256=identity))
    save(package/'approval.template.json',dict(approved=False,plan_sha256=identity,protocol=plan['protocol'],arms=plan['arms'],
        maximum_native_calls_per_arm=1,total_window_s=600,retries=0,user_decision_reference=''))
    verify_plan(package/'plan.json',workspace,package)
    save(package/'freeze_receipt.json',dict(plan_sha256=identity,source_files=len(plan['workspace_files']),
        package_files=len(plan['package_files']),verified=True,execution_authorized=False,
        execution_ledger_exists=(workspace/plan['execution_directory']).exists()))
    print(identity)

if __name__=='__main__':freeze(Path(sys.argv[1]).resolve())
