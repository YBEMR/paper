function [pi, E_mJ, ok, n_wait] = greedy_scheduler(cfg, th, map_mode, priority, select_mode)
% GREEDY_SCHEDULER  A SIMPLE single-step transient-prediction baseline.
%
% NOTE (per review): this is a *simple* baseline, NOT a "strong temperature-
% feedback scheduler". It answers: "how well does a fixed-priority scheduler
% with one-step thermal prediction do?"
%
% Two SELECTION rules (per the latest review), both single-step (no look-ahead,
% no exhaustive optimum used):
%   select_mode = 'minpeak'     (original "lowest predicted-peak greedy"):
%       among feasible (core, frequency) options pick the one with the lowest
%       predicted peak.  NOTE: this can pick a lower frequency even when the
%       high frequency is already thermally feasible and uses less energy.
%   select_mode = 'energyfirst' (new "energy-prioritised single-step greedy"):
%       among feasible options pick the one with the LOWEST INCREMENTAL ENERGY
%       ( (P_run - P_idle_r)*d ).  Ties on incremental energy are broken by the
%       lower predicted peak.  If the cheapest option is infeasible, fall back
%       to the next-cheaper option; if NONE is feasible, WAIT (no commit).
%
% Common behavior (identical for both rules):
%   - at each integer-ms decision time, ready stages tried in priority order;
%   - trial from the CURRENT temperature predicts sampled peak over the
%     candidate stage execution (same RC model, same sub-sampling);
%   - mapping: 'parallel' (A1->C1, B1->C2), 'same' (both on C1), or 'auto'
%     (choose the idle core; tie-broken by lower predicted peak);
%   - waiting: ALL intermediate ms are re-examined (full resolution).
%
% Returns pi = [mA mB fA fB sA1 sB1 sA2 sB2], E (mJ), ok, n_wait (ms waited).
if nargin < 3, map_mode = 'parallel'; end
if nargin < 4, priority = [1 2 3 4]; end
if nargin < 5, select_mode = 'minpeak'; end

Tlim = cfg.T_lim; Tamb = th.T_amb; T0 = cfg.T0;
H = cfg.H_ms; DA = cfg.D_A_ms; DB = cfg.D_B_ms;
rA = 0; rB = 0;
if isfield(cfg,'rA_ms'), rA = cfg.rA_ms; end   % request release times
if isfield(cfg,'rB_ms'), rB = cfg.rB_ms; end
sub = 4; dts = cfg.delta_ms*cfg.s_per_ms/sub;
Tstep = expm(th.A*dts); Ginv = th.Ginv;

switch map_mode
  case 'parallel', resOf = [1 2 3 3];   % A1->C1, B1->C2
  case 'same',     resOf = [1 1 3 3];   % A1->C1, B1->C1
  case 'auto',     resOf = [0 0 3 3];   % CPU cores chosen dynamically
end

% ---- per-ms power table (committed schedule) ----
Pc1 = repmat(cfg.P_idle_C, 1, H);
Pc2 = repmat(cfg.P_idle_C, 1, H);
Pn  = repmat(cfg.P_idle_N, 1, H);

started = false(1,4); done = false(1,4);
s = zeros(1,4); fsel = [1 1];           % fsel(1)=fA, fsel(2)=fB (1=L,2=H)
n_wait = 0;

