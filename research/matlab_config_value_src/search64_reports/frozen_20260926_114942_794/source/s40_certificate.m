function cert=s40_certificate(c,h,s)
% Sufficient all-schedule bounds, independent of resource order or deadlines.
% Max-node comparison: D+M <= -gamma*M+b+sum(active Q)/min(C).
peakpower=[c.idle_cpu+max(s.increment(1:2)),c.idle_npu+max(s.increment(3:4))];
box=max([h.initial h.ambient+peakpower./h.g_env]);
gamma=min(h.g_env./h.capacity);
b=max([c.idle_cpu c.idle_npu]./h.capacity);
energybound=h.ambient+max(max(h.initial)-h.ambient,b/gamma)+sum(s.increment.*s.duration)/min(h.capacity);
bound=min(box,energybound); kind='none';
if box<min(h.limit)-h.band, kind='invariant_box';
elseif energybound<min(h.limit)-h.band, kind='positive_system_energy_bound'; end
cert=struct('safe',~strcmp(kind,'none'),'kind',kind,'bound_C',bound, ...
    'box_bound_C',box,'energy_bound_C',energybound,'scope','all_continuous_legal_schedules');
end
