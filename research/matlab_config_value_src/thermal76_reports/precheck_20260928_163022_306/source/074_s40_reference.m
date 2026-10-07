function out=s40_reference(c,h,clock)
% Exact no-heat reference on the declared start grid; durations not rounded.
if nargin<3, clock=tic; end
orders=[1 2;2 1]; rows=struct([]);
for a=1:2
    for b=1:2
        for oc=1:2
            for on=1:2
                if toc(clock)>h.budget_s, error('s40:timeout','Reference budget'); end
                s=cv_schedule(c,'task',[a b],orders(oc,:),orders(on,:));
                free=0;
                for i=orders(oc,:)
                    s.start(i)=ceil((max(free,c.release(i))-c.time_tol)/h.grid)*h.grid;
                    s.finish(i)=s.start(i)+s.duration(i); free=s.finish(i);
                end
                free=0;
                for i=orders(on,:)
                    z=i+2; s.start(z)=ceil((max(free,s.finish(i))-c.time_tol)/h.grid)*h.grid;
                    s.finish(z)=s.start(z)+s.duration(z); free=s.finish(z);
                end
                v=cv_validate(c,s);
                energy=(c.idle_cpu+c.idle_npu+c.external)*c.window+sum(s.duration.*s.increment);
                rows=s40_append(rows,struct('schedule',s,'validation',v,'energy',energy));
            end
        end
    end
end
feasible=[rows.validation]; feasible=[feasible.feasible];
best=inf; idx=[];
if any(feasible)
    best=min([rows(feasible).energy]);
    idx=find(feasible & abs([rows.energy]-best)<=max(c.energy_abs_tol,c.energy_rel_tol*abs(best)));
end
out=struct('rows',rows,'best',best,'optimal_indices',idx,'grid',h.grid);
end
