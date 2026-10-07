function [t_ms, T] = compute_trajectory(pi, cfg, th, sub)
% COMPUTE_TRAJECTORY  Fine temperature trajectory of one schedule.
%   [t_ms,T] = COMPUTE_TRAJECTORY(pi,cfg,th,sub)
%   pi: 1x8 schedule. Returns time axis (ms) and T (n x 3) sampled at
%   delta_ms/sub resolution.
if nargin < 4, sub = 4; end
S = int32(pi(:)');
[Pc1, Pc2, Pn] = schedule_power(S, cfg);
H = cfg.H_ms;
dts = cfg.delta_ms*cfg.s_per_ms/sub;
Tstep = expm(th.A*dts);
Ginv = th.Ginv;
theta = repmat(cfg.T0 - th.T_amb, 1, 3);
n = sub*H + 1;
t_ms = ((0:n-1)') * (cfg.delta_ms/sub);
T = zeros(n, 3);
T(1,:) = theta + th.T_amb;
for k = 1:H
  q = [Pc1(1,k), Pc2(1,k), Pn(1,k)];
  thss = q * Ginv';
  for s = 1:sub
    theta = thss + (theta - thss) * Tstep';
    T(sub*(k-1)+s+1, :) = theta + th.T_amb;
  end
end
end
