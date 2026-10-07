function out = cv_compare(c,clock)
if nargin<2, clock=tic; end
if strcmp(c.family,'N1')
    rows=struct('schedule',{},'validation',{},'energy',{});
    for m=1:2
        s=cv_schedule(c,'task',[m 2],[2 1],[2 1],[.006 0 0 .006]);
        rows(m)=struct('schedule',s,'validation',cv_validate(c,s),'energy',cv_energy(c,s));
    end
    out=struct('kind','fixed_suffix','rows',rows,'status','complete'); return;
end
simple=cv_reference(c,'simple',clock); task=cv_reference(c,'task',clock);
replay=cell(1,2); refs={simple,task};
for k=1:2
    p=refs{k}; records=struct('source_index',{},'original',{},'raw_common',{}, ...
        'raw_validation',{},'replayed',{},'validation',{},'energy',{},'delay',{});
    for index=p.optimal_indices
        if toc(clock)>c.budget_s, error('cv:timeout','Case budget exceeded'); end
        old=p.rows(index).schedule;
        % Original start times retained; finish times replaced by common durations.
        actual=cv_schedule(c,'task',old.modes,old.cpu_order,old.npu_order);
        raw=actual; raw.start=old.start; raw.finish=raw.start+raw.duration;
        played=cv_schedule(c,'task',old.modes,old.cpu_order,old.npu_order,old.start);
        records(end+1)=struct('source_index',index,'original',old, ...
            'raw_common',raw,'raw_validation',cv_validate(c,raw), ...
            'replayed',played,'validation',cv_validate(c,played), ...
            'energy',cv_energy(c,played),'delay',played.start-old.start);
    end
    replay{k}=records;
end
[d,Q]=cv_response(c,'task'); local=cell(1,2);
conditional=inf(2,2);
for i=1:2
    ok=c.release(i)+d(i,:)+c.n(i)<=c.deadline(i)+c.time_tol;
    cost=Q(i,:).*d(i,:); candidates=find(ok);
    if isempty(candidates), local{i}=[];
    else
        best=min(cost(ok)); tol=max(c.energy_abs_tol,c.energy_rel_tol*abs(best));
        local{i}=find(ok & abs(cost-best)<=tol);
    end
    for m=1:2
        for row=task.rows
            if row.validation.feasible && row.schedule.modes(i)==m
                conditional(i,m)=min(conditional(i,m),row.energy.integral);
            end
        end
    end
end
merge=struct('modes',{},'feasible',{},'best',{});
for a=local{1}
    for b=local{2}
        ok=false; best=inf;
        for row=task.rows
            if isequal(row.schedule.modes,[a b]) && row.validation.feasible
                ok=true; best=min(best,row.energy.integral);
            end
        end
        merge(end+1)=struct('modes',[a b],'feasible',ok,'best',best);
    end
end
out=struct('kind','global','simple',simple,'task',task, ...
    'simple_replay',replay{1},'task_replay',replay{2},'local_modes',{local}, ...
    'conditional_energy',conditional,'local_merge',merge,'status','complete');
end
