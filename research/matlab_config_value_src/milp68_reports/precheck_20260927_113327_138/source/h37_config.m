function configs = h37_config(c,clock)
% No-heat configuration adapter. Deliberately discard all reference timings.
if nargin<2, clock=tic; end
r=cv_reference(c,'task',clock);
configs=struct('modes',{},'duration',{},'increment',{});
seen=zeros(0,2);
for j=r.optimal_indices
    s=r.rows(j).schedule;
    if ~ismember(s.modes,seen,'rows')
        configs(end+1)=struct('modes',s.modes,'duration',s.duration,'increment',s.increment);
        seen(end+1,:)=s.modes;
    end
end
end
