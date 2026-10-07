function th = thermal_build(cfg, uncoupled)
% THERMAL_BUILD  Build the 3-node RC thermal network.
%   th = THERMAL_BUILD(cfg)        coupled model (g1N,g2N as in cfg)
%   th = THERMAL_BUILD(cfg, true)  uncoupled model: g1N=g2N=0, G rebuilt from
%                                  the original network definition (diagonal
%                                  terms g1+g12, g2+g12, gN; NOT a naive zeroing
%                                  of off-diagonal entries of the coupled G).
%
% Continuous model:  C*theta_dot = -G*theta + q
% Steady state:      theta_ss = G^{-1} q
% Per-interval step: theta(t+dt) = theta_ss + expm(A*dt)*(theta(t)-theta_ss),
%                    A = -C^{-1} G.
if nargin < 2, uncoupled = false; end
g1 = cfg.g_env(1); g2 = cfg.g_env(2); gN = cfg.g_env(3);
g12 = cfg.g12;
if uncoupled
    g1N = 0; g2N = 0;
else
    g1N = cfg.g1N; g2N = cfg.g2N;
end
G = [ g1+g12+g1N,      -g12,       -g1N;
      -g12,      g2+g12+g2N,       -g2N;
      -g1N,           -g2N,  gN+g1N+g2N ];
C = diag(cfg.C);
A = -C \ G;
Ginv = inv(G);
th.G = G; th.C = C; th.A = A; th.Ginv = Ginv;
th.g1N = g1N; th.g2N = g2N;
th.T_amb = cfg.T_amb;
th.uncoupled = uncoupled;
end
