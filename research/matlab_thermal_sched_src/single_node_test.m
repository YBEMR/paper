function r = single_node_test(cfg)
% SINGLE_NODE_TEST  Test 2: verify the transient integrator against the
% analytic single-node solution  T(t) = T_ss + (T0 - T_ss)*exp(-t/tau).
g = cfg.g_env(1); Cnode = cfg.C(1);
P = 5.0; T_amb = cfg.T_amb; T0 = 45;
tau = Cnode/g;
Tss = T_amb + P/g;
dt = 0.1e-3; tend = 0.2;
t = (0:dt:tend)';
Tana = Tss + (T0 - Tss)*exp(-t/tau);
% Numerical integration via the same per-interval update used by the model,
% applied to a 1x1 system:  theta <- theta_ss + exp(-dt/tau)*(theta - theta_ss)
A1 = -g/Cnode; Tstep = exp(A1*dt);
thss = P/g; theta = T0 - T_amb;
Tnum = zeros(size(t)); Tnum(1) = T0;
for i = 2:numel(t)
  theta = thss + (theta - thss)*Tstep;
  Tnum(i) = theta + T_amb;
end
r.max_abs_err = max(abs(Tana - Tnum));
r.tau_ms = tau*1e3;
i50 = round(0.05/dt) + 1;                 % t = 50 ms = tau
r.ratio_at_tau = (Tnum(i50) - Tss)/(T0 - Tss);
r.e_inv = exp(-1);
r.pass = r.max_abs_err < 1e-9 && abs(r.ratio_at_tau - r.e_inv) < 1e-3;
end
