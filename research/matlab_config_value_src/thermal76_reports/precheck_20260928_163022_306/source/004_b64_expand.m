function children=b64_expand(d,N)
% Exhaustive partition only. No heat, heuristic pruning or reference data.
children={};
if N.phase==1
 j=d.order(find(N.m(d.order)==0,1));
 if isempty(j)
  N.phase=2;N.pairs=b64_conflicts(d,N.m);children={N};return;
 end
 opts=d.options{j};[~,ord]=sortrows([d.en{j} d.dt{j} opts(:,1:2)],[1 2 3 4]);
 for z=ord'
  C=N;C.m(j)=z;children{end+1}=C; %#ok<AGROW>
 end
elseif N.phase==2
 reach=N.adj;for k=1:d.n,reach=reach | (reach(:,k)&reach(k,:));end
 while N.pos<=size(N.pairs,1)
  ij=N.pairs(N.pos,:);i=ij(1);j=ij(2);N.pos=N.pos+1;
  if reach(i,j) || reach(j,i),continue;end
  C=N;C.adj(i,j)=true;children{1}=C;C=N;C.adj(j,i)=true;children{2}=C;return;
 end
 N.phase=3;children={N};
else
 [ord,ok]=b64_topo(N.adj);assert(ok);i=ord(find(~isfinite(N.s(ord)),1));
 if isempty(i),return;end
 pr=find(N.adj(:,i));lo=d.a(d.request(i));
 for j=pr',lo=max(lo,N.s(j)+d.dt{j}(N.m(j)));end
 hi=min(d.dead(d.request(i)),d.w)-d.dt{i}(N.m(i));
 for t=d.g*ceil(lo/d.g):d.g:hi
  C=N;C.s(i)=t;children{end+1}=C; %#ok<AGROW>
 end
end
end
