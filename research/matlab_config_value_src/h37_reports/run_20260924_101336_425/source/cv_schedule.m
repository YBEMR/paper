function s = cv_schedule(c,model,modes,cpu_order,npu_order,lower)
% Longest paths for fixed resource orders; no time grid or rounding.
% Vector order: CPU_A, CPU_B, NPU_A, NPU_B.
if nargin<6, lower=zeros(1,4); end
[d,Q]=cv_response(c,model);
s=struct('modes',modes,'cpu_order',cpu_order,'npu_order',npu_order, ...
    'start',zeros(1,4),'finish',zeros(1,4),'duration',zeros(1,4), ...
    'increment',zeros(1,4),'model',model);
for i=1:2
    s.duration(i)=d(i,modes(i)); s.increment(i)=Q(i,modes(i));
end
s.duration(3:4)=c.n; s.increment(3:4)=c.w;
available=0;
for i=cpu_order
    s.start(i)=max([available c.release(i) lower(i)]);
    s.finish(i)=s.start(i)+s.duration(i); available=s.finish(i);
end
available=0;
for i=npu_order
    j=i+2; s.start(j)=max([available s.finish(i) lower(j)]);
    s.finish(j)=s.start(j)+s.duration(j); available=s.finish(j);
end
end
