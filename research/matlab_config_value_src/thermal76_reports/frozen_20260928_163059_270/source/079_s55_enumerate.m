function lib=s55_enumerate(c,b)
% Exhaustive topological VARIABLE assignment, not chronological execution.
n=c.n; mind=zeros(1,n); mine=zeros(1,n); tail=zeros(1,n);
for i=1:n, mind(i)=min(c.options{i}(:,3)); mine(i)=min(prod(c.options{i}(:,3:4),2)); end
for i=n:-1:1
    children=find(cellfun(@(p)any(p==i),c.pred));
    if ~isempty(children),tail(i)=max(mind(children)+tail(children));end
end
lib=struct('rows',zeros(0,2*n,'uint16'),'complete',false,'status','running','count',0, ...
    'visited',0,'lower_J',(c.idle_cpu+c.idle_npu+c.external)*c.window+sum(mine), ...
    'observed_upper_J',Inf,'message','','proof','');
choice=zeros(1,n); ticks=zeros(1,n); st=zeros(1,n); fin=zeros(1,n); units=zeros(1,n); modes=zeros(1,n);
dur=zeros(1,n); inc=zeros(1,n); chunkSize=4096; buf=zeros(chunkSize,2*n,'uint16'); used=0; chunks={};
try
    s55_budget(b,'enumerate');
    for i=1:n
        if isempty(c.pred{i}) && c.release(c.request(i))+mind(i)+tail(i)>c.deadline(c.request(i))+c.time_tol
            lib.complete=true;lib.status='complete';lib.proof='isolated_chain_lower_bound';return;
        end
    end
    visit(1); s55_budget(b,'enumerate');
    lib.complete=true;lib.status='complete';
catch err
    if strcmp(err.identifier,'s55:timeout'),lib.status='timeout';
    elseif contains(lower(err.identifier),'nomem') || contains(lower(err.message),'out of memory'),lib.status='resource_unresolved';
    else,rethrow(err);end
    lib.message=err.message;
end
if used>0,chunks{end+1}=buf(1:used,:);end
% A timed-out partial collection is diagnostic only, never an exact library.
if ~isempty(chunks),lib.rows=vertcat(chunks{:});end
lib.count=size(lib.rows,1);
if lib.complete
    try,s55_budget(b,'enumerate');catch err,lib.complete=false;lib.status='timeout';lib.message=err.message;end
end
    function visit(i)
        s55_budget(b,'enumerate');
        if i>n
            s=struct('choice',choice,'unit',units,'mode',modes,'start',st,'finish',fin,'duration',dur,'increment',inc);
            v=s55_validate(c,s);assert(v.feasible,['Enumerator emitted illegal leaf: ' v.reason]);
            energy=(c.idle_cpu+c.idle_npu+c.external)*c.window+sum(dur.*inc);
            lib.observed_upper_J=min(lib.observed_upper_J,energy);
            used=used+1;buf(used,:) = uint16([choice ticks]);
            if used==chunkSize,chunks{end+1}=buf;buf=zeros(chunkSize,2*n,'uint16');used=0;end %#ok<AGROW>
            return;
        end
        req=c.request(i); lo=c.release(req);
        if ~isempty(c.pred{i}),lo=max(lo,max(fin(c.pred{i})));end
        klo=max(0,ceil((lo-c.time_tol)/c.grid)); opts=c.options{i};
        for m=1:size(opts,1)
            u=opts(m,1);f=opts(m,2);d=opts(m,3);
            khi=floor((min(c.deadline(req),c.window)-d-tail(i)+c.time_tol)/c.grid);
            for k=klo:khi
                lib.visited=lib.visited+1;s55_budget(b,'enumerate');
                t=k*c.grid; finish=t+d; valid=true;
                for j=1:i-1
                    if min(finish,fin(j))-max(t,st(j))<=c.time_tol,continue;end
                    if u==units(j) || (c.unit_kind(u)==1 && c.unit_kind(units(j))==1 && c.domain(u)==c.domain(units(j)) && f~=modes(j))
                        valid=false;break;
                    end
                end
                if ~valid,continue;end
                assert(k<=intmax('uint16') && m<=intmax('uint16'),'Compact row capacity exceeded');
                choice(i)=m;ticks(i)=k;st(i)=t;fin(i)=finish;units(i)=u;modes(i)=f;dur(i)=d;inc(i)=opts(m,4);
                visit(i+1);
            end
        end
    end
end
