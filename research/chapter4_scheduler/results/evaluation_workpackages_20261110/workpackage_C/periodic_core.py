"""Fixed-template posterior periodic review using the unchanged interval kernel.

No scheduling, model repair, parameter search or candidate generation exists.
Floating arithmetic supplies only a fixed-point candidate. All reported bounds
come from exact rational arithmetic and original outward interval propagation.
"""
from copy import deepcopy
from fractions import Fraction as F


def clip_period(segments,period_ms,makespan_ms):
    period=F(period_ms)
    if F(makespan_ms)>period:raise ValueError('FIXED_TEMPLATE_CANNOT_FIT_PERIOD')
    out=[]
    for old in segments:
        start,end=F(old['start_ms']),F(old['end_ms'])
        if start>=period:break
        row=deepcopy(old);row['end_ms']=str(min(end,period));row['duration_ms']=str(min(end,period)-start);out.append(row)
    if not out or F(out[0]['start_ms'])!=0 or F(out[-1]['end_ms'])!=period:raise ValueError('PERIOD_POWER_NOT_COVERED')
    for a,b in zip(out,out[1:]):
        if F(a['end_ms'])!=F(b['start_ms']):raise ValueError('POWER_GAP')
    return out


def contraction(platform,segments,period_ms):
    nodes=platform['node_order'];capacity=list(map(F,platform['heat_capacity_J_per_K']));g=[list(map(F,row)) for row in platform['conductance_W_per_K']]
    if len(nodes)!=4 or any(c<=0 for c in capacity):raise ValueError('FOUR_POSITIVE_CAPACITIES_REQUIRED')
    for i,row in enumerate(g):
        for j,v in enumerate(row):
            if v!=g[j][i] or i!=j and v>0:raise ValueError('NONPASSIVE_G')
    if any(F(s['local_leakage_slope_W_per_K'][node])<0 for s in segments for node in nodes):raise ValueError('NEGATIVE_LEAKAGE_BREAKS_ENERGY_ORDER')
    alpha=min((sum(g[i])-F(s['local_leakage_slope_W_per_K'][node]))/capacity[i] for s in segments for i,node in enumerate(nodes))
    if alpha<=0:raise ValueError('NO_RIGOROUS_INFINITY_CONTRACTION')
    period=F(period_ms)/1000;q=1/(1+alpha*period)
    return {'alpha_per_s':str(alpha),'q_rational_upper':str(q),'period_s':str(period),'proof':'4x4 temperature block Metzler; row sums<=-alpha. exp(-alpha*P)<=1/(1+alpha*P)<1 in the same unweighted infinity norm.'}


def residual_radius(candidate,end_intervals,q):
    q=F(q)
    if not 0<=q<1:raise ValueError('NONCONTRACTIVE_Q')
    residual=max(abs(F(v)-F(x)) for x,interval in zip(candidate,end_intervals) for v in interval)
    return residual,residual/(1-q)


def box_distance(a,b):
    return max(max(abs(F(x[0])-F(y[1])),abs(F(x[1])-F(y[0]))) for x,y in zip(a,b))


