function run_all()
% RUN_ALL  End-to-end pipeline for the first-round minimal model:
%   1) correctness tests (single-node analytic check, boundary cases)
%   2) main experiment   (steady vs transient)
%   3) ablations         (no coupling, no dependency)
%   4) parameter scan    (T0, tau, duration)
% All reports and figures go to ./output
cfg = config_default();
outdir = fullfile(pwd, 'output');
if ~exist(outdir, 'dir'), mkdir(outdir); end

fprintf('=== MATLAB minimal model: 2 CPU cores + 1 NPU, 2 inference requests ===\n');
fprintf('T_amb=%g, T_lim=%g, T0=%g, D_A=%dms, D_B=%dms, H=%dms, delta=%gms\n\n', ...
    cfg.T_amb, cfg.T_lim, cfg.T0, cfg.D_A_ms, cfg.D_B_ms, cfg.H_ms, cfg.delta_ms);

% ---- 1. correctness tests ----
fprintf('--- Test 2: single-node analytic check ---\n');
r1 = single_node_test(cfg);
fprintf('max|num-ana| = %.3e, tau = %.1f ms, ratio@tau = %.6f (e^-1=%.6f)  -> %s\n', ...
    r1.max_abs_err, r1.tau_ms, r1.ratio_at_tau, r1.e_inv, pass_str(r1.pass));

fprintf('--- Boundary test A: T_lim=200 (constraints inactive) ---\n');
r2 = boundary_tests(cfg);
fprintf('E_ss* = %.6f mJ, E_tr* = %.6f mJ, E_glob = %.6f mJ  -> %s\n', ...
    r2.TestA.Ess, r2.TestA.Etr, r2.TestA.Eglob, pass_str(r2.TestA.pass));
fprintf('--- Boundary test B: finer grid delta=0.5ms ---\n');
fprintf('E_tr* coarse=%.6f mJ, fine=%.6f mJ, diff=%.6f  -> %s\n', ...
    r2.TestB.Etr_coarse, r2.TestB.Etr_fine, r2.TestB.dE_grid, pass_str(r2.TestB.pass));

% ---- 2. main experiment ----
fprintf('\n--- Main experiment ---\n');
m = run_main(cfg, outdir);

% ---- 3. ablations ----
fprintf('\n--- Ablations ---\n');
a = run_ablation(cfg, outdir);

% ---- 4. parameter scan ----
fprintf('\n--- Parameter scan ---\n');
sc = param_scan(cfg, outdir);

% ---- summary file ----
fid = fopen(fullfile(outdir,'report.txt'),'w','n','UTF-8');
fprintf(fid, '=== SUMMARY (first-round minimal model) ===\n');
fprintf(fid, 'Correctness: single-node %s | boundary-A %s | boundary-B(fine grid) %s\n', ...
    pass_str(r1.pass), pass_str(r2.TestA.pass), pass_str(r2.TestB.pass));
fprintf(fid, 'Main: base=%d, ss=%d, tr=%d, tr_only=%d, E_ss*=%.4f mJ, E_tr*=%.4f mJ, dE=%.4f mJ\n', ...
    m.n_base, m.n_ss, m.n_tr, m.n_tr_only, m.Ess_mJ, m.Etr_mJ, m.dE_mJ);
fprintf(fid, 'Ablation: coupled dE=%.4f | uncoupled dE=%.4f | nodep dE=%.4f (mJ)\n', ...
    a.base.dE_mJ, a.uncoupled.dE_mJ, a.nodep.dE_mJ);
fprintf(fid, 'Scan dE (mJ): %s\n', num2str(sc.dE_mJ, '%.4f '));
fclose(fid);

fprintf('\nDone. Reports and figures in: %s\n', outdir);
end

function s = pass_str(ok)
if ok, s = 'PASS'; else, s = 'FAIL'; end
end
