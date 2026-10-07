function out = thv_evaluate(c,s,h,net)
if nargin<4, net=thv_build(h); end
assert(all(isfinite(h.initial)) && all(h.initial<=h.limit));
valid=cv_validate(c,s); assert(valid.feasible,'Thermal evaluation requires a legal full schedule');
events=unique([0 c.window s.start s.finish]);
theta=h.initial(:)-h.ambient; peaks=theta; at=zeros(2,1);
state=zeros(numel(events),2); state(1,:)=theta';
segments=cell(1,numel(events)-1);
for k=1:numel(events)-1
    mid=(events(k)+events(k+1))/2;
    active=s.start<=mid & mid<s.finish;
    p=[c.idle_cpu+sum(s.increment(1:2).*active(1:2)); ...
       c.idle_npu+sum(s.increment(3:4).*active(3:4))];
    z=thv_step(net,theta,p,events(k+1)-events(k));
    hit=z.peak>peaks; peaks(hit)=z.peak(hit); at(hit)=events(k)+z.peak_time(hit);
    theta=z.finish; state(k+1,:)=theta'; segments{k}=z;
end
peak=peaks'+h.ambient;
if any(peak>h.limit+h.band), status='violation';
elseif all(peak<h.limit-h.band), status='safe';
else, status='unresolved'; end
out=struct('status',status,'peak',peak,'peak_time',at', ...
    'terminal',theta'+h.ambient,'event_time',events,'event_temperature',state+h.ambient, ...
    'segments',{segments});
end
