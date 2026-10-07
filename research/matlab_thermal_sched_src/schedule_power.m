function [P_C1, P_C2, P_N] = schedule_power(S, cfg)
% SCHEDULE_POWER  Per-schedule 1-ms power matrix.
%   [P_C1,P_C2,P_N] = SCHEDULE_POWER(S,cfg)
%   S: N x 8 schedule array. Returns N x H matrices with per-ms power of
%   CPU core 1, CPU core 2 and NPU (idle power when the resource is idle).
N = size(S,1); H = cfg.H_ms;
mA = S(:,1); mB = S(:,2); fA = S(:,3); fB = S(:,4);
sA1 = double(S(:,5)); sB1 = double(S(:,6));
sA2 = double(S(:,7)); sB2 = double(S(:,8));
dA1 = cfg.d_A1_ms(fA)'; dB1 = cfg.d_B1_ms(fB)';
dA2 = cfg.d_A2_ms; dB2 = cfg.d_B2_ms;
pA1 = cfg.P_A1(fA)'; pB1 = cfg.P_B1(fB)';
pA2 = cfg.P_A2; pB2 = cfg.P_B2;
P_C1 = repmat(cfg.P_idle_C, N, H);
P_C2 = repmat(cfg.P_idle_C, N, H);
P_N  = repmat(cfg.P_idle_N, N, H);
for k = 0:H-1
  kk = k+1;
  a1 = (k >= sA1) & (k < sA1 + dA1);
  b1 = (k >= sB1) & (k < sB1 + dB1);
  a2 = (k >= sA2) & (k < sA2 + dA2);
  b2 = (k >= sB2) & (k < sB2 + dB2);
  a1c1 = a1 & (mA==1); a1c2 = a1 & (mA==2);
  b1c1 = b1 & (mB==1); b1c2 = b1 & (mB==2);
  P_C1(a1c1,kk) = pA1(a1c1);
  P_C1(b1c1,kk) = pB1(b1c1);
  P_C2(a1c2,kk) = pA1(a1c2);
  P_C2(b1c2,kk) = pB1(b1c2);
  P_N(a2,kk) = pA2;
  P_N(b2,kk) = pB2;
end
end
