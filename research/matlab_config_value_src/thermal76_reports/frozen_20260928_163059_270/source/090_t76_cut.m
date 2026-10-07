function cut=t76_cut(c,h,columns,selected,thermal)
assert(numel(selected)==c.n && numel(unique(selected))==c.n);
assert(isequal(sort(columns(selected,1))',(1:c.n)),'t76:selection','A complete one-option-per-Stage selection is required');
cut=struct('kind','none','row',[],'source_lhs_interval',[NaN NaN], ...
 'source_point_temperature_interval',[NaN NaN],'reason','thermal_unresolved_or_safe');
if ~strcmp(thermal.status,'violation'),return;end
cut.kind='no_good';cut.reason='no_certified_point_row';
[~,node]=max(thermal.peak_lower-h.limit-h.band);t=thermal.peak_time(node);
row=t76_coefficients(c,h,columns,t,node);
lhs=t76_point(row,selected);
point=t76_iv('add',row.baseline_interval,t76_iv('sum',row.pulse_interval(selected,:)));
cut.source_lhs_interval=lhs;cut.source_point_temperature_interval=point;
if lhs(1)>row.rhs_upper
 cut.kind='temperature_row';cut.row=row;cut.reason='fixed_time_independently_certified';
end
end
