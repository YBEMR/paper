function out=p47_reference(tr,policy)
% Exhaustive thermal classification in increasing energy order, same domain.
% Prefix diagnoses reuse only evaluations made within this reference budget.
c=tr.case; h=tr.thermal; timer=tic;
out=struct('status','running','rows',zeros(0,8),'energy',[],'thermal_state',[], ...
    'peaks',zeros(0,2),'noheat_energy',nan,'noheat_modes',[], ...
    'lower_J',nan,'upper_J',inf,'energy_exact',false,'optimal_modes',[], ...
    'mode_set_complete',false,'evaluated',0,'prefixes',{{}},'first_loss_time',nan, ...
    'prefix_status','not_started','elapsed_s',0,'message','');
try
    lib=c44_library(c,timer); out.rows=lib.rows; out.energy=lib.energy;
    N=lib.count; out.thermal_state=zeros(N,1); out.peaks=nan(N,2); net=thv_build(h);
    if N==0, out.status='noheat_infeasible'; out.lower_J=inf; out.elapsed_s=toc(timer); return; end
    out.noheat_energy=min(lib.energy);
    out.noheat_modes=unique(lib.mode_id(abs(lib.energy-out.noheat_energy)<=tol(out.noheat_energy)))';
    % For the frozen pair all no-heat schedules belong to HH, a single layer.
    % Enumerate the entire finite library to certify each committed prefix.
    for k=1:N
        budget(); z=c44_thermal(c,c44_schedule(c,lib.rows(k,:)),h,net);
        out.evaluated=out.evaluated+1; out.peaks(k,:)=z.peak;
        if strcmp(z.status,'safe'), out.thermal_state(k)=1;
        elseif strcmp(z.status,'violation'), out.thermal_state(k)=2;
        else, out.thermal_state(k)=3; end
    end
    budget(); out.status='complete';
catch err
    if strcmp(err.identifier,'c44:timeout'), out.status='timeout'; else, out.status='error'; end
    out.message=getReport(err,'extended','hyperlinks','off');
end
if ~isempty(out.rows)
    safe=out.thermal_state==1; possible=out.thermal_state~=2;
    if any(safe), out.upper_J=min(out.energy(safe)); end
    if any(possible), out.lower_J=min(out.energy(possible)); else, out.lower_J=inf; end
    out.energy_exact=isfinite(out.upper_J) && abs(out.upper_J-out.lower_J)<=tol(out.upper_J);
    if out.energy_exact
        layer=abs(out.energy-out.upper_J)<=tol(out.upper_J);
        ids=2*(out.rows(:,1)-1)+out.rows(:,2);
        out.optimal_modes=unique(ids(safe & layer))';
        out.mode_set_complete=all(ismember(out.thermal_state(layer),[1 2]));
    end
    if all(out.thermal_state==2), out.status='grid_thermal_infeasible'; end
    out.prefix_status='complete';
    for ev=policy.events
        if ev.selected==0, continue; end
        if toc(timer)>c.budget_s, out.prefix_status='budget_unresolved'; break; end
        keep=c44_prefix(c,out.rows,ev.prefix,ev.time,true);
        states=out.thermal_state(keep);
        status='unresolved';
        if isempty(states), status='no_noheat_continuation';
        elseif any(states==1), status='safe_continuation_exists';
        elseif all(states==2), status='all_thermal_continuations_excluded'; end
        rec=struct('time',ev.time,'prefix',ev.prefix,'eligible_rows',find(keep)', ...
            'count',sum(keep),'safe',sum(states==1),'violation',sum(states==2), ...
            'unresolved',sum(states==3),'unchecked',sum(states==0),'status',status);
        out.prefixes{end+1}=rec;
        if strcmp(status,'all_thermal_continuations_excluded') && isnan(out.first_loss_time), out.first_loss_time=ev.time; end
    end
end
out.elapsed_s=toc(timer);
    function v=tol(e), v=max(c.energy_abs_tol,c.energy_rel_tol*abs(e)); end
    function budget()
        if toc(timer)>c.budget_s, error('c44:timeout','Reference and prefix budget exceeded'); end
    end
end