t = 0;
while ~all(done) && t <= H
  % update done flags (full ms-resolution, no event skipping)
  for jj = 1:4
    if started(jj) && ~done(jj) && t >= s(jj) + stage_dur(jj, fsel(min(jj,2)))
      done(jj) = true;
    end
  end
  if all(done), break; end

  % one decision round at time t: multiple commits allowed (different resources)
  committed_any = false;
  while true
    committed = false;
    for jj2 = 1:numel(priority)
      j = priority(jj2);
      if started(j) || done(j), continue; end
      if j == 1 && t < rA, continue; end      % A not released yet
      if j == 2 && t < rB, continue; end      % B not released yet
      if j == 3 && ~done(1), continue; end   % A2 needs A1 done
      if j == 4 && ~done(2), continue; end   % B2 needs B1 done
      % candidate cores for CPU stages
      if j <= 2
        if strcmp(map_mode,'auto')
          cores = [1 2];
        else
          cores = resOf(j);
        end
      else
        cores = 3;
      end
      % collect ALL feasible (core, frequency) candidates
      cand = zeros(0,4);   % columns: r, fc, dd, peak
      candE = zeros(0,1);  % incremental energy (J)
      for r = cores
        f_candidates = [2 1];
        if j > 2, f_candidates = 1; end
        for fc = f_candidates
          dd = stage_dur(j, fc);
          if t + dd > H, continue; end
          if j == 3 && t + dd > DA, continue; end
          if j == 4 && t + dd > DB, continue; end
          if busy_interval(r, t, t+dd), continue; end
          q_run = current_q(t, t+dd, r, stage_pow(j, fc));
          peak = trial_from(t, q_run);
          if peak <= Tlim + 1e-9
            dE = (stage_pow(j,fc) - idle_of(r)) * dd * cfg.s_per_ms;
            cand(end+1,:) = [r, fc, dd, peak]; %#ok<AGROW>
            candE(end+1,1) = dE;               %#ok<AGROW>
          end
        end
      end
      if ~isempty(cand)
        if strcmp(select_mode,'energyfirst')
          % lowest incremental energy; ties -> lower predicted peak
          [~, k] = sortrows([candE, cand(:,4)]);
        else
          % minpeak (original): lowest predicted peak; ties -> lower energy
          [~, k] = sortrows([cand(:,4), candE]);
        end
        ch = k(1);
        best_r = cand(ch,1); best_fc = cand(ch,2);
        if j <= 2, fsel(j) = best_fc; resOf(j) = best_r; end
        s(j) = t; started(j) = true;
        apply_stage(j, s(j), stage_dur(j, fsel(min(j,2))), stage_pow(j, fsel(min(j,2))));
        committed = true;
        committed_any = true;
        break;
      end
    end
    if ~committed, break; end
  end

  if ~committed_any, n_wait = n_wait + 1; end   % one full ms with no commit = active wait
  t = t + 1;                               % full ms-resolution waiting
end

% ---- result ----
pi = [resOf(1) resOf(2) fsel(1) fsel(2) s(1) s(2) s(3) s(4)];
ok = all(done);
if ok
  ok = (s(3) + cfg.d_A2_ms <= DA) && (s(4) + cfg.d_B2_ms <= DB);
end
E_mJ = (sum(Pc1) + sum(Pc2) + sum(Pn)) * (cfg.delta_ms*cfg.s_per_ms) * 1e3;

% ---- nested helpers ----
  function pw0 = idle_of(r)
    if r == 3, pw0 = cfg.P_idle_N; else, pw0 = cfg.P_idle_C; end
  end
  function dur = stage_dur(j, f)
    if j == 1, dur = cfg.d_A1_ms(f);
    elseif j == 2, dur = cfg.d_B1_ms(f);
    elseif j == 3, dur = cfg.d_A2_ms;
    else, dur = cfg.d_B2_ms; end
  end
  function pw = stage_pow(j, f)
    if j == 1, pw = cfg.P_A1(f);
    elseif j == 2, pw = cfg.P_B1(f);
    elseif j == 3, pw = cfg.P_A2;
    else, pw = cfg.P_B2; end
  end
  function busy = busy_interval(r, a, b)
    busy = false;
    for jj4 = 1:4
      if started(jj4) && resOf(jj4) == r
        d0 = stage_dur(jj4, fsel(min(jj4,2)));
        if s(jj4) < b && s(jj4)+d0 > a, busy = true; end
      end
    end
  end
  function q = current_q(a, b, r, pw)
    n = b - a;
    q = zeros(3, n);
    q(1,:) = Pc1(a+1:b);
    q(2,:) = Pc2(a+1:b);
    q(3,:) = Pn(a+1:b);
    q(r,:) = pw;
  end
  function apply_stage(j, a, dd, pw)
    r = resOf(j);
    if r == 1, Pc1(a+1:a+dd) = pw;
    elseif r == 2, Pc2(a+1:a+dd) = pw;
    else, Pn(a+1:a+dd) = pw; end
  end
  function peak = trial_from(a, q_run)
    theta = theta_at(a);
    peak = max(theta + Tamb);
    nsub = size(q_run,2)*sub;
    for i = 1:nsub
      kk = floor((i-1)/sub) + 1;
      thss = Ginv*q_run(:,kk);
      theta = thss + Tstep*(theta - thss);
      peak = max(peak, theta + Tamb);
    end
    peak = max(peak);                      % scalar over the 3 nodes
  end
  function th = theta_at(a)
    th = repmat(T0 - Tamb, 3, 1);
    for kk2 = 1:a
      q = [Pc1(kk2); Pc2(kk2); Pn(kk2)];
      thss = Ginv*q;
      for s2 = 1:sub
        th = thss + Tstep*(th - thss);
      end
    end
  end
end
