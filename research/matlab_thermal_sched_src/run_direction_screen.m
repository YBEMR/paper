function run_direction_screen(test_set)
% RUN_DIRECTION_SCREEN  Direction screen (Route B): does a simple energy-first
% single-step predictor ever lose to the exhaustive optimum, and when?
%
% Fixed active-region parameters (lam=1.6, tau*0.25). Only vary release times,
% absolute deadlines, T0. Observation window H=28 for ALL cases.
%
% Metrics per case:
%   DeltaE = E_greedy - E_tr*   (>0 means greedy wastes energy; =0 matches)
%   class: A = greedy matches optimum; B = greedy feasible & costlier;
%          C = greedy infeasible (incomplete OR fails full-window thermal recheck)
%   t* : first decision moment after which the greedy history can no longer be
%        extended to ANY exhaustive optimum. Whole-CPU-core-swap tolerated;
%        waiting diverges only when NO optimal completion preserves it.
%
% Greedy completion is ALWAYS re-checked with the same full-window transient
% model (eval_schedules). Incomplete greedy schedules are class C and do NOT
% enter the energy comparison (their partial-window energy is not reported).
if nargin < 1, test_set = 'quick'; end
cfg = config_default();
b = cfg;
b.P_A1 = cfg.P_A1*1.6; b.P_B1 = cfg.P_B1*1.6;
b.P_A2 = cfg.P_A2*1.6; b.P_B2 = cfg.P_B2*1.6;
b.C = cfg.C*0.25;
b.H_ms = 28;

outdir = fullfile(pwd, 'output');
if ~exist(outdir, 'dir'), mkdir(outdir); end

if strcmp(test_set,'quick')
  cases = { [0 0],[20 24],45; [0 5],[20 24],45; [5 0],[18 22],60; [0 10],[24 28],70 };
  outfile = 'direction_screen_quick.txt';
else
  rA = [0 0 5 0]; rB = [0 5 0 10];
  Ds = {[18 22],[20 24],[24 28]};
  T0s = [45 60 70];
  cases = {};
  for i = 1:4, for di = 1:3, for ti = 1:3
    cases(end+1,:) = { [rA(i) rB(i)], Ds{di}, T0s(ti) }; %#ok<AGROW>
  end, end, end
  outfile = 'direction_screen_full.txt';
end

fid = fopen(fullfile(outdir, outfile),'w','n','UTF-8');
fprintf(fid, '=== DIRECTION SCREEN (H=28, active lam1.6/tau0.25) ===\n');
fprintf(fid, 'Both methods know arrival times/deadlines. DeltaE = E_greedy - E_tr*.\n');
fprintf(fid, 'Greedy re-checked with the SAME full-window transient model.\n\n');
hdr = '%-3s  %-6s  %-7s  %-3s | %6s | %8s %8s %7s %6s | %8s %7s %6s | %s\n';
fprintf(fid, hdr, 'case','(rA,rB)','(DA,DB)','T0','n_sched','Etr', ...
    'E_gpar','dE_par','t*_par','E_gauto','dE_auto','t*_auto','class(par/auto)');

nA = 0; nB = 0; nC = 0;
for k = 1:size(cases,1)
  c = b;
  c.rA_ms = cases{k,1}(1); c.rB_ms = cases{k,1}(2);
  c.D_A_ms = cases{k,2}(1); c.D_B_ms = cases{k,2}(2);
  c.T0 = cases{k,3};
  S = enumerate_schedules(c);
  th = thermal_build(c);
  res = eval_schedules(S, c, th);
  ok = res.tr_ok;
  n_sched = size(S,1);
  if any(ok)
    Etr = min(res.E(ok))*1e3;
    Opt = S(ok & res.E*1e3 <= Etr + 1e-9, :);
  else
    Etr = Inf; Opt = zeros(0,8,'int32');
  end
  [cls_p, dEp, tp, Egp] = judge(c, th, Opt, Etr, [1 2 3 4], 'parallel');
  [cls_a, dEa, ta, Ega] = judge(c, th, Opt, Etr, [1 2 3 4], 'auto');
  if strcmp(cls_p,'A'), nA = nA+1; end
  if strcmp(cls_p,'B'), nB = nB+1; end
  if strcmp(cls_p,'C'), nC = nC+1; end
  fprintf(fid, hdr, sprintf('%02d',k), mat2str(cases{k,1}), mat2str(cases{k,2}), ...
      sprintf('%g',c.T0), sprintf('%6d',n_sched), sprintf('%8.2f',Etr), ...
      sprintf('%8.2f',Egp), sprintf('%7.3f',dEp), sprintf('%6.0f',tp), ...
      sprintf('%8.2f',Ega), sprintf('%7.3f',dEa), sprintf('%6.0f',ta), ...
      sprintf('%s / %s', cls_p, cls_a));
  fprintf('[dir] case %02d (r=%s D=%s T0=%g): n=%d Etr=%.1f par: %s dE=%+.2f t*=%.0f | auto: %s dE=%+.2f t*=%.0f\n', ...
    k, mat2str(cases{k,1}), mat2str(cases{k,2}), c.T0, n_sched, Etr, cls_p, dEp, tp, cls_a, dEa, ta);
end

fprintf(fid, '\n=== Summary (parallel variant) ===\n');
fprintf(fid, '  A (matches optimum): %d\n', nA);
fprintf(fid, '  B (feasible, costlier): %d\n', nB);
fprintf(fid, '  C (greedy infeasible / fails recheck): %d\n', nC);
fclose(fid);
fprintf('[dir] done -> %s\n', outfile);
end

function [cls, dE, tstar, E_g_mJ] = judge(c, th, Opt, Etr, priority, map_mode)
if isinf(Etr), cls = '-'; dE = NaN; tstar = NaN; E_g_mJ = NaN; return; end  % exhaustive itself infeasible
[pi_g, E_g, g_ok, ~] = greedy_scheduler(c, th, map_mode, priority, 'energyfirst');
if ~g_ok
  cls = 'C'; dE = NaN; tstar = NaN; E_g_mJ = NaN; return;   % incomplete: not comparable
end
% full-window transient re-check with the SAME model
rg = eval_schedules(pi_g, c, th);
if ~rg.tr_ok
  cls = 'C'; dE = NaN; tstar = NaN; E_g_mJ = rg.E*1e3; return; % greedy unsafe over full window
end
E_g_mJ = rg.E*1e3;
dE = E_g_mJ - Etr;
if dE <= 1e-6, cls = 'A'; else, cls = 'B'; end
tstar = find_tstar(pi_g, Opt, c);
end

function tstar = find_tstar(pi_g, Opt, cfg)
tstar=first_optimal_divergence(pi_g,Opt,cfg,true);
end
