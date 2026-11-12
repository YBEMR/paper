"""Ten separate scientific layers; no external initial witness counted as native output."""
from representation import digest

def layers(runtime,r):
    n=r.get('native') or {};v=r.get('returned_vector_validation') or {};p=r['progress']
    return {
        '1_model_input':dict(input_identity=runtime.plan['input_identity'],arm=runtime.arm,model_arm=runtime.model_arm,Heuristics=runtime.trial['Heuristics'],
            fresh_full_model_completed_at_s=getattr(runtime,'model_completed_at_elapsed_s',None),
            exact_projection_completed_at_s=getattr(runtime,'certificate_completed_at_elapsed_s',None),
            source_and_lifecycle_verified=r['lifecycle_integrity']),
        '2_root_LP':dict(entry_observed=p['root_lp_entry_observed'],completion_observed=p['root_lp_completion_observed'],
            completion_basis=p['root_lp_completion_basis'],native_root_objectives=p['root_lp_native_objectives']),
        '3_native_bound':dict(records=p['finite_bounds'],best_consistent=p['best_consistent_native_bound'],
            conflict=r['native_bound_conflict'],independently_certified=False,source='Timestamped native callback publications'),
        '4_native_candidate':dict(vector_present=bool(n.get('x')),vector_sha256=digest(n['x']) if n.get('x') else None,
            vector_source='Final native response only; callback vectors archived but not substituted',
            candidate_identity=digest(r['candidate']) if r.get('candidate') else None),
        '5_original_and_represented_admission':dict(state=v.get('state','UNKNOWN'),original=v.get('original_rows'),
            represented=v.get('transformed_rows'),strict_feasibility_certificate=False),
        '6_schedule_legality':v.get('legality',{'state':'UNKNOWN'}),
        '7_complete_two_scene_SAFE':dict(returned_complete_SAFE=r['returned_complete_SAFE'],
            evaluation=r.get('returned_evaluation'),usable=r['returned_complete_SAFE'] and r['evidence_integrity']),
        '8_different_schedule':dict(same_initial=r['same_initial'],new_complete_SAFE=r['new_complete_SAFE']),
        '9_strict_full_energy_improvement':dict(established=r['strict_energy_improvement'],
            criterion='returned upper < initial lower AND different schedule',identity_conflict=r['energy_identity_conflict']),
        '10_independent_optimality':dict(established=False,status='UNKNOWN; native status/gap is not independent proof')}
