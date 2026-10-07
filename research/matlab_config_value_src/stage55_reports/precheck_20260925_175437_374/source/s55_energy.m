function e=s55_energy(c,s)
v=s55_validate(c,s); assert(v.feasible,v.reason);
ev=unique([0 c.window s.start s.finish]); base=c.idle_cpu+c.idle_npu+c.external;
integral=0;
for k=1:numel(ev)-1
    mid=(ev(k)+ev(k+1))/2; active=s.start<=mid & mid<s.finish;
    integral=integral+(base+sum(s.increment(active)))*(ev(k+1)-ev(k));
end
parts=s.duration.*s.increment; cpu=c.unit_kind(s.unit)==1;
e=struct('integral_J',integral,'sum_J',base*c.window+sum(parts), ...
    'cpu_active_J',sum(parts(cpu)),'npu_active_J',sum(parts(~cpu)),'base_J',base*c.window);
e.error_J=abs(e.integral_J-e.sum_J);
end
