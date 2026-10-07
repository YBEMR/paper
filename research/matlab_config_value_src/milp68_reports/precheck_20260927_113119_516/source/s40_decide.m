function d=s40_decide(modes,best,c)
% Pure evidence reducer; U is not infeasibility.
if isinf(best)
    d=struct('class','N','reason','no_heat_infeasible','lower_J',inf,'upper_J',inf,'energy_exact',true); return;
end
opt=[modes.optimal]; safe=[modes.has_safe]; bad=[modes.has_violation];
excluded=[modes.excluded]; allsafe=[modes.all_safe];
kind='U'; reason='optimal_schedule_evidence_incomplete';
if all(allsafe(opt)), kind='A'; reason='all_optimal_schedules_safe';
elseif any(safe(opt)) && any(bad(opt)), kind='B'; reason='safe_and_unsafe_optimal_witnesses';
elseif all(excluded(opt)) && any(safe), kind='C'; reason='all_original_optimal_modes_excluded';
elseif all(excluded), kind='D'; reason='all_modes_excluded'; end
upper=inf; if any(safe), upper=min([modes(safe).energy]); end
potential=~excluded;
lower=inf; if any(potential), lower=min([modes(potential).energy]); end
exact=isinf(lower)&&isinf(upper);
if isfinite(upper), exact=abs(upper-lower)<=max(c.energy_abs_tol,c.energy_rel_tol*abs(upper)); end
d=struct('class',kind,'reason',reason,'lower_J',lower,'upper_J',upper,'energy_exact',exact);
end