def combine_paths(lower,upper,platform,period_ms):
    """Order-preserving bounds, requiring both full trajectories in model range."""
    nodes=platform['node_order'];valid_lo,valid_hi=map(F,platform['power_model_temperature_range_degC']);period=F(period_ms)/1000;ambient=F(platform['ambient_temperature_degC'])
    for receipt in (lower,upper):
        if not receipt.get('complete') or F(receipt['covered_until_s'])!=period:raise ValueError('INCOMPLETE_PERIOD_PROPAGATION')
        if receipt.get('reason') in ('NUMERICAL_ERROR','INTERNAL_CONSISTENCY_ERROR'):raise ValueError('NUMERICAL_FAILURE')
    if any(F(lower['minimum_degC'][node][0])<valid_lo or F(upper['peaks_degC'][node][1])>valid_hi for node in nodes):raise ValueError('ACTUAL_TRAJECTORY_MODEL_RANGE_UNRESOLVED')
    # k>=0 makes integrated electrical energy monotone in temperature too.
    out={'peak_by_node_degC':{node:[lower['peaks_degC'][node][0],upper['peaks_degC'][node][1]] for node in nodes},
        'minimum_by_node_degC':{node:[lower['minimum_degC'][node][0],upper['minimum_degC'][node][1]] for node in nodes},
        'end_temperature_degC':[[lower['final_temperature_degC'][node][0],upper['final_temperature_degC'][node][1]] for node in nodes],
        'mean_by_node_degC':{node:[str(ambient+F(lower['temperature_rise_integrals_Ks'][node][0])/period),str(ambient+F(upper['temperature_rise_integrals_Ks'][node][1])/period)] for node in nodes},
        'energy_J':[lower['energy_J'][0],upper['energy_J'][1]],
        'energy_components_J':{key:[lower['energy_components_J'][key][0],upper['energy_components_J'][key][1]] for key in lower['energy_components_J']}}
    for intervals in (out['peak_by_node_degC'].values(),out['minimum_by_node_degC'].values(),out['mean_by_node_degC'].values(),out['end_temperature_degC'],[out['energy_J']],out['energy_components_J'].values()):
        if any(F(interval[0])>F(interval[1]) for interval in intervals):raise ValueError('ORDERED_PATH_INTERFACE_INCONSISTENCY')
    return out


def fixed_point_guess(platform,segments):
    """Floating guide only; never evidence or a SAFE classification."""
    import numpy as np
    from scipy.linalg import expm
    nodes=platform['node_order'];c=np.array([float(F(v)) for v in platform['heat_capacity_J_per_K']]);g=np.array([[float(F(v)) for v in row] for row in platform['conductance_W_per_K']]);ambient=float(F(platform['ambient_temperature_degC']));reference=float(F(platform['reference_temperature_degC']))
    mapping=np.eye(4);offset=np.zeros(4)
    for segment in segments:
        slopes=np.array([float(F(segment['local_leakage_slope_W_per_K'][n])) for n in nodes]);constant=np.array([float(F(segment['node_power_constant_at_reference_W'][n])) for n in nodes])
        aug=np.zeros((5,5));aug[:4,:4]=(np.diag(slopes)-g)/c[:,None];aug[:4,4]=(g.sum(axis=1)*ambient+constant-slopes*reference)/c
        step=expm(aug*float(F(segment['duration_ms'])/1000));mapping,offset=step[:4,:4]@mapping,step[:4,:4]@offset+step[:4,4]
    x=np.linalg.solve(np.eye(4)-mapping,offset)
    return [str(v) for v in x],{'spectral_radius_float_diagnostic':float(max(abs(np.linalg.eigvals(mapping)))),'fixed_point_float':list(map(float,x)),'role':'candidate/guide only, not proof'}


