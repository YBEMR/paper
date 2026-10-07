function lib=c44_library(c,timer)
% Complete finite-domain enumeration. No thermal input or reference files.
if nargin<2, timer=tic; end
[d,q]=cv_response(c,'task'); chunks={}; energies=zeros(4,1); steps=0;
for a=1:2
    for b=1:2
        m=2*(a-1)+b; dur=[d(1,a) d(2,b)];
        energies(m)=(c.idle_cpu+c.idle_npu+c.external)*c.window+sum([q(1,a) q(2,b)].*dur)+sum(c.npu_increment.*c.n);
        lo=ceil((c.release-c.time_tol)/c.grid);
        hi=floor((min(c.deadline,c.window)-c.n-dur+c.time_tol)/c.grid);
        for ua=1:2
            for ub=1:2
                for ka=lo(1):hi(1)
                    for kb=lo(2):hi(2)
                        steps=steps+1; if mod(steps,32)==1, budget(); end
                        st=[ka kb]*c.grid; fin=st+dur;
                        ov=min(fin)-max(st)>c.time_tol;
                        if ov && (ua==ub || (c.domain(ua)==c.domain(ub) && a~=b)), continue; end
                        nl=ceil((fin-c.time_tol)/c.grid); nh=floor((min(c.deadline,c.window)-c.n+c.time_tol)/c.grid);
                        [na,nb]=ndgrid(nl(1):nh(1),nl(2):nh(2));
                        ns=[na(:) nb(:)]*c.grid;
                        if isempty(ns), continue; end
                        keep=min(ns+c.n,[],2)-max(ns,[],2)<=c.time_tol;
                        ns=ns(keep,:); n=size(ns,1);
                        if n>0, chunks{end+1}=[repmat([a b ua ub st],n,1) ns]; end %#ok<AGROW>
                    end
                end
            end
        end
    end
end
budget();
if isempty(chunks), rows=zeros(0,8); else, rows=vertcat(chunks{:}); end
ids=2*(rows(:,1)-1)+rows(:,2); E=energies(ids);
% Energy comparison uses fixed layers, avoiding floating-point tie artefacts.
[sorted,ord]=sort(energies); ranks=zeros(4,1); rank=1; anchor=sorted(1);
for j=1:4
    if abs(sorted(j)-anchor)>max(c.energy_abs_tol,c.energy_rel_tol*max(abs([sorted(j) anchor])))
        rank=rank+1; anchor=sorted(j);
    end
    ranks(ord(j))=rank;
end
C=rows(:,7:8)+c.n; n=size(rows,1);
key=[ranks(ids) sum(C,2) max(C,[],2) rows(:,5) rows(:,3) rows(:,1) ...
    rows(:,6) rows(:,4) rows(:,2) rows(:,7) 3*ones(n,1) zeros(n,1) rows(:,8) 3*ones(n,1) zeros(n,1)];
[~,ix]=sortrows(key); rows=rows(ix,:); E=E(ix); ids=ids(ix);
budget();
lib=struct('rows',rows,'energy',E,'mode_id',ids,'mode_energy',energies, ...
    'mode_rank',ranks,'count',size(rows,1),'complete',true);
    function budget()
        if toc(timer)>c.budget_s, error('c44:timeout','Finite-domain enumeration budget exceeded'); end
    end
end
