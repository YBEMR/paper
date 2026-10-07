function v=s55_validate(c,s,partial)
% Independent full-schedule validation; not the enumerator's pruning code.
if nargin<3, partial=false; end
r={}; n=c.n; fields={'choice','unit','mode','start','finish','duration','increment'};
if ~all(cellfun(@(f)isfield(s,f) && numel(s.(f))==n,fields))
    v=struct('feasible',false,'reason','shape','completion',nan(size(c.terminal))); return;
end
known=isfinite(s.start); tol=c.time_tol;
if ~partial && ~all(known), r{end+1}='incomplete'; end
for j=1:numel(fields)
    f=fields{j}; if any(~isfinite(s.(f)(known))) || any(~isnan(s.(f)(~known))), r{end+1}='nonfinite_or_partial'; end
end
for i=find(known)
    if ~isfinite(s.choice(i)) || s.choice(i)~=fix(s.choice(i)) || s.choice(i)<1 || s.choice(i)>size(c.options{i},1)
        r{end+1}='mode_support'; continue;
    end
    m=c.options{i}(s.choice(i),:);
    if s.unit(i)~=m(1) || s.mode(i)~=m(2) || abs(s.duration(i)-m(3))>tol || abs(s.increment(i)-m(4))>1e-12
        r{end+1}='mode_response';
    end
    if s.duration(i)<=0 || s.increment(i)<0 || abs(s.finish(i)-s.start(i)-s.duration(i))>tol, r{end+1}='duration'; end
    req=c.request(i);
    if s.start(i)<c.release(req)-tol, r{end+1}='release'; end
    if s.start(i)<-tol || s.finish(i)>c.window+tol, r{end+1}='window'; end
    if s.finish(i)>c.deadline(req)+tol, r{end+1}='deadline'; end
    if abs(s.start(i)-round(s.start(i)/c.grid)*c.grid)>tol, r{end+1}='grid'; end
    pr=c.pred{i};
    if any(~known(pr)) || any(s.start(i)<s.finish(pr)-tol), r{end+1}='precedence'; end
end
for i=find(known)
    for j=find(known & (1:n)>i)
        if min(s.finish([i j]))-max(s.start([i j]))<=tol, continue; end
        if s.unit(i)==s.unit(j), r{end+1}='unit_overlap'; end
        u=s.unit([i j]);
        if all(isfinite(u)) && all(u==fix(u)) && all(u>=1 & u<=numel(c.unit_kind))
            if all(c.unit_kind(u)==1) && c.domain(u(1))==c.domain(u(2)) && s.mode(i)~=s.mode(j)
                r{end+1}='domain_conflict';
            end
        else, r{end+1}='unit_support'; end
    end
end
v=struct('feasible',isempty(r),'reason',strjoin(unique(r),';'),'completion',s.finish(c.terminal));
end
