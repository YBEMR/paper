function [candidates,targets,contribution]=b64_repair(d,node,earliest,z,h)
% One independent single-stage delay from the ORIGINAL earliest arrangement.
s=b64_schedule(d,node.m,earliest);bad=find(z.peak_lower>h.limit+h.band);
if isempty(bad),bad=find(z.peak>h.limit+h.band);end
assert(~isempty(bad));keys=[z.peak_time(bad)' bad'];[~,ii]=sortrows(keys,[1 2]);nn=bad(ii(1));tt=z.peak_time(nn);
net=thv_build(h);contribution=zeros(1,d.n);
for i=1:d.n
 if s.start(i)>=tt,continue;end
 j=d.unit_kind(s.unit(i));p=zeros(2,1);p(j)=s.increment(i);
 en=min(s.finish(i),tt);q=thv_step(net,[0;0],p,en-s.start(i));
 q=thv_step(net,q.finish,[0;0],tt-en);contribution(i)=q.finish(nn);
end
[~,targets]=sortrows([-contribution' (1:d.n)'],[1 2]);targets=targets';candidates=cell(1,d.n);
for k=1:d.n
 lo=earliest;lo(targets(k))=lo(targets(k))+d.g;
 [ok,t]=b64_propagate(d,node,lo);if ok,candidates{k}=t;end
end
end
