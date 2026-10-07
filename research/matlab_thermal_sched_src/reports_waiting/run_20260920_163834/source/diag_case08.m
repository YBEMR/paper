function diag_case08()
% DIAG_CASE08  Deep diagnosis of case 08 (r=(0,0), D=(24,28), T0=60):
% per-moment comparison table between greedy and the exhaustive optimum, plus
% causal localization (what decision at t*, and the no-thermal-limit control).
cfg = config_default();
b = cfg;
b.P_A1 = cfg.P_A1*1.6; b.P_B1 = cfg.P_B1*1.6;
b.P_A2 = cfg.P_A2*1.6; b.P_B2 = cfg.P_B2*1.6;
b.C = cfg.C*0.25; b.H_ms = 28;
b.rA_ms = 0; b.rB_ms = 0;
b.D_A_ms = 24; b.D_B_ms = 28;
b.T0 = 60;

S = enumerate_schedules(b);
th = thermal_build(b);
res = eval_schedules(S, b, th);
ok = res.tr_ok;
Etr = min(res.E(ok))*1e3;
Opt = S(ok & res.E*1e3 <= Etr + 1e-9, :);
fprintf('=== case 08 (r=(0,0), D=(24,28), T0=60) ===\n');
fprintf('n=%d, Etr=%.2f mJ, n_optimum=%d\n', size(S,1), Etr, size(Opt,1));

[pi_g, Eg, okg, nw] = greedy_scheduler(b, th, 'parallel', [1 2 3 4], 'energyfirst');
fprintf('greedy: pi=%s E=%.2f ok=%d waits=%d\n', mat2str(pi_g), Eg, okg, nw);
rg = eval_schedules(pi_g, b, th);
fprintf('greedy full-window recheck: tr_ok=%d, Tmax=%.2f\n', rg.tr_ok, rg.Tmax);

ts = find_tstar_local(pi_g, Opt, b);
fprintf('t* (corrected) = %d ms\n\n', ts);

[~, ii] = min(res.E(ok));
idx_ok = find(ok);
pi_o = S(idx_ok(ii),:);
fprintf('exhaustive optimum: pi=%s Tmax=%.2f\n\n', mat2str(pi_o), res.Tmax(idx_ok(ii)));

% precompute per-ms temperature for both schedules
Tg = traj_per_ms(pi_g, b, th);
To = traj_per_ms(pi_o, b, th);

fprintf('%-3s | %-14s | %-10s | %-6s | %-18s | %-16s | %-16s\n', ...
  't','done(greedy)','ready','free','T(C1/C2/N) greedy','greedy starts','optimum starts');
for t = 0:b.H_ms
  [dg, rg2, fg] = state_at(t, pi_g, b);
  [~, ~, fo] = state_at(t, pi_o, b);
  sg = starts_str(t, pi_g);
  so = starts_str(t, pi_o);
  if t <= b.H_ms
    tg = Tg(t+1,:); to = To(t+1,:);
    fprintf('%-3d | %-14s | %-10s | %-6s | %4.1f/%4.1f/%4.1f     | %-16s | %-16s\n', ...
      t, strjoin(dg,''), strjoin(rg2,''), strjoin(fg,''), ...
      tg(1), tg(2), tg(3), sg, so);
  end
end

% ---- causal localization: what did greedy do at t* and what is the alternative ----
fprintf('\n=== Causal localization at t*=%d ===\n', ts);
fprintf('greedy starts at t* : %s\n', starts_str(ts, pi_g));
fprintf('optimum starts at t*: %s\n', starts_str(ts, pi_o));
% list what the optimum starts vs greedy in the window around t*
fprintf('greedy  s = A1@%d(f%d) B1@%d(f%d) A2@%d B2@%d\n', ...
  pi_g(5), pi_g(3), pi_g(6), pi_g(4), pi_g(7), pi_g(8));
fprintf('optimum s = A1@%d(f%d) B1@%d(f%d) A2@%d B2@%d\n', ...
  pi_o(5), pi_o(3), pi_o(6), pi_o(4), pi_o(7), pi_o(8));

% ---- no-thermal-limit control ----
b2 = b; b2.T_lim = 200;
[pi_g2, Eg2, okg2, ~] = greedy_scheduler(b2, th, 'parallel', [1 2 3 4], 'energyfirst');
fprintf('\n=== No-thermal-limit control (Tlim=200) ===\n');
fprintf('greedy: pi=%s E=%.2f ok=%d\n', mat2str(pi_g2), Eg2, okg2);
fprintf('exhaustive optimum under same (no-limit) is the energy-minimal schedule.\n');
end

function s = starts_str(t, pi)
s = '';
if pi(5)==t, s=[s sprintf('A1(f%d)',pi(3))]; end
if pi(6)==t, s=[s sprintf('B1(f%d)',pi(4))]; end
if pi(7)==t, s=[s 'A2']; end
if pi(8)==t, s=[s 'B2']; end
if isempty(s), s='(wait)'; end
end

function [done, ready, free] = state_at(t, pi, cfg)
state = schedule_state_before(pi,cfg,t);
done=state.done; ready=state.ready; free=state.free;
end

function T = traj_per_ms(pi, cfg, th)
% per-ms temperature (last sub-sample of each ms)
H = cfg.H_ms; sub = 4;
dts = cfg.delta_ms*cfg.s_per_ms/sub;
Tstep = expm(th.A*dts); Ginv = th.Ginv;
[Pc1, Pc2, Pn] = schedule_power(pi, cfg);
theta = repmat(cfg.T0 - th.T_amb, 3, 1);
T = zeros(H+1, 3);
for k = 1:H
  q = [Pc1(k); Pc2(k); Pn(k)];
  thss = Ginv*q;
  for s = 1:sub
    theta = thss + Tstep*(theta - thss);
  end
  T(k+1,:) = (theta + th.T_amb)';
end
T(1,:) = cfg.T0;
end

function tstar = find_tstar_local(pi_g, Opt, cfg)
tstar=first_optimal_divergence(pi_g,Opt,cfg,true);
end
