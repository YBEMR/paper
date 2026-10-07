function e = cv_energy(c,s)
% Independent event-interval integration and duration-based sum.
assert(all(s.start>=-c.time_tol) && all(s.finish<=c.window+c.time_tol), ...
    'Cannot score an incomplete schedule outside the common window');
base=c.idle_cpu+c.idle_npu+c.external;
events=unique([0 c.window s.start s.finish]); total=0;
for j=1:numel(events)-1
    lo=max(0,events(j)); hi=min(c.window,events(j+1));
    if hi<=lo, continue; end
    mid=(lo+hi)/2;
    active=(s.start<=mid)&(mid<s.finish);
    total=total+(hi-lo)*(base+sum(s.increment(active)));
end
parts=s.increment.*s.duration;
formula=base*c.window+sum(parts);
tol=max(c.energy_abs_tol,c.energy_rel_tol*max(abs([formula total])));
assert(abs(total-formula)<=tol,'Energy integral differs from sum');
e=struct('integral',total,'formula',formula,'base',base*c.window, ...
    'cpu',sum(parts(1:2)),'npu',sum(parts(3:4)), ...
    'difference',abs(total-formula));
end
