function a = run_ablation(cfg, outdir)
% RUN_ABLATION  Two ablation experiments on the SAME task/power/deadline set:
%   (1) no CPU-NPU thermal coupling   : g1N=g2N=0, G rebuilt from network def
%   (2) structural ablation A         : remove A1->A2 and B1->B2 dependencies
% The NPU-resource-capacity ablation is deferred (per plan).
% Output: output/ablation_report.txt
a = struct();

% ---- baseline ----
S  = enumerate_schedules(cfg);
th = thermal_build(cfg);
res  = eval_schedules(S, cfg, th);
a.base = summarize(S, res, cfg);

% ---- ablation 1: uncoupled ----
th1 = thermal_build(cfg, true);
res1 = eval_schedules(S, cfg, th1);        % same schedules, same energies
a.uncoupled = summarize(S, res1, cfg);

% ---- ablation 2: remove CPU->NPU dependency ----
opts2.remove_dependency = true;
S2 = enumerate_schedules(cfg, opts2);
res2 = eval_schedules(S2, cfg, th);
a.nodep = summarize(S2, res2, cfg);

% ---- report ----
fid = fopen(fullfile(outdir,'ablation_report.txt'),'w','n','UTF-8');
fprintf(fid, '=== ABLATION EXPERIMENTS ===\n\n');
hdrS = '%-28s %10s %10s %10s %12s %12s %12s %10s\n';
hdrN = '%-28s %10d %10d %10d %12d %12.4f %12.4f %10.4f\n';
fprintf(fid, hdrS, 'case','n_base','n_ss','n_tr','n_tr_only','E_ss*(mJ)','E_tr*(mJ)','dE(mJ)');
row = @(name,s) fprintf(fid, hdrN, name, s.n_base, s.n_ss, s.n_tr, s.n_tr_only, ...
    s.Ess_mJ, s.Etr_mJ, s.dE_mJ);
row('baseline (coupled, dep)', a.base);
row('no CPU-NPU coupling', a.uncoupled);
row('no CPU->NPU dependency', a.nodep);
fprintf(fid, '\nNotes:\n');
fprintf(fid, '  - uncoupled: same task/power/deadline, only g1N=g2N=0 with G\n');
fprintf(fid, '    rebuilt from the original network definition (diagonal g1+g12 etc.).\n');
fprintf(fid, '  - In the uncoupled model the NPU loses its two extra heat paths to the\n');
fprintf(fid, '    CPU cores; if E_ss* is Inf there, no schedule passes the steady check\n');
fprintf(fid, '    (NPU steady equilibrium with B2 exceeds the limit) while transient\n');
fprintf(fid, '    schedules remain feasible.\n');
fprintf(fid, '  - no-dependency: theoretical ablation only; added schedules are NOT\n');
fprintf(fid, '    executable in a real inference pipeline.\n');
fclose(fid);

% ---- console ----
fprintf('[abl] baseline: dE=%.4f  uncoupled: dE=%.4f  nodep: dE=%.4f (mJ)\n', ...
    a.base.dE_mJ, a.uncoupled.dE_mJ, a.nodep.dE_mJ);
end

function s = summarize(S, res, cfg)
s.n_base = size(S,1);
s.n_ss = sum(res.ss_ok);
s.n_tr = sum(res.tr_ok);
s.n_tr_only = sum(~res.ss_ok & res.tr_ok);
s.n_ss_only = sum(res.ss_ok & ~res.tr_ok);
[Ess, ~] = minimize_energy(res, res.ss_ok);
[Etr, ~] = minimize_energy(res, res.tr_ok);
s.Ess_mJ = Ess; s.Etr_mJ = Etr; s.dE_mJ = Ess - Etr;
end
