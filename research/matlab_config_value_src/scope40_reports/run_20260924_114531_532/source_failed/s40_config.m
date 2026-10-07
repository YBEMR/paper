function configs=s40_config(c,h,clock)
% Reference timings intentionally not part of the public policy interface.
r=s40_reference(c,h,clock); configs=struct([]); seen=zeros(0,2);
for i=r.optimal_indices
    s=r.rows(i).schedule;
    if ~ismember(s.modes,seen,'rows')
        configs(end+1)=struct('modes',s.modes,'duration',s.duration,'increment',s.increment); %#ok<AGROW>
        seen(end+1,:)=s.modes; %#ok<AGROW>
    end
end
end
