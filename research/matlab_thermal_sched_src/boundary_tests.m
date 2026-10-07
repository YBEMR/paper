function r = boundary_tests(cfg)
% BOUNDARY_TESTS  Correctness checks required before trusting optimization.
%   Test A (boundary case 1): with T_lim very high, steady and transient
%   optimizers must agree with each other and with the unconstrained optimum.
%   Test B (finer grid): re-solve with delta = 0.5 ms (time axis doubled,
%   stage durations and deadlines scaled by 2, same physical problem) and
%   compare the transient optimum against the delta = 1 ms result.
r = struct();

% ---- Test A: thermal constraints inactive ----
cfgA = cfg; cfgA.T_lim = 200;
SA = enumerate_schedules(cfgA);
thA = thermal_build(cfgA);
resA = eval_schedules(SA, cfgA, thA);
rA.Ess = min(resA.E(resA.ss_ok))*1e3;
rA.Etr = min(resA.E(resA.tr_ok))*1e3;
rA.Eglob = min(resA.E)*1e3;
rA.pass = (rA.Ess == rA.Etr) && (rA.Etr == rA.Eglob);

% ---- Test B: finer grid delta = 0.5 ms (doubled time axis) ----
cfgB = cfg;
cfgB.delta_ms = 0.5;
cfgB.d_A1_ms = cfg.d_A1_ms*2; cfgB.d_B1_ms = cfg.d_B1_ms*2;
cfgB.d_A2_ms = cfg.d_A2_ms*2; cfgB.d_B2_ms = cfg.d_B2_ms*2;
cfgB.D_A_ms = cfg.D_A_ms*2; cfgB.D_B_ms = cfg.D_B_ms*2;
cfgB.H_ms = cfgB.D_B_ms;
SB = enumerate_schedules(cfgB);
thB = thermal_build(cfgB);
resB = eval_schedules(SB, cfgB, thB);
rB.Etr_fine = min(resB.E(resB.tr_ok))*1e3;
rB.n_base_fine = size(SB,1);

% coarse (delta = 1 ms) reference with nominal T_lim
SAc = enumerate_schedules(cfg);
thAc = thermal_build(cfg);
resAc = eval_schedules(SAc, cfg, thAc);
rB.Etr_coarse = min(resAc.E(resAc.tr_ok))*1e3;
rB.n_base_coarse = size(SAc,1);
rB.dE_grid = rB.Etr_coarse - rB.Etr_fine;
rB.pass = abs(rB.dE_grid) < 1e-6;   % conclusion must not flip on grid refinement

r.TestA = rA; r.TestB = rB;
end
