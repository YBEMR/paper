function out = thv_search(trial)
% Finite-grid reference. Earliest/common-shift probes only change search order.
c=trial.case; h=trial.thermal; clock=tic; net=thv_build(h);
ref=cv_reference(c,'task',clock);
earliest=struct('index',{},'modes',{},'schedule',{},'evaluation',{});
for j=1:numel(ref.rows)
    row=ref.rows(j);
    if row.validation.feasible
        earliest(end+1)=struct('index',j,'modes',row.schedule.modes, ...
            'schedule',row.schedule,'evaluation',thv_evaluate(c,row.schedule,h,net));
    end
end
modes=struct('mode',{},'energy',{},'status',{},'reason',{},'evaluated',{}, ...
    'unresolved_count',{},'witness',{},'evaluation',{},'witness_kind',{},'earliest_safe',{});
for a=1:2
    for b=1:2
        m=[a b]; found=[]; evaluation=[]; count=0; uncertain=0; timed=false;
        kind=''; earlysafe=0;
        seeds=earliest(arrayfun(@(x)isequal(x.modes,m),earliest));
        s0=cv_schedule(c,'task',m,[1 2],[1 2]); en=cv_energy(c,s0);
        for z=seeds
            count=count+1;
            if strcmp(z.evaluation.status,'safe')
                earlysafe=earlysafe+1;
                if isempty(found), found=z.schedule; evaluation=z.evaluation; kind='earliest'; end
            elseif strcmp(z.evaluation.status,'unresolved'), uncertain=uncertain+1; end
        end
        if isempty(seeds)
            status='grid_infeasible'; reason='resource_deadline_no_schedule';
        else
            if isempty(found)
                % Same shift for all stages: legal voluntary waiting, no future reservation.
                for shift=h.grid:h.grid:c.window
                    if ~isempty(found) || timed, break; end
                    for z=seeds
                        s=z.schedule; s.start=s.start+shift; s.finish=s.finish+shift;
                        v=cv_validate(c,s);
                        if v.feasible, probe(s,'common_shift'); end
                        if ~isempty(found) || timed, break; end
                    end
                end
            end
            if isempty(found) && ~timed
                % Full enumeration: CPU order first, then independent NPU order.
                % Bounds only use release, precedence, resource capacity, deadlines.
                for oc=[1 2;2 1]'
                    if ~isempty(found) || timed, break; end
                    cpu=oc'; i=cpu(1); j=cpu(2);
                    for on=[1 2;2 1]'
                        if ~isempty(found) || timed, break; end
                        npu=on'; u=npu(1); v=npu(2);
                        s=cv_schedule(c,'task',m,cpu,npu);
                        for ti=ticks(c.release(i),c.deadline(i)-s.duration(i)-c.n(i))
                            if ~isempty(found) || timed, break; end
                            for tj=ticks(max(c.release(j),ti*h.grid+s.duration(i)),c.deadline(j)-s.duration(j)-c.n(j))
                                if ~isempty(found) || timed, break; end
                                s.start(i)=ti*h.grid; s.start(j)=tj*h.grid;
                                s.finish(1:2)=s.start(1:2)+s.duration(1:2);
                                for tu=ticks(s.finish(u),c.deadline(u)-c.n(u))
                                    if ~isempty(found) || timed, break; end
                                    for tv=ticks(max(s.finish(v),tu*h.grid+c.n(u)),c.deadline(v)-c.n(v))
                                        s.start(u+2)=tu*h.grid; s.start(v+2)=tv*h.grid;
                                        s.finish(3:4)=s.start(3:4)+s.duration(3:4);
                                        probe(s,'full_grid');
                                        if ~isempty(found) || timed, break; end
                                    end
                                    if toc(clock)>h.budget_s, timed=true; end
                                end
                                if toc(clock)>h.budget_s, timed=true; end
                            end
                            if toc(clock)>h.budget_s, timed=true; end
                        end
                    end
                end
            end
            if ~isempty(found), status='feasible'; reason='continuous_peak_checked_witness';
            elseif timed, status='timeout'; reason='case_budget_not_infeasibility';
            elseif uncertain>0, status='unresolved'; reason='threshold_band_candidate';
            else, status='grid_infeasible'; reason='all_legal_grid_schedules_unsafe'; end
        end
        modes(end+1)=struct('mode',m,'energy',en.integral,'status',status,'reason',reason, ...
            'evaluated',count,'unresolved_count',uncertain,'witness',found, ...
            'evaluation',evaluation,'witness_kind',kind,'earliest_safe',earlysafe);
    end
end
safe=strcmp({modes.status},'feasible'); best=inf; opts=[];
if any(safe)
    best=min([modes(safe).energy]); tol=max(c.energy_abs_tol,c.energy_rel_tol*best);
    opts=find(safe & abs([modes.energy]-best)<=tol);
end
resolved=all(ismember({modes.status},{'feasible','grid_infeasible'}));
recovered=isfinite(best) && abs(best-ref.best)<=max(c.energy_abs_tol,c.energy_rel_tol*ref.best);
out=struct('reference',ref,'earliest',earliest,'modes',modes,'best_found',best, ...
    'optimal_mode_indices',opts,'all_modes_resolved',resolved,'recovered_lower_bound',recovered, ...
    'elapsed_s',toc(clock),'status','completed');
    function ts=ticks(lo,hi)
        ts=ceil((lo-c.time_tol)/h.grid):floor((hi+c.time_tol)/h.grid);
    end
    function probe(s,label)
        if toc(clock)>h.budget_s, timed=true; return; end
        z=thv_evaluate(c,s,h,net); count=count+1;
        if strcmp(z.status,'safe'), found=s; evaluation=z; kind=label;
        elseif strcmp(z.status,'unresolved'), uncertain=uncertain+1; end
    end
end
