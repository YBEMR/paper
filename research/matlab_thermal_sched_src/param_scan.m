function s = param_scan(cfg, outdir)
% PARAM_SCAN  First-round parameter sweeps:
%   (1) initial temperature T0        : 35, 45, 55, 65 C
%   (2) thermal time constant tau     : scale C by 0.5, 1, 2, 4 (g unchanged)
%   (3) stage duration d              : scale d and D together by 1, 2
% The core observation axis is d/tau vs the energy gain Delta E.
% Output: output/scan_report.txt, output/scan_dE.png
s = struct();
labels = {};
rows = {};

% ---- T0 sweep ----
for v = [35 45 55 65 70 72 74 77]
  c = cfg; c.T0 = v;
  labels{end+1} = sprintf('T0=%g', v); %#ok<AGROW>
  rows{end+1} = run_once_scan(c); %#ok<AGROW>
end
% ---- tau sweep (scale C) ----
for k = [0.02 0.05 0.1 0.25 0.5 1 2 4]
  c = cfg; c.C = cfg.C * k;
  labels{end+1} = sprintf('tau x%.2f', k); %#ok<AGROW>
  rows{end+1} = run_once_scan(c); %#ok<AGROW>
end
% ---- duration sweep (scale d and D together) ----
for k = [1 2 4]
  c = cfg; c.d_A1_ms = cfg.d_A1_ms*k; c.d_B1_ms = cfg.d_B1_ms*k;
  c.d_A2_ms = cfg.d_A2_ms*k; c.d_B2_ms = cfg.d_B2_ms*k;
  c.D_A_ms = cfg.D_A_ms*k; c.D_B_ms = cfg.D_B_ms*k;
  c.H_ms = max(c.D_A_ms, c.D_B_ms);
  labels{end+1} = sprintf('d x%d', k); %#ok<AGROW>
  rows{end+1} = run_once_scan(c); %#ok<AGROW>
end

% ---- report ----
fid = fopen(fullfile(outdir,'scan_report.txt'),'w','n','UTF-8');
fprintf(fid, '=== PARAMETER SCAN ===\n');
fprintf(fid, '%-14s %10s %10s %10s %10s %12s %12s %12s\n', ...
    'case','d/tau','n_base','n_tr_rej','n_tr_only','E_ss*(mJ)','E_tr*(mJ)','dE(mJ)');
for i = 1:numel(rows)
  r = rows{i};
  fprintf(fid, '%-14s %10.4f %10d %10d %10d %12.4f %12.4f %12.4f\n', ...
      labels{i}, r.d_over_tau, r.n_base, r.n_tr_rej, r.n_tr_only, r.Ess_mJ, r.Etr_mJ, r.dE_mJ);
end
fprintf(fid, '\nd/tau = d_A1(high) / tau_C, tau_C = C1/g1.\n');
fprintf(fid, 'n_tr_rej = schedules rejected by the transient check (base - tr).\n');
fclose(fid);

% ---- figure ----
dE = cellfun(@(r) r.dE_mJ, rows);
fig = figure('Visible','off','Position',[100 100 900 420]);
bar(1:numel(dE), dE);
set(gca,'XTick',1:numel(dE),'XTickLabel',labels,'XTickLabelRotation',45);
ylabel('Delta E = E_{ss}* - E_{tr}*  (mJ)');
title('Energy gain of transient modeling across parameter cases');
grid on;
exportgraphics(fig, fullfile(outdir,'scan_dE.png'), 'Resolution', 150);
close(fig);

s.labels = labels; s.dE_mJ = dE;
fprintf('[scan] cases: %s\n', strjoin(labels, ', '));
fprintf('[scan] dE: %s\n', num2str(dE, '%.4f '));
end

function r = run_once_scan(c)
% Single evaluation of one parameter configuration.
S = enumerate_schedules(c);
th = thermal_build(c);
res = eval_schedules(S, c, th);
r.n_base = size(S,1);
r.n_ss = sum(res.ss_ok);
r.n_tr = sum(res.tr_ok);
r.n_tr_rej = r.n_base - r.n_tr;
r.n_tr_only = sum(~res.ss_ok & res.tr_ok);
[Ess, ~] = minimize_energy(res, res.ss_ok);
[Etr, ~] = minimize_energy(res, res.tr_ok);
r.Ess_mJ = Ess; r.Etr_mJ = Etr; r.dE_mJ = Ess - Etr;
r.tau_C_ms = c.C(1)/c.g_env(1)*1e3;
r.d_over_tau = c.d_A1_ms(2)/r.tau_C_ms;
end
