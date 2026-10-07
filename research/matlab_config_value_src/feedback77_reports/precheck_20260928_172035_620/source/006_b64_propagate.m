function [ok,s,finish,order]=b64_propagate(d,node,lower)
% Fixed starts are equalities. Unassigned stages use an optimistic duration.
if nargin<3,lower=zeros(1,d.n);end
[order,ok]=b64_topo(node.adj);s=nan(1,d.n);finish=s;if ~ok,return;end
for i=order
 dur=d.minD(i);if node.m(i)>0,dur=d.dt{i}(node.m(i));end
 req=d.request(i);lo=max(d.a(req),lower(i));pr=find(node.adj(:,i));
 if ~isempty(pr),lo=max(lo,max(finish(pr)));end
 t=d.g*ceil(lo/d.g);
 if isfinite(node.s(i))
  if node.s(i)<t,ok=false;return;end
  t=node.s(i);
 end
 s(i)=t;finish(i)=t+dur;
 if finish(i)>min(d.dead(req),d.w),ok=false;return;end
end
end
