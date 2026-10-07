function out = h37_partial(c,s,h,net)
% Unstarted stages are NaN. All committed stages run to their actual ends.
if nargin<4, net=thv_build(h); end
known=isfinite(s.start); assert(isequal(known,isfinite(s.finish)));
assert(all(s.start(known)>=-c.time_tol) && all(s.finish(known)<=c.window+c.time_tol));
assert(all(abs(s.finish(known)-s.start(known)-s.duration(known))<=c.time_tol));
for i=find(known(3:4))
    assert(known(i) && s.start(i+2)>=s.finish(i)-c.time_tol);
end
for pair=[1 2;3 4]'
    if all(known(pair)), assert(min(s.finish(pair))-max(s.start(pair))<=c.time_tol); end
end
events=unique([0 c.window s.start(known) s.finish(known)]);
theta=h.initial(:)-h.ambient; peak=theta; at=zeros(2,1);
states=zeros(numel(events),2); states(1,:)=theta';
for k=1:numel(events)-1
    mid=(events(k)+events(k+1))/2;
    active=known & s.start<=mid & mid<s.finish;
    p=[c.idle_cpu+sum(s.increment(1:2).*active(1:2)); ...
       c.idle_npu+sum(s.increment(3:4).*active(3:4))];
    z=thv_step(net,theta,p,events(k+1)-events(k));
    hit=z.peak>peak; peak(hit)=z.peak(hit); at(hit)=events(k)+z.peak_time(hit);
    theta=z.finish; states(k+1,:)=theta';
end
peak=peak'+h.ambient;
if any(peak>h.limit+h.band), status='violation';
elseif all(peak<h.limit-h.band), status='safe';
else, status='unresolved'; end
out=struct('status',status,'peak',peak,'peak_time',at', ...
    'terminal',theta'+h.ambient,'event_time',events,'event_temperature',states+h.ambient);
end
