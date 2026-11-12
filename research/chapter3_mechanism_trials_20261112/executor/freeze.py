"""Freeze the finite repeatability and one-variable mechanism plan; never execute science."""
from pathlib import Path
import sys
from guard import read,save,sha,verify_plan,TRIALS,environment_snapshot

def freeze(workspace):
    workspace=workspace.resolve();package=Path(__file__).resolve().parent
    previous=read(workspace/'work/formal_abc_v1/plan.json')
    # Preserve every prior scientific source/input binding and add immutable historical audit provenance.
    sources=dict(previous['workspace_files'])
    for rel in ['work/formal_abc_v1/plan.json','work/formal_abc_execution_audit/audit.json',
                'work/formal_abc_execution_audit/native_artifact_audit.json']:
        sources[rel]=sha(workspace/rel)
    original=workspace/'work/equality_pair_source/research/chapter3_experiments/solve_model.m'
    variant=package/'native_none/solve_model.m'
    line="        opts.Heuristics = 'none'; % Predeclared mechanism trial; sole native option intervention.\n"
    if variant.read_bytes().replace(line.encode('utf-8'),b'')!=original.read_bytes():
        raise ValueError('Native variant is not exactly the single Heuristics assignment')
    plan=dict(previous)
    plan.update(protocol='full-R1-mechanism-trials-v1',base_commit='3baeae859d0370da183c108cd4f6de869db09fec',
        execution_authorized=False,arms=list(TRIALS),trials=TRIALS,
        order_policy='C_repeat then B_repeat then C_noheur; ordinary limits do not gate independent trials',
        execution_directory='work/mechanism_trials_execution_v1',
        purposes={'C_repeat':'Finite fresh C repeat, first position rather than historical third position',
                  'B_repeat':'Finite fresh B repeat, same full method budget and native options',
                  'C_noheur':'Single predeclared intervention Heuristics=none; all other model, initialization, expression, tolerances and dynamic budget settings unchanged'},
        maximum_native_calls_batch=3,maximum_MATLAB_sessions_batch=3,maximum_full_builds_batch=3,
        experimental_success='Different final native schedule AND in-window original/new numerical admission, independent legality, complete two-scene SAFE AND returned energy upper < common initial energy lower',
        mechanism_success='Root LP completion, finite native lower bound, branching/node progress separately reported; none substitutes strict physical improvement',
        statistical_scope='One fresh B and C repeat only; descriptive evidence, no significance, acceleration ratio or general repeatability claim',
        native_intervention={'trial':'C_noheur','option':'Heuristics','from':'basic','to':'none','all_other_options':'unchanged except common dynamic MaxTime'},
        native_script_variant={'path':'native_none/solve_model.m','only_change':"opts.Heuristics = 'none';",'original_sha256':sha(original),'variant_sha256':sha(variant)},
        root_callback_semantics='R2023b rootlp callback itself means completed root LP; raw fval is root relaxation objective, distinct from later lowerbound and integer candidate',
        scientific_cache_policy=previous['scientific_cache_policy'],
        approval_policy='Current user instruction authorizes design then execution; bind the final concrete plan SHA to that instruction in a NEW approval and consume it once. Prior ABC and ON authorizations remain consumed.',
        correctness_stop_policy={'shared_input_source_expression_or_unknown':'ALL',
            'independent_support_certificate_failure':['B','C'],'joint_certificate_failure':['C'],
            'model_scope_mapping':'Affected model arm stops every pending trial with that model arm; trial-local fault stops only the named trial',
            'native_bound_conflict_with_verified_identity':'current trial; other trials may continue',
            'cleanup_failure_or_untracked_worker_exit':'ALL'},
        environment=environment_snapshot(),workspace_files=sources,
        package_files={str(p.relative_to(package)).replace('\\','/'):sha(p)
            for p in sorted([*package.glob('*.py'),*package.glob('native_none/*.m')])},
        historical_audit_only=True,prior_scientific_authorizations_reused=False)
    plan.pop('preflight_audit_sha256',None)
    save(package/'plan.json',plan);identity=sha(package/'plan.json')
    save(package/'plan.identity.json',dict(sha256=identity))
    save(package/'approval.template.json',dict(approved=False,plan_sha256=identity,protocol=plan['protocol'],arms=plan['arms'],
        maximum_native_calls_per_arm=1,total_window_s=600,retries=0,user_decision_reference=''))
    verify_plan(package/'plan.json',workspace,package)
    save(package/'freeze_receipt.json',dict(plan_sha256=identity,source_files=len(plan['workspace_files']),
        package_files=len(plan['package_files']),verified=True,execution_authorized=False,
        execution_ledger_exists=(workspace/plan['execution_directory']).exists(),new_scientific_calls=0))
    print(identity)

if __name__=='__main__':freeze(Path(sys.argv[1]))
