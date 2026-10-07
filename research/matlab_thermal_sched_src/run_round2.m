function run_round2()
% RUN_ROUND2  Second-round experiments per review:
%   Phase 1: scan power x T0 x tau to locate the regime where the transient
%            constraint binds and schedule decisions can matter.
%   Phase 2: in an active regime, indicators A (timing changes thermal
%            feasibility), B (mapping changes feasibility, asymmetric cores)
%            and C (timing enables the lowest-energy frequency combo).
%   Phase 3: single-step transient-prediction greedy vs exhaustive optimum.
cfg = config_default();
outdir = fullfile(pwd, 'output');
if ~exist(outdir, 'dir'), mkdir(outdir); end

fprintf('=== ROUND 2: locating where scheduling decisions matter ===\n\n');

% ---- Phase 1 ----
R = scan_active_region(cfg, outdir);

% ---- pick the most discriminating active configuration ----
% criteria: transient constraint binds (n_tr_rej>0), transient optimum exists,
% and the lowest-energy combo HH is only partially feasible (0 < ok < total),
% i.e. timing actually decides whether HH can be used.
best = []; bestscore = -Inf;
for i = 1:numel(R.rows)
  r = R.rows{i};
  if r.n_tr_rej > 0 && isfinite(r.Etr_mJ) && ...
     r.freq_ok(2,2) > 0 && r.freq_ok(2,2) < r.freq_total(2,2)
    if r.n_tr_rej > bestscore
      bestscore = r.n_tr_rej; best = i;
    end
  end
end
if isempty(best)
  fprintf('[round2] no active configuration with timing-dependent HH found; skipping Phases 2-3.\n');
  return;
end
fprintf('\n[round2] selected active configuration: %s (tr_rej=%d)\n', R.labels{best}, bestscore);
c = rebuild_cfg(cfg, R.labels{best});

% ---- Phase 2 ----
scheduling_value_analysis(c, outdir, R.labels{best});

% ---- Phase 3 ----
run_greedy_compare(c, outdir, R.labels{best});
end

function c = rebuild_cfg(cfg, label)
tok = regexp(label, 'lam([\d.]+)_T0(\d+)_tau([\d.]+)', 'tokens');
lam = str2double(tok{1}{1}); T0v = str2double(tok{1}{2}); tauv = str2double(tok{1}{3});
c = cfg;
c.P_A1 = cfg.P_A1*lam; c.P_B1 = cfg.P_B1*lam;
c.P_A2 = cfg.P_A2*lam; c.P_B2 = cfg.P_B2*lam;
c.T0 = T0v; c.C = cfg.C*tauv;
end
