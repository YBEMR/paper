function code = cv_mode_codes(ref)
labels='LH'; values={};
for j=ref.optimal_indices
    values{end+1}=labels(ref.rows(j).schedule.modes);
end
if isempty(values), code='NONE'; else, code=strjoin(sort(unique(values)),'|'); end
end