def review_configuration(config,instance,candidate,scene_id,period_ms,evaluate,*,max_rounds=128):
    """evaluate(entry) is the logged original evaluate_piecewise on one period."""
    platform=instance['platform'];nodes=platform['node_order'];scene=next(s for s in instance['scenarios'] if s['id']==scene_id);limits=list(map(F,scene['maximum_temperature_degC']))
    # Segment clipping and contraction are frozen by the caller after original
    # 400ms legality. No instance.window or deadline is rewritten here.
    segments=evaluate.segments;contract=contraction(platform,segments,period_ms);q=F(contract['q_rational_upper'])
    xhat,float_info=fixed_point_guess(platform,segments)
    nominal=evaluate(xhat,'fixed_point_residual')
    if not nominal.get('complete'):raise ValueError('FIXED_POINT_RESIDUAL_INCOMPLETE')
    residual,radius=residual_radius(xhat,[nominal['final_temperature_degC'][n] for n in nodes],q)
    steady_box=[[str(F(x)-radius),str(F(x)+radius)] for x in xhat]
    lower=evaluate([b[0] for b in steady_box],'steady_lower');upper=evaluate([b[1] for b in steady_box],'steady_upper')
    steady=combine_paths(lower,upper,platform,period_ms)
    steady_peak_lo=max(F(v[0]) for v in steady['peak_by_node_degC'].values());steady_peak_hi=max(F(v[1]) for v in steady['peak_by_node_degC'].values())
    initial=[[t,t] for t in scene['entry']['temperature_degC']];entry=initial;rounds=[];prefix_upper=None;classification='UNRESOLVED_MAX_ROUNDS';witness=None;tail_upper=None;first=None
    earlier_rounds_all_safe=True;earliest_unsafe_certified=False
    for n in range(1,max_rounds+1):
        lo_entry=[v[0] for v in entry];hi_entry=[v[1] for v in entry]
        lo=evaluate(lo_entry,f'round_{n:03d}_lower')
        hi=lo if lo_entry==hi_entry else evaluate(hi_entry,f'round_{n:03d}_upper')
        bound=combine_paths(lo,hi,platform,period_ms)
        if first is None:first=deepcopy(bound)
        peak_hi=max(F(v[1]) for v in bound['peak_by_node_degC'].values());prefix_upper=peak_hi if prefix_upper is None else max(prefix_upper,peak_hi)
        # Only a low-path point above limit certifies violation of the actual
        # trajectory; a high-path point alone does not prove overheating.
        points=[v for v in lo.get('violations',[]) if F(v['temperature_degC'][0])>F(v['limit_degC'])]
        distance=box_distance(bound['end_temperature_degC'],steady_box);tail_upper=steady_peak_hi+distance
        tail_lower=min(F(v[0]) for v in steady['minimum_by_node_degC'].values())-distance
        valid_lower,valid_upper=map(F,platform['power_model_temperature_range_degC'])
        tail_model_valid=tail_lower>=valid_lower and tail_upper<=valid_upper
        row={'round':n,'entry_box_degC':deepcopy(entry),'bound':bound,'distance_after_round_to_periodic_box_K':str(distance),'tail_all_future_upper_degC':str(tail_upper),'tail_all_future_lower_degC':str(tail_lower),'tail_model_range_certified':tail_model_valid};rounds.append(row)
        if points:
            v=deepcopy(points[0]);v.update(round=n,global_time_s=str((n-1)*F(period_ms)/1000+F(v['time_s'])),certificate='actual trajectory>=lower-start path; low point within original model validity range')
            witness=v;classification='THERMAL_VIOLATION';break
        if prefix_upper<=min(limits) and tail_upper<=min(limits) and tail_model_valid:classification='SAFE_ALL_ROUNDS';break
        earlier_rounds_all_safe=earlier_rounds_all_safe and peak_hi<=min(limits)
        entry=bound['end_temperature_degC']
    if classification=='SAFE_ALL_ROUNDS':all_rounds=max(prefix_upper,tail_upper)
    else:all_rounds=None
    return {'classification':classification,'contractivity':contract,'floating_guide':float_info,'fixed_point_residual_infinity_K':str(residual),'fixed_point_initial_error_radius_K':str(radius),'periodic_entry_box_degC':steady_box,
        'periodic_bounds':steady,'periodic_peak_degC':[str(steady_peak_lo),str(steady_peak_hi)],'periodic_peak_node_upper':max(nodes,key=lambda n:F(steady['peak_by_node_degC'][n][1])),
        'first_round':first,'startup_rounds':rounds,'checked_round_count':len(rounds),'all_rounds_conservative_upper_degC':str(all_rounds) if all_rounds is not None else None,'violation_witness':witness,
        'earlier_rounds_all_safe':earlier_rounds_all_safe,'first_unsafe_round':witness['round'] if witness and earlier_rounds_all_safe else None,
        'periodic_energy_is_diagnostic_only':classification!='SAFE_ALL_ROUNDS','notes':'Period energy/mean vs original400ms single-window quantities are distinct. Same original propagation kernel; no independent numerical certificate.'}
