function [peak_fine, peak_coarse] = verify_peak(pi, cfg, th, sub_fine)
% VERIFY_PEAK  Re-check the peak temperature of one schedule with a much finer
% sub-sampling density than the screening pass.
%   [peak_fine, peak_coarse] = VERIFY_PEAK(pi, cfg, th, sub_fine)
%   sub_fine: substeps per ms for the fine pass (e.g. 200 -> 0.005 ms).
%   peak_coarse uses sub=4 (the screening density) for comparison, giving an
%   empirical indication of sampling convergence.
if nargin < 4, sub_fine = 200; end
[~, Tf] = compute_trajectory(pi, cfg, th, sub_fine);
[~, Tc] = compute_trajectory(pi, cfg, th, 4);
peak_fine = max(Tf(:));
peak_coarse = max(Tc(:));
end
