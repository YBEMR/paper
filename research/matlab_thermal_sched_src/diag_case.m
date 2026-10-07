function diag_case()
cfg = config_default();
b = cfg;
b.P_A1 = cfg.P_A1*1.6; b.P_B1 = cfg.P_B1*1.6;
b.P_A2 = cfg.P_A2*1.6; b.P_B2 = cfg.P_B2*1.6;
b.C = cfg.C*0.25; b.H_ms = 28;

% ---- case 04: rB=10, DB=28, T0=70 ----
b.rA_ms = 0; b.rB_ms = 10;
b.D_A_ms = 24; b.D_B_ms = 28;
b.T0 = 70;

S = enumerate_schedules(b);
th = thermal_build(b);
res = eval_schedules(S, b, th);
ok = res.tr_ok;
fprintf('=== case 04 (rA=0 rB=10 DA=24 DB=28 T0=70) ===\n');
fprintf('n_sched=%d, n_tr_ok=%d\n', size(S,1), sum(ok));
if any(ok)
  Etr = min(res.E(ok))*1e3;
  fprintf('Etr=%.2f mJ\n', Etr);
  [~, ii] = min(res.E(ok));
  idx_ok = find(ok);
  fprintf('exhaustive optimum pi=%s (Tmax=%.2f)\n', mat2str(S(idx_ok(ii),:)), res.Tmax(idx_ok(ii)));
end

[pi_gp, Egp, okgp, nwp] = greedy_scheduler(b, th, 'parallel', [1 2 3 4], 'energyfirst');
fprintf('greedy parallel: pi=%s E=%.1f ok=%d waits=%d\n', mat2str(pi_gp), Egp, okgp, nwp);
[pi_ga, Ega, okga, nwa] = greedy_scheduler(b, th, 'auto', [1 2 3 4], 'energyfirst');
fprintf('greedy auto:     pi=%s E=%.1f ok=%d waits=%d\n', mat2str(pi_ga), Ega, okga, nwa);

% what does the greedy schedule look like? identify which stages started
fl = {'L','H'};
fprintf('  greedy stages: A1(mA=%d,f=%s,s=%d) B1(mB=%d,f=%s,s=%d) A2(s=%d) B2(s=%d)\n', ...
  pi_gp(1), fl{pi_gp(3)}, pi_gp(5), pi_gp(2), fl{pi_gp(4)}, pi_gp(6), pi_gp(7), pi_gp(8));

% ---- case 03: rA=5, DA=18, T0=60 ----
c = cfg;
c.P_A1 = cfg.P_A1*1.6; c.P_B1 = cfg.P_B1*1.6;
c.P_A2 = cfg.P_A2*1.6; c.P_B2 = cfg.P_B2*1.6;
c.C = cfg.C*0.25; c.H_ms = 28;
c.rA_ms = 5; c.rB_ms = 0;
c.D_A_ms = 18; c.D_B_ms = 22;
c.T0 = 60;
S3 = enumerate_schedules(c);
th3 = thermal_build(c);
res3 = eval_schedules(S3, c, th3);
fprintf('\n=== case 03 (rA=5 rB=0 DA=18 DB=22 T0=60) ===\n');
fprintf('n_sched=%d, n_tr_ok=%d, min sampled peak over all = %.2f\n', ...
  size(S3,1), sum(res3.tr_ok), min(res3.Tmax));
end
