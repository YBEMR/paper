function [Ebest_mJ, i] = minimize_energy(res, ok)
% MINIMIZE_ENERGY  Energy-minimal schedule among feasible ones.
%   [Ebest_mJ, i] = MINIMIZE_ENERGY(res, ok)
%   Returns Inf and [] if no feasible schedule exists.
idx = find(ok);
if isempty(idx)
  Ebest_mJ = Inf; i = [];
  return;
end
[Ebest, j] = min(res.E(idx));
i = idx(j);
Ebest_mJ = Ebest*1e3;
end
