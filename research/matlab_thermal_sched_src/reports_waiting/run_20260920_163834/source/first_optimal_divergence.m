function [tstar, remaining] = first_optimal_divergence(pi, Opt, cfg, allow_swap)
% Filter all optimal completions using only decisions made at each time.
% Core permutations, when valid, are fixed for an entire candidate history.
% A NaN start denotes a stage that never started (partial schedule).
if nargin<4, allow_swap=false; end
tstar=NaN; remaining=nan(cfg.H_ms,1);
if isempty(Opt), return; end
pool=double(Opt);
if allow_swap
    assert(cfg.C(1)==cfg.C(2) && cfg.g_env(1)==cfg.g_env(2) && cfg.g1N==cfg.g2N,...
        'first_optimal_divergence:asymmetric', 'Core swapping requires a symmetric model.');
    swapped=pool; swapped(:,1:2)=3-swapped(:,1:2);
    pool=[pool;swapped];
end
for t=0:cfg.H_ms-1
    events=(pi(5:8)==t);
    keep=all((pool(:,5:8)==t)==events,2);
    for j=find(events)
        if j<=2
            keep=keep & pool(:,j)==pi(j) & pool(:,j+2)==pi(j+2);
        end
    end
    pool=pool(keep,:); remaining(t+1)=size(pool,1);
    if isempty(pool), tstar=t; return; end
end
end
