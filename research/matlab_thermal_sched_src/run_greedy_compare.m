function r = run_greedy_compare(cfg, outdir, tag)
% RUN_GREEDY_COMPARE  Phase 3: SIMPLE single-step transient-prediction greedy
% schedulers vs the exhaustive transient optimum.
%
% Two selection rules are compared on the SAME active instance:
%   'minpeak'     - original: among feasible options pick the lowest predicted
%                   peak (can pick a low frequency even when the high frequency
%                   is feasible and cheaper).
%   'energyfirst' - new: among feasible options pick the lowest incremental
%                   energy; ties broken by lower peak; wait if none feasible.
%
% Every completed schedule is then re-verified with the fine sub-sampling
% peak check (verify_peak, sub=200). The conclusion is stated factually:
% if a simple variant reaches E_tr*, a simple single-step method already matches
% the exhaustive optimum on THIS instance (no claim that a new algorithm is
% necessary).
%
% Output: output/greedy_compare_<tag>.txt
if nargin < 3, tag = 'active'; end
S = enumerate_schedules(cfg);
th = thermal_build(cfg);
res = eval_schedules(S, cfg, th);
[Etr, i_tr] = minimize_energy(res, res.tr_ok);
pi_opt = S(i_tr,:);
[Ess, ~] = minimize_energy(res, res.ss_ok);

fid = fopen(fullfile(outdir, sprintf('greedy_compare_%s.txt', tag)),'w','n','UTF-8');
fprintf(fid, '=== PHASE 3: single-step greedy baselines vs exhaustive optimum ===\n');
fprintf(fid, 'active cfg: T0=%g, T_lim=%g (tag=%s)\n\n', cfg.T0, cfg.T_lim, tag);
fprintf(fid, 'Exhaustive:  E_tr* = %.4f mJ   E_ss* = %.4f mJ\n', Etr, Ess);
fprintf(fid, 'Optimal schedule (transient): %s\n', pi_str(pi_opt, cfg));
[pf_opt, pc_opt] = verify_peak(pi_opt, cfg, th, 200);
fprintf(fid, '  fine peak re-check (sub=200): coarse=%.3f C, fine=%.3f C\n\n', pc_opt, pf_opt);

fprintf(fid, '%-9s %-8s %-12s %10s %8s %6s %8s %s\n', ...
    'map_mode','prio','select','E(mJ)','gap(mJ)','waits','peak(C)','schedule');

maps = {'parallel','same','auto'};
prios = {[1 2 3 4], [2 1 3 4]};
sels = {'minpeak','energyfirst'};
best_ef = struct('E', inf, 'pi', [], 'ok', false);
for mi = 1:numel(maps)
  for pi_ = 1:numel(prios)
    for si = 1:numel(sels)
      [pi_g, Eg, ok, nw] = greedy_scheduler(cfg, th, maps{mi}, prios{pi_}, sels{si});
      if ok
        [pf, pc] = verify_peak(pi_g, cfg, th, 200);
        d = Eg - Etr;
        fprintf(fid, '%-9s %-8s %-12s %10.4f %8.4f %6d %8.3f %s\n', ...
            maps{mi}, prio_str(prios{pi_}), sels{si}, Eg, d, nw, pf, pi_str(pi_g, cfg));
        fprintf('[phase3] %-9s prio %-8s %-12s E=%.4f (gap %+.4f), fine peak=%.3f C\n', ...
            maps{mi}, prio_str(prios{pi_}), sels{si}, Eg, d, pf);
        if strcmp(sels{si},'energyfirst') && Eg < best_ef.E
          best_ef.E = Eg; best_ef.pi = pi_g; best_ef.ok = true;
        end
      else
        fprintf(fid, '%-9s %-8s %-12s %10s %8s %6d %8s %s\n', ...
            maps{mi}, prio_str(prios{pi_}), sels{si}, 'FAIL', '-', nw, '-', 'incomplete');
        fprintf('[phase3] %-9s prio %-8s %-12s FAILED\n', ...
            maps{mi}, prio_str(prios{pi_}), sels{si});
      end
    end
  end
end

% conclusion
fprintf(fid, '\n--- Conclusion (factual) ---\n');
if best_ef.ok && abs(best_ef.E - Etr) < 1e-6
  fprintf(fid, 'energy-first single-step greedy reaches E=%.4f mJ = E_tr*=%.4f mJ.\n', best_ef.E, Etr);
  fprintf(fid, '=> On THIS instance a simple single-step predictor (energy-prioritised,\n');
  fprintf(fid, '   with active waiting but no look-ahead) MATCHES the exhaustive optimum.\n');
  fprintf(fid, '   This does NOT prove any new algorithm is necessary; it only shows the\n');
  fprintf(fid, '   original minpeak rule was leaving energy on the table by preferring a\n');
  fprintf(fid, '   lower peak over the feasible, cheaper high frequency.\n');
  plot_gantt(best_ef.pi, cfg, fullfile(outdir, sprintf('gantt_energyfirst_%s.png', tag)));
elseif best_ef.ok
  fprintf(fid, 'energy-first best = %.4f mJ vs E_tr*=%.4f mJ (gap %.4f mJ).\n', ...
      best_ef.E, Etr, best_ef.E - Etr);
  fprintf(fid, 'Remaining gap; see the table above for the variant that still loses.\n');
  plot_gantt(best_ef.pi, cfg, fullfile(outdir, sprintf('gantt_energyfirst_%s.png', tag)));
else
  fprintf(fid, 'energy-first greedy FAILED to complete on this instance.\n');
end
fprintf(fid, '\nRestraint note: these simple baselines use no exhaustive optimum as a\n');
fprintf(fid, 'guide; their gap to E_tr* only characterises the simple family on this\n');
fprintf(fid, 'synthetic instance.\n');
fclose(fid);

r.Etr_mJ = Etr; r.Ess_mJ = Ess; r.best_energyfirst_mJ = best_ef.E;
end

function s = prio_str(p)
s = sprintf('%d%d%d%d', p(1), p(2), p(3), p(4));
end

function s = pi_str(pi, cfg)
fl = {'L','H'};
s = sprintf('[mA=%d mB=%d fA=%s fB=%s sA1=%d sB1=%d sA2=%d sB2=%d]', ...
    pi(1), pi(2), fl{pi(3)}, fl{pi(4)}, pi(5), pi(6), pi(7), pi(8));
end
