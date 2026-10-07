function out = cv_reference(c,model,clock)
% Complete 4 modes x 2 CPU orders x 2 NPU orders, without thermal limits.
if nargin<3, clock=tic; end
orders=[1 2;2 1]; rows=struct([]); j=0;
for a=1:2
    for b=1:2
        for oc=1:2
            for on=1:2
                if toc(clock)>c.budget_s, error('cv:timeout','Case budget exceeded'); end
                s=cv_schedule(c,model,[a b],orders(oc,:),orders(on,:));
                v=cv_validate(c,s); e=cv_energy(c,s);
                j=j+1; rows(j)=struct('schedule',s,'validation',v,'energy',e);
            end
        end
    end
end
feasible=arrayfun(@(z)z.validation.feasible,rows);
energies=arrayfun(@(z)z.energy.integral,rows);
best=inf; opt=[];
if any(feasible)
    best=min(energies(feasible));
    tol=max(c.energy_abs_tol,c.energy_rel_tol*abs(best));
    opt=find(feasible & abs(energies-best)<=tol);
end
out=struct('model',model,'rows',rows,'best',best,'optimal_indices',opt, ...
    'status','complete','thermal','not_evaluated');
end
