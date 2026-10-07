function out=c44_thermal(c,s,h,net)
% Partial/full schedules share the same injection and continuous peak engine.
if nargin<4, net=thv_build(h); end
v=c44_validate(c,s,true); assert(v.feasible,v.reason);
known=isfinite(s.start); events=unique([0 c.window s.start(known) s.finish(known)]);
theta=h.initial(:)-h.ambient; peaks=theta; at=zeros(2,1);
state=zeros(numel(events),2); state(1,:)=theta'; segments=cell(1,numel(events)-1);
for k=1:numel(events)-1
    mid=(events(k)+events(k+1))/2; active=known & s.start<=mid & mid<s.finish;
    cpu=find(active & [true true false false]); npu=find(active & [false false true true]);
    p=[c.idle_cpu+sum(s.increment(cpu));c.idle_npu+sum(s.increment(npu))];
    z=thv_step(net,theta,p,events(k+1)-events(k));
    hit=z.peak>peaks; peaks(hit)=z.peak(hit); at(hit)=events(k)+z.peak_time(hit);
    theta=z.finish; state(k+1,:)=theta'; segments{k}=z;
end
peak=peaks'+h.ambient;
if any(peak>h.limit+h.band), status='violation';
elseif all(peak<h.limit-h.band), status='safe'; else, status='unresolved'; end
out=struct('status',status,'peak',peak,'peak_time',at','terminal',theta'+h.ambient, ...
    'event_time',events,'event_temperature',state+h.ambient,'segments',{segments});
end
