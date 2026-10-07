function lib=s55_sort(c,lib,b)
assert(lib.complete,'Partial library cannot be sorted into exact representatives');s55_budget(b,'sort');
N=lib.count;n=c.n;E=repmat((c.idle_cpu+c.idle_npu+c.external)*c.window,N,1);
finish=zeros(N,n); canonical=zeros(N,3*n);
for i=1:n
    opts=c.options{i};mi=double(lib.rows(:,i));k=double(lib.rows(:,n+i));
    E=E+opts(mi,3).*opts(mi,4);finish(:,i)=k*c.grid+opts(mi,3);
    canonical(:,3*i-2:3*i)=[k*c.grid opts(mi,1:2)];s55_budget(b,'sort');
end
ranks=zeros(N,1);[se,ix]=sort(E);rank=0;anchor=NaN;
for j=1:N
    if mod(j,2048)==1,s55_budget(b,'sort');end
    if j==1 || abs(se(j)-anchor)>max(c.energy_abs_tol,c.energy_rel_tol*max(abs([se(j) anchor])))
        rank=rank+1;anchor=se(j);
    end
    ranks(ix(j))=rank;
end
C=finish(:,c.terminal);key=[ranks sum(C,2) max(C,[],2) canonical];
s55_budget(b,'sort');[~,ix]=sortrows(key);s55_budget(b,'sort');
lib.rows=lib.rows(ix,:);lib.energy=E(ix);lib.rank=ranks(ix);lib.completion=C(ix,:);
lib.sort_complete=true;
end
