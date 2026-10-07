function R = scan_active_region(cfg, outdir)
% SCAN_ACTIVE_REGION  Phase 1: locate the regime where the transient thermal
% constraint actually binds and schedule decisions could matter.
%
% Sweep: running-power scale x {1.0,1.3,1.6,2.0} x T0 x {45,60,70} x
%        tau scale (C scale) x {1.0,0.5,0.25,0.1}
%
% For every configuration we report:
%   - feasibility-set sizes (ss / tr / tr-rejected / transient-only)
%   - E_ss*, E_tr*, Delta E (absolute mJ and relative %)
%   - frequency combination of the transient-optimal schedule
%   - peak temperature range of transient-feasible schedules
%   - feasibility of each (fA,fB) combination under the transient constraint
%
% Output: output/active_region_report.txt + output/active_region_dE.png
lambda = [1.0 1.3 1.6 2.0];
T0s    = [45 60 70];
taus   = [1.0 0.5 0.25 0.1];
labels = {}; rows = {};
idx = 0;
for li = 1:numel(lambda)
  for ti = 1:numel(T0s)
    for ui = 1:numel(taus)
      c = cfg;
      c.P_A1 = cfg.P_A1*lambda(li);
      c.P_B1 = cfg.P_B1*lambda(li);
      c.P_A2 = cfg.P_A2*lambda(li);
      c.P_B2 = cfg.P_B2*lambda(li);
      c.T0 = T0s(ti);
      c.C = cfg.C*taus(ui);
      idx = idx + 1;
      labels{idx} = sprintf('lam%.1f_T0%d_tau%.2f', lambda(li), T0s(ti), taus(ui));
      rows{idx} = analyze_one(c);
    end
  end
end

% ---- report ----
fid = fopen(fullfile(outdir,'active_region_report.txt'),'w','n','UTF-8');
fprintf(fid, '=== PHASE 1: locating the regime where transient constraints bind ===\n');
fprintf(fid, 'sweep: power x {1,1.3,1.6,2}  T0 x {45,60,70}  tau-scale x {1,0.5,0.25,0.1}\n');
fprintf(fid, 'd/tau_net = d_A1(high) / tau_net, tau_net = slowest eigenmode of the coupled network\n\n');
hdr = '%-22s %8s %8s %8s %8s %8s %10s %10s %10s %8s %8s %8s %10s\n';
fprintf(fid, hdr, 'case','d/tau_net','n_ss','n_tr','n_tr_rej','n_tr_only','E_ss*(mJ)','E_tr*(mJ)','dE(mJ)','dE%','fA*','fB*','Tmax_feas');
for i = 1:numel(rows)
  r = rows{i};
  fprintf(fid, '%-22s %8.3f %8d %8d %8d %8d %10.3f %10.3f %10.3f %8.2f %8s %8s %10.2f\n', ...
      labels{i}, r.d_over_tau_net, r.n_ss, r.n_tr, r.n_tr_rej, r.n_tr_only, ...
      r.Ess_mJ, r.Etr_mJ, r.dE_mJ, r.dE_rel, fstr(r.fA_tr), fstr(r.fB_tr), r.Tmax_feas);
end
fprintf(fid, '\nTransient-feasibility of each frequency combination (per config):\n');
fprintf(fid, '%-22s %10s %10s %10s %10s\n', 'case','LL','LH','HL','HH');
for i = 1:numel(rows)
  r = rows{i};
  fprintf(fid, '%-22s %10d %10d %10d %10d\n', labels{i}, ...
      r.freq_ok(1,1), r.freq_ok(1,2), r.freq_ok(2,1), r.freq_ok(2,2));
