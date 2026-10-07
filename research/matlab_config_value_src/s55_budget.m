function s55_budget(b,phase)
if isfield(b,'inject_phase') && strcmp(b.inject_phase,phase)
    if isfield(b,'inject_error'),error(b.inject_error,'Test-injected failure at %s',phase);end
    error('s55:timeout','Test-injected timeout at %s',phase);
end
if toc(b.timer)>b.limit, error('s55:timeout','Budget exceeded at %s',phase); end
end
