function R = scheduling_value_analysis(cfg, outdir, tag)
% SCHEDULING_VALUE_ANALYSIS  Phase 2: in an active regime, test whether the
% scheduling decisions (start times, core mapping, NPU order) change transient
% thermal feasibility, and whether they enable the lowest-energy frequency
% combination. Per the review, indicators:
%   A) start-time choice changes transient feasibility (fixed freq + mapping)
%   B) core mapping changes transient feasibility (asymmetric cores)
%   B2) controlled mapping swap: everything else fixed, only cores swapped
%   C) whether the lowest-energy frequency combination is timing-dependent
%      (the energy question is answered by Phase 3, NOT assumed here)
% Output: output/scheduling_value_<tag>.txt and comparison figures.
if nargin < 3, tag = 'active'; end
S = enumerate_schedules(cfg);
th = thermal_build(cfg);
res = eval_schedules(S, cfg, th);
fl = {'L','H'};
fid = fopen(fullfile(outdir, sprintf('scheduling_value_%s.txt', tag)),'w','n','UTF-8');
fprintf(fid, '=== PHASE 2: do scheduling decisions change transient feasibility? ===\n');
fprintf(fid, 'active cfg: T0=%g, T_lim=%g (tag=%s)\n\n', cfg.T0, cfg.T_lim, tag);

% ================= Indicator A =================
fprintf(fid, '--- Indicator A: start-time choice changes transient feasibility ---\n');
fprintf(fid, '(fixed frequency combination and core mapping; varying only start times)\n');
A_hits = 0;
for fA = 1:2
  for fB = 1:2
    for mA = 1:2
      for mB = 1:2
        sel = (S(:,1)==mA)&(S(:,2)==mB)&(S(:,3)==fA)&(S(:,4)==fB);
        n = sum(sel);
        if n == 0, continue; end
        nok = sum(sel & res.tr_ok);
        if nok > 0 && nok < n
          A_hits = A_hits + 1;
          fprintf(fid, '  fA=%s fB=%s map=(C%d,C%d): %d/%d timing choices feasible, %d exceed T_lim\n', ...
              fl{fA}, fl{fB}, mA, mB, nok, n, n-nok);
        end
      end
    end
  end
end
fprintf(fid, '  -> %d (freq, mapping) cells show timing-dependent feasibility\n\n', A_hits);

% ================= Indicator C illustration within HH =================
selHH = (S(:,3)==2) & (S(:,4)==2);
nHH = sum(selHH); nHHok = sum(selHH & res.tr_ok);
fprintf(fid, '--- Indicator C: does timing enable the lowest-energy combination (HH)? ---\n');
fprintf(fid, '  HH schedules total: %d, transient-feasible: %d, rejected: %d\n', ...
    nHH, nHHok, nHH - nHHok);
fprintf(fid, '  energy per frequency combination (mJ): LL=%.2f LH=%.2f HL=%.2f HH=%.2f\n', ...
    comboE(1,1,S,res), comboE(1,2,S,res), comboE(2,1,S,res), comboE(2,2,S,res));
fprintf(fid, '  FACT: HH is the lowest-energy combination and its feasibility varies\n');
fprintf(fid, '  with timing. Whether a SIMPLE timing policy can realize this energy is\n');
fprintf(fid, '  checked separately in greedy_compare_*.txt (Phase 3), NOT assumed here.\n\n');

% pick the hottest rejected HH schedule (bad timing) and the coolest feasible HH
selbad = selHH & ~res.tr_ok;
if any(selbad)
  idxb = find(selbad);
  [~, j] = max(res.Tmax(idxb));
  pi_bad = S(idxb(j),:); peak_bad = res.Tmax(idxb(j));
else
  pi_bad = []; peak_bad = NaN;
end
selgood = selHH & res.tr_ok;
if any(selgood)
  idxg = find(selgood);
  [~, j] = min(res.Tmax(idxg));
  pi_good = S(idxg(j),:); peak_good = res.Tmax(idxg(j));
else
  pi_good = []; peak_good = NaN;
end
if ~isempty(pi_bad) && ~isempty(pi_good)
  [pf_bad, pc_bad] = verify_peak(pi_bad, cfg, th, 200);
  [pf_good, pc_good] = verify_peak(pi_good, cfg, th, 200);
  fprintf(fid, '  Timing comparison inside HH (same frequency, same energy):\n');
  fprintf(fid, '    bad timing  %s  peak=%.2f C (VIOLATION), fine recheck(sub=200)=%.3f C\n', ...
      pi_str(pi_bad, cfg), peak_bad, pf_bad);
  fprintf(fid, '    good timing %s  peak=%.2f C (OK), fine recheck(sub=200)=%.3f C\n', ...
      pi_str(pi_good, cfg), peak_good, pf_good);
  fprintf(fid, '    (coarse screening peaks were %.3f / %.3f C)\n', pc_bad, pc_good);
  plot_gantt(pi_bad, cfg, fullfile(outdir, sprintf('gantt_HH_bad_%s.png', tag)));
  plot_gantt(pi_good, cfg, fullfile(outdir, sprintf('gantt_HH_good_%s.png', tag)));
  plot_temperature(pi_bad, pi_good, cfg, th, ...
      fullfile(outdir, sprintf('temp_HH_badgood_%s.png', tag)), ...
      'bad timing (peak>T_{lim})', 'good timing (feasible)');
end
fprintf(fid, '\n');

