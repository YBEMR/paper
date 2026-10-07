function m = run_main(cfg, outdir)
% RUN_MAIN  Main experiment: exhaustive enumeration + steady vs transient
% thermal constraint comparison.
%
% Answers the two first-round questions:
%   Q1: which schedules does the steady-state constraint exclude although the
%       full transient trajectory respects the limit?
%   Q2: do those extra transient-feasible schedules actually lower optimal
%       energy (Delta E > 0)?
%
% Outputs: output/main_report.txt, gantt and temperature figures.
m = struct();
S = enumerate_schedules(cfg);
th = thermal_build(cfg);
res = eval_schedules(S, cfg, th);

Fss = res.ss_ok; Ftr = res.tr_ok;
m.n_base = size(S,1);
m.n_ss = sum(Fss);
m.n_tr = sum(Ftr);
m.n_both = sum(Fss & Ftr);
m.n_ss_only = sum(Fss & ~Ftr);   % steady feasible, transient violates
m.n_tr_only = sum(~Fss & Ftr);   % transient feasible, steady excludes (too conservative)

[Ess, i_ss] = minimize_energy(res, Fss);
[Etr, i_tr] = minimize_energy(res, Ftr);
m.Ess_mJ = Ess; m.Etr_mJ = Etr;
m.dE_mJ = Ess - Etr;               % > 0  => transient modeling finds lower energy
m.tr_peak_ss = res.Tmax(i_ss);     % real transient peak of the steady-optimal schedule
m.tr_peak_tr = res.Tmax(i_tr);     % real transient peak of the transient-optimal schedule
if ~isempty(i_ss), m.pi_ss = S(i_ss,:); else, m.pi_ss = []; end
if ~isempty(i_tr), m.pi_tr = S(i_tr,:); else, m.pi_tr = []; end

% ---- report file ----
fid = fopen(fullfile(outdir,'main_report.txt'),'w','n','UTF-8');
fprintf(fid, '=== MAIN EXPERIMENT: steady vs transient thermal constraints ===\n');
fprintf(fid, 'cfg: T_amb=%g, T_lim=%g, T0=%g, D_A=%d ms, D_B=%d ms, H=%d ms, delta=%g ms\n\n', ...
    cfg.T_amb, cfg.T_lim, cfg.T0, cfg.D_A_ms, cfg.D_B_ms, cfg.H_ms, cfg.delta_ms);
fprintf(fid, 'Base feasible schedules          : %d\n', m.n_base);
fprintf(fid, 'Steady-feasible                  : %d  (%5.2f%%)\n', m.n_ss, 100*m.n_ss/m.n_base);
fprintf(fid, 'Transient-feasible               : %d  (%5.2f%%)\n', m.n_tr, 100*m.n_tr/m.n_base);
fprintf(fid, 'Both feasible                    : %d\n', m.n_both);
fprintf(fid, 'Steady-only (steady accepts, transient rejects) : %d\n', m.n_ss_only);
fprintf(fid, 'Transient-only (steady excludes, transient ok)  : %d\n', m.n_tr_only);
fprintf(fid, '\n');
% ---- what does steady-state actually exclude? frequency-combination breakdown ----
fl = {'L','H'};
fprintf(fid, 'Frequency-combination breakdown of the base feasible set:\n');
fprintf(fid, '%-10s %10s %10s %14s %14s\n', 'fA fB', 'n_total', 'n_steady', 'n_tr_only', 'minE_tr_only');
for fA = 1:2
  for fB = 1:2
    sel = (S(:,3)==fA) & (S(:,4)==fB);
    n_sel = sum(sel);
    n_ss_sel = sum(sel & Fss);
    n_tr_only_sel = sum(sel & ~Fss & Ftr);
    if n_tr_only_sel > 0
      mE = min(res.E(sel & ~Fss & Ftr))*1e3;
    else
      mE = NaN;
    end
    fprintf(fid, '%-10s %10d %10d %14d %14.4f\n', [fl{fA} ' ' fl{fB}], n_sel, n_ss_sel, n_tr_only_sel, mE);
  end
end
fprintf(fid, '\n');
fprintf(fid, 'min energy among transient-only (steady-excluded) schedules: ');
idx_to = find(~Fss & Ftr);
if ~isempty(idx_to)
  fprintf(fid, '%.4f mJ\n', min(res.E(idx_to))*1e3);
else
  fprintf(fid, 'none\n');
end
fprintf(fid, '\n');
fprintf(fid, 'E_ss* = %.6f mJ\n', m.Ess_mJ);
fprintf(fid, 'E_tr* = %.6f mJ\n', m.Etr_mJ);
fprintf(fid, 'Delta E = E_ss* - E_tr* = %.6f mJ  %s\n', m.dE_mJ, ...
    ternary(m.dE_mJ > 1e-9, '=> transient modeling finds LOWER energy', ...
            '=> no energy gain from transient modeling in this parameter set'));
fprintf(fid, '\n');
if ~isempty(m.pi_ss)
  fprintf(fid, 'Steady-optimal schedule    : %s\n', pi_str(m.pi_ss, cfg));
  fprintf(fid, '  real transient peak      : %.2f C  %s\n', m.tr_peak_ss, ...
      ternary(m.tr_peak_ss <= cfg.T_lim, '(OK)', '(THERMAL VIOLATION - reported as infeasible under transient check)'));
end
if ~isempty(m.pi_tr)
  fprintf(fid, 'Transient-optimal schedule : %s\n', pi_str(m.pi_tr, cfg));
  fprintf(fid, '  real transient peak      : %.2f C  (OK)\n', m.tr_peak_tr);
end
fclose(fid);

% ---- figures ----
if ~isempty(m.pi_ss)
  plot_gantt(m.pi_ss, cfg, fullfile(outdir,'gantt_steady_opt.png'));
end
if ~isempty(m.pi_tr)
  plot_gantt(m.pi_tr, cfg, fullfile(outdir,'gantt_transient_opt.png'));
end
if ~isempty(m.pi_ss) && ~isempty(m.pi_tr)
  plot_temperature(m.pi_ss, m.pi_tr, cfg, th, fullfile(outdir,'temp_compare.png'), ...
      'steady-optimal', 'transient-optimal');
end

% ---- console summary ----
fprintf('[main] base=%d ss=%d tr=%d tr_only=%d  E_ss*=%.4f E_tr*=%.4f dE=%.4f mJ\n', ...
    m.n_base, m.n_ss, m.n_tr, m.n_tr_only, m.Ess_mJ, m.Etr_mJ, m.dE_mJ);
end

function s = ternary(cond, a, b)
if cond, s = a; else, s = b; end
end

function s = pi_str(pi, cfg)
fl = {'L','H'};
s = sprintf('[mA=%d mB=%d fA=%s fB=%s sA1=%d sB1=%d sA2=%d sB2=%d]', ...
    pi(1), pi(2), fl{pi(3)}, fl{pi(4)}, pi(5), pi(6), pi(7), pi(8));
end
