function res = eval_schedules(S, cfg, th, opts)
% EVAL_SCHEDULES  Batch evaluation of energy + steady/transient thermal feasibility.
%   res = EVAL_SCHEDULES(S, cfg, th)
%   opts.sub  : sub-sampling per ms for transient internal peak checking (default 4)
%   opts.block: rows per block for memory control (default 20000)
%
%   res.E       (N x 1, J)   total energy over [0,H], idle power included
%   res.ss_ok   (N x 1)      steady-state constraint: for every 1-ms constant-power
%                            interval, theta_ss = G^{-1} q must be <= T_lim
%   res.tr_ok   (N x 1)      transient constraint: sampled full temperature
%                            trajectory <= T_lim (sub-sample points inside each
%                            interval; this is a sampled constraint, reported as such)
%   res.Tmax    (N x 1, C)   max sampled temperature over the whole window
%
% NOTE: transient feasibility here is "sampled temperature constraint" with
% opts.sub points per ms; the sub-sampling density can be tightened by the user.
if nargin < 4, opts = struct(); end
if ~isfield(opts,'sub'), opts.sub = 4; end
if ~isfield(opts,'block'), opts.block = 20000; end
N = size(S,1);
res.E = zeros(N,1);
res.ss_ok = true(N,1);
T_amb = th.T_amb; T_lim = cfg.T_lim;
% explicit initial-temperature check: if the system starts above the limit,
% no transient schedule can be feasible (per the review)
res.tr_ok = repmat(cfg.T0 <= T_lim, N, 1);
res.Tmax = repmat(cfg.T0, N, 1);
dts = cfg.delta_ms * cfg.s_per_ms / opts.sub;   % substep (s)
Tstep = expm(th.A * dts);                       % 3x3
theta0 = cfg.T0 - T_amb;
Ginv = th.Ginv;
nblk = ceil(N/opts.block);
for b = 1:nblk
  idx = (b-1)*opts.block+1 : min(b*opts.block,N);
  nb = numel(idx);
  [Pc1, Pc2, Pn] = schedule_power(S(idx,:), cfg);
  H = cfg.H_ms;
  E = sum(Pc1 + Pc2 + Pn, 2) * (cfg.delta_ms*cfg.s_per_ms);
  ss_ok = true(nb,1);
  Tmax = repmat(cfg.T0,nb,1);
  theta = repmat(theta0, nb, 1);
  for k = 1:H
    q = [Pc1(:,k), Pc2(:,k), Pn(:,k)];
    thss = q * Ginv';                 % steady-state rise, N x 3
    Tss = thss + T_amb;
    ss_ok = ss_ok & all(Tss <= T_lim, 2);
    for s = 1:opts.sub
      theta = thss + (theta - thss) * Tstep';
      Tmax = max(Tmax, max(theta + T_amb, [], 2));
    end
  end
  % transient feasibility = initial temperature OK AND sampled peak OK
  % (merge the initial-temperature check, it must NOT be overwritten)
  tr_ok = (cfg.T0 <= T_lim) & (Tmax <= T_lim);
  res.E(idx) = E; res.ss_ok(idx) = ss_ok; res.tr_ok(idx) = tr_ok; res.Tmax(idx) = Tmax;
end
end