% ================= Indicator B: mapping with asymmetric cores =================
fprintf(fid, '--- Indicator B: core mapping changes transient feasibility ---\n');
fprintf(fid, '(asymmetric cores: g1=0.06, g2=0.08, g1N=0.03, g2N=0.01; same tasks)\n');
casym = cfg;
casym.g_env = [0.06, 0.08, cfg.g_env(3)];
casym.g1N = 0.03; casym.g2N = 0.01;
thas = thermal_build(casym);
resas = eval_schedules(S, casym, thas);
for fA = 1:2
  for fB = 1:2
    mapstats = zeros(2,2,2);  % (mA,mB,:) = [total, ok_sym, ok_asym]
    for mA = 1:2
      for mB = 1:2
        sel = (S(:,1)==mA)&(S(:,2)==mB)&(S(:,3)==fA)&(S(:,4)==fB);
        mapstats(mA,mB,1) = sum(sel);
        mapstats(mA,mB,2) = sum(sel & res.tr_ok);
        mapstats(mA,mB,3) = sum(sel & resas.tr_ok);
      end
    end
    fprintf(fid, '  fA=%s fB=%s: map (C1,C2)->(A1,B1)  |  total  | tr_ok(sym) | tr_ok(asym)\n', fl{fA}, fl{fB});
    for mA = 1:2
      for mB = 1:2
        fprintf(fid, '      mA=%d mB=%d : %6d  | %6d  | %6d\n', mA, mB, ...
            mapstats(mA,mB,1), mapstats(mA,mB,2), mapstats(mA,mB,3));
      end
    end
    fprintf(fid, '      (sym cores: map (1,2) == map (2,1) by symmetry; asym cores: differ)\n');
  end
end

% ================= Indicator B2: controlled mapping swap =================
fprintf(fid, '\n--- Indicator B2: mapping swap with EVERYTHING ELSE fixed (controlled) ---\n');
fprintf(fid, '  Only the core assignment (1,2)<->(2,1) changes; frequency and ALL\n');
fprintf(fid, '  start times are identical. Count swaps where the same timing flips\n');
fprintf(fid, '  across the T_lim boundary under the asymmetric-core model.\n');
sel12 = (S(:,1)==1) & (S(:,2)==2);
n12 = sum(sel12);
% sanity: symmetric cores must leave peak identical (label exchange)
maxdiff_sym = 0;
for i = find(sel12)'
  pi_o = S(i,:);
  pi_s = [2 1 pi_o(3:8)];
  [~, To] = compute_trajectory(pi_o, cfg, th, 4);
  [~, Ts] = compute_trajectory(pi_s, cfg, th, 4);
  maxdiff_sym = max(maxdiff_sym, abs(max(To(:))-max(Ts(:))));
end
fprintf(fid, '  symmetric cores: max |peak(swap)-peak(orig)| = %.6f C (should be ~0)\n', maxdiff_sym);
% asymmetric crossings
n_cross = 0; first_ex = [];
for i = find(sel12)'
  pi_o = S(i,:);
  pi_s = [2 1 pi_o(3:8)];
  [~, To] = compute_trajectory(pi_o, casym, thas, 4);
  [~, Ts] = compute_trajectory(pi_s, casym, thas, 4);
  po = max(To(:)); ps = max(Ts(:));
  if (po > cfg.T_lim && ps <= cfg.T_lim) || (ps > cfg.T_lim && po <= cfg.T_lim)
    n_cross = n_cross + 1;
    if isempty(first_ex)
      first_ex = struct('orig', pi_o, 'swap', pi_s, 'p_orig', po, 'p_swap', ps);
    end
  end
end
fprintf(fid, '  asymmetric cores: %d/%d (1,2)-schedules flip feasibility on a pure mapping swap\n', n_cross, n12);
if ~isempty(first_ex)
  fprintf(fid, '  example: orig %s peak=%.2f C  vs  swap %s peak=%.2f C\n', ...
      pi_str(first_ex.orig, cfg), first_ex.p_orig, pi_str(first_ex.swap, cfg), first_ex.p_swap);
end
fprintf(fid, '  CAUTION: a mapping swap changing peak for a FIXED timing does not by\n');
fprintf(fid, '  itself show a mapping change improves ENERGY (see Phase 3).\n');
fclose(fid);

R.A_hits = A_hits;
R.nHH = nHH; R.nHHok = nHHok;
R.pi_bad = pi_bad; R.pi_good = pi_good;
R.peak_bad = peak_bad; R.peak_good = peak_good;
R.n_cross_swap = n_cross;
fprintf('[phase2] A: %d timing-dependent cells; HH: %d/%d feasible; B2 crossing swaps: %d\n', ...
    A_hits, nHHok, nHH, n_cross);
if ~isempty(pi_bad)
  fprintf('[phase2] bad timing peak=%.2f C vs good timing peak=%.2f C (same HH, same energy)\n', ...
      peak_bad, peak_good);
end
end

function E = comboE(fA, fB, S, res)
sel = (S(:,3)==fA) & (S(:,4)==fB);
E = min(res.E(sel))*1e3;
end

function s = pi_str(pi, cfg)
fl = {'L','H'};
s = sprintf('[mA=%d mB=%d fA=%s fB=%s sA1=%d sB1=%d sA2=%d sB2=%d]', ...
    pi(1), pi(2), fl{pi(3)}, fl{pi(4)}, pi(5), pi(6), pi(7), pi(8));
end
