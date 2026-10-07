function [time,T] = thv_trace(out,h,step)
% Plot/diagnostic samples only. The classifier uses thv_step stationary points.
time=[]; T=[];
net=thv_build(h);
for k=1:numel(out.segments)
    z=out.segments{k}; local=unique([0:step:z.duration z.duration z.roots(isfinite(z.roots))']);
    value=z.equilibrium+z.coeff*exp(-net.lambda*local);
    time=[time out.event_time(k)+local]; %#ok<AGROW>
    T=[T; value'+h.ambient]; %#ok<AGROW>
end
end