end
fprintf(fid, '\nNotes:\n');
fprintf(fid, '  - n_tr_rej = base - tr : schedules rejected by the transient check.\n');
fprintf(fid, '  - n_tr_only = transient-feasible but steady-infeasible.\n');
fprintf(fid, '  - Tmax_feas = max sampled peak over transient-feasible schedules (C).\n');
fprintf(fid, '  - An "active" regime has n_tr_rej > 0: the transient constraint is binding,\n');
fprintf(fid, '    so start times / mapping / order have room to affect feasibility.\n');
fclose(fid);

% ---- figure: relative energy gain ----
dErel = cellfun(@(r) r.dE_rel, rows);
fig = figure('Visible','off','Position',[100 100 1100 420]);
bar(1:numel(dErel), dErel);
set(gca,'XTick',1:numel(dErel),'XTickLabel',labels,'XTickLabelRotation',90,'FontSize',7);
ylabel('dE/E_{ss}*  (%)');
title('Relative energy gain of transient modeling (Phase 1 sweep)');
grid on;
exportgraphics(fig, fullfile(outdir,'active_region_dE.png'), 'Resolution', 150);
close(fig);

R.labels = labels; R.rows = rows;
% console: highlight active configs
fprintf('[phase1] %d configs scanned\n', numel(rows));
for i = 1:numel(rows)
  r = rows{i};
  if r.n_tr_rej > 0 && isfinite(r.Etr_mJ)
    fprintf('[phase1 ACTIVE] %-22s dE=%.3f mJ (%.2f%%), tr_rej=%d, fA*=%s fB*=%s\n', ...
        labels{i}, r.dE_mJ, r.dE_rel, r.n_tr_rej, fstr(r.fA_tr), fstr(r.fB_tr));
  end
end
end

function r = analyze_one(c)
% Single configuration evaluation.
S = enumerate_schedules(c);
th = thermal_build(c);
res = eval_schedules(S, c, th);
r.n_base = size(S,1);
r.n_ss = sum(res.ss_ok);
r.n_tr = sum(res.tr_ok);
r.n_tr_rej = r.n_base - r.n_tr;
r.n_tr_only = sum(~res.ss_ok & res.tr_ok);
[Ess, ~] = minimize_energy(res, res.ss_ok);
[Etr, i_tr] = minimize_energy(res, res.tr_ok);
r.Ess_mJ = Ess; r.Etr_mJ = Etr;
r.dE_mJ = Ess - Etr;
if isfinite(Ess) && Ess > 0
  r.dE_rel = (Ess - Etr)/Ess*100;
else
  r.dE_rel = NaN;
end
if ~isempty(i_tr)
  r.pi_tr = S(i_tr,:);
  r.fA_tr = S(i_tr,3); r.fB_tr = S(i_tr,4);
else
  r.pi_tr = []; r.fA_tr = NaN; r.fB_tr = NaN;
end
r.Tmax_all = max(res.Tmax);
if any(res.tr_ok)
  r.Tmax_feas = max(res.Tmax(res.tr_ok));
  r.Tmax_feas_min = min(res.Tmax(res.tr_ok));
else
  r.Tmax_feas = NaN; r.Tmax_feas_min = NaN;
end
% frequency-combination breakdown under the transient constraint
r.freq_ok = zeros(2,2);
r.freq_minE = inf(2,2);
r.freq_total = zeros(2,2);
for fA = 1:2
  for fB = 1:2
    seltot = (S(:,3)==fA) & (S(:,4)==fB);
    r.freq_total(fA,fB) = sum(seltot);
    sel = seltot & res.tr_ok;
    r.freq_ok(fA,fB) = sum(sel);
    if any(sel)
      r.freq_minE(fA,fB) = min(res.E(sel))*1e3;
    end
  end
end
% network time scale: slowest eigenmode of the coupled system
ev = eig(th.A);
tau_net = max(-1./real(ev));          % seconds
r.tau_net_ms = tau_net*1e3;
r.d_over_tau_net = c.d_A1_ms(2)/r.tau_net_ms;
end

function s = fstr(f)
if isnan(f), s = 'NA'; else, s = 'LH'; s = s(f); end
end
