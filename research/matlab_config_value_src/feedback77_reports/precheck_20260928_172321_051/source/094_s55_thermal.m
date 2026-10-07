function out=s55_thermal(c,s,h,net,b)
if nargin<4 || isempty(net), net=thv_build(h); end
if nargin<5, b=struct('timer',tic,'limit',Inf); end
s55_budget(b,'thermal'); v=s55_validate(c,s,true); assert(v.feasible,v.reason);
known=isfinite(s.start); ev=unique([0 c.window s.start(known) s.finish(known)]);
theta=h.initial(:)-h.ambient; peak=theta; at=zeros(2,1);
states=zeros(numel(ev),2); states(1,:)=theta'; segments=cell(1,numel(ev)-1);
for k=1:numel(ev)-1
    s55_budget(b,'thermal'); mid=(ev(k)+ev(k+1))/2;
    ix=find(known & s.start<=mid & mid<s.finish); kinds=c.unit_kind(s.unit(ix));
    p=[c.idle_cpu+sum(s.increment(ix(kinds==1))); c.idle_npu+sum(s.increment(ix(kinds==2)))];
    z=thv_step(net,theta,p,ev(k+1)-ev(k)); s55_budget(b,'thermal');
    hit=z.peak>peak; peak(hit)=z.peak(hit); at(hit)=ev(k)+z.peak_time(hit);
    theta=z.finish; states(k+1,:)=theta'; segments{k}=z;
end
temp=peak'+h.ambient;
if any(temp>h.limit+h.band), verdict='violation';
elseif all(temp<h.limit-h.band), verdict='safe'; else, verdict='unresolved'; end
out=struct('status',verdict,'peak',temp,'peak_time',at','terminal',theta'+h.ambient, ...
    'event_time',ev,'event_temperature',states+h.ambient,'segments',{segments}, ...
    'scope',ternary(all(known),'complete','committed_only'));
s55_budget(b,'thermal');
end
function x=ternary(q,a,b), if q,x=a;else,x=b;end,end
