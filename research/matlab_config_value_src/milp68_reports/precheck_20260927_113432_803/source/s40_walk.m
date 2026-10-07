function out=s40_walk(c,h,m,visit,clock)
% Complete, deterministic start-grid enumeration. Callback true stops.
orders=[1 2;2 1]; count=0; status='exhausted';
for oc=1:2
    cpu=orders(oc,:); i=cpu(1); j=cpu(2);
    for on=1:2
        npu=orders(on,:); u=npu(1); v=npu(2);
        s=cv_schedule(c,'task',m,cpu,npu);
        for ti=ticks(c.release(i),min(c.deadline(i),c.window)-s.duration(i)-c.n(i))
            for tj=ticks(max(c.release(j),ti*h.grid+s.duration(i)),min(c.deadline(j),c.window)-s.duration(j)-c.n(j))
                s.start(i)=ti*h.grid; s.start(j)=tj*h.grid;
                s.finish(1:2)=s.start(1:2)+s.duration(1:2);
                for tu=ticks(s.finish(u),min(c.deadline(u),c.window)-c.n(u))
                    for tv=ticks(max(s.finish(v),tu*h.grid+c.n(u)),min(c.deadline(v),c.window)-c.n(v))
                        if toc(clock)>h.budget_s, status='timeout'; out=finish(); return; end
                        s.start(u+2)=tu*h.grid; s.start(v+2)=tv*h.grid;
                        s.finish(3:4)=s.start(3:4)+c.n;
                        count=count+1;
                        if visit(s), status='stopped_by_evidence'; out=finish(); return; end
                    end
                end
                if toc(clock)>h.budget_s, status='timeout'; out=finish(); return; end
            end
        end
    end
end
out=finish();
    function a=ticks(lo,hi)
        a=ceil((lo-c.time_tol)/h.grid):floor((hi+c.time_tol)/h.grid);
    end
    function z=finish()
        z=struct('status',status,'count',count);
    end
end
