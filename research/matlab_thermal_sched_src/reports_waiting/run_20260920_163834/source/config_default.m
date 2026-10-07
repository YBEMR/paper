function cfg = config_default()
% CONFIG_DEFAULT  Default experiment configuration.
% All task, power, temperature and thermal-network parameters live here.
% Time unit: ms; power unit: W; temperature unit: degC.
cfg.name = 'cpu_npu_2c1n_v1';

% ---- Time & discretization ----
cfg.delta_ms = 1;                    % scheduling grid (ms)
cfg.D_A_ms = 20;                     % deadline of request A
cfg.D_B_ms = 24;                     % deadline of request B
cfg.H_ms = max(cfg.D_A_ms, cfg.D_B_ms); % unified observation window
cfg.s_per_ms = 1e-3;                 % ms -> s

% ---- Stage durations (ms) ----
% CPU stages have two frequency choices: index 1 = low, 2 = high.
% NPU stages run at a fixed frequency.
cfg.d_A1_ms = [6, 4];                % A1 (CPU preprocessing): low/high
cfg.d_B1_ms = [7, 5];                % B1 (CPU preprocessing): low/high
cfg.d_A2_ms = 6;                     % A2 (NPU inference)
cfg.d_B2_ms = 7;                     % B2 (NPU inference)

% ---- Running power (W) ----
cfg.P_A1 = [4.0, 5.0];               % A1 low/high.  E_low=24, E_high=20 mJ (high saves energy)
cfg.P_B1 = [5.0, 6.5];               % B1 low/high.  E_low=35, E_high=32.5 mJ
cfg.P_A2 = 6.0;                      % A2 NPU
cfg.P_B2 = 7.0;                      % B2 NPU
cfg.P_idle_C = 0.5;                  % CPU core idle power
cfg.P_idle_N = 1.0;                  % NPU idle power

% ---- Temperature ----
cfg.T_amb = 25;                      % ambient (degC)
cfg.T_lim = 80;                      % temperature limit (degC)
cfg.T0 = 45;                         % initial temperature of all three nodes

% ---- Thermal network ----
cfg.g_env = [0.08, 0.08, 0.12];      % g1, g2, gN: conductance to ambient (W/K)
cfg.g12 = 0.02;                      % CPU core 1 <-> core 2 coupling
cfg.g1N = 0.015;                     % C1 <-> NPU coupling
cfg.g2N = 0.015;                     % C2 <-> NPU coupling
cfg.C = [0.004, 0.004, 0.006];       % thermal capacitance C1,C2,CN (J/K)
end
