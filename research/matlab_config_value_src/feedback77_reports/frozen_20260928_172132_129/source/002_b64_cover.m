function rows=b64_cover(c)
% Test-only complete traversal, no energy/thermal pruning or probes.
d=b64_data(c);Q={b64_root(d)};rows=zeros(0,2*c.n);
while ~isempty(Q)
 N=Q{end};Q(end)=[];[ok,~]=b64_propagate(d,N);if ~ok,continue;end
 if N.phase==3 && all(isfinite(N.s))
  s=b64_schedule(d,N.m,N.s);v=s55_validate(c,s);assert(v.feasible,v.reason);
  rows(end+1,:)=[N.m N.s/d.g]; %#ok<AGROW>
 else
  kids=b64_expand(d,N);Q=[Q kids]; %#ok<AGROW>
 end
end
rows=sortrows(rows);
end
