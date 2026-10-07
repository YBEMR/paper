function checks=h37_tests(here,trials,runs,diagnostics,reference)
rows=struct('name',{},'passed',{},'detail',{});
add('main_trial_version_count',numel(runs)==2*numel(trials),'15 inputs, two versions; no research outcome assertion');
for k=1:numel(runs)
    r=runs(k); t=trials(r.trial); c=t.case; h=t.thermal;
    label=[t.id '_' r.version];
    add([label '_execution_no_error'],strcmp(r.status,'completed'),'Policy failure/timeout remains a research outcome, not physical infeasibility');
    expected=[]; ref=reference{r.trial}.reference;
    for j=ref.optimal_indices, expected(end+1,:)=ref.rows(j).schedule.modes; end
    actual=reshape([r.configs.modes],2,[])';
    add([label '_all_optimal_configs'],isequal(sortrows(actual),unique(expected,'rows')),'Adapter recomputed configurations; history only in post-evaluation');
    add([label '_adapter_no_timings'],isequal(fieldnames(r.configs),{'modes';'duration';'increment'}),'No reference order/start/lower-bound fields');
    for j=1:numel(r.outputs)
        o=r.outputs{j}; s=o.schedule;
        starts=o.events(strcmp({o.events.kind},'start'));
        add([label '_one_commit_per_stage'],numel(unique([starts.stage]))==numel(starts),'Started stages never changed');
        add([label '_grid'],all(abs(s.start(isfinite(s.start))/h.grid-round(s.start(isfinite(s.start))/h.grid))*h.grid<=c.time_tol),'Durations not quantized');
        add([label '_fixed_modes_response'],isequal(s.duration,r.configs(j).duration) && isequal(s.increment,r.configs(j).increment),'Execution characteristics unchanged');
        if strcmp(o.status,'completed')
            p=h37_partial(c,s,h); full=thv_evaluate(c,s,h);
            add([label '_full_partial_agree'],max(abs([p.peak-full.peak p.terminal-full.terminal]))<1e-9,'Same event power/continuous peaks, including idle tail');
            v=cv_validate(c,s); en=cv_energy(c,s);
            add([label '_legality_energy'],v.feasible && en.difference<=max(c.energy_abs_tol,c.energy_rel_tol*en.integral),'Release/resource/dependency/deadline/window and independent energy sum');
        else
            add([label '_incomplete_not_scored'],isempty(o.energy) && isempty(o.thermal),'No partial energy rankings');
        end
        if strcmp(r.version,'P0')
            disabled=h37_policy(c,h,r.configs(j),'P1',tic,false);
            add([label '_filter_off_identical'],isequaln(disabled.schedule,s) && strcmp(disabled.status,o.status),'Same ranking and actions when filter disabled');
        end
    end
end
% Analytical single-stage trajectory: independently concatenate active + idle.
t=trials(1); c=t.case; h=t.thermal; config=runs(1).configs(1);
s=struct('duration',config.duration,'increment',config.increment, ...
    'start',[0 NaN NaN NaN],'finish',[config.duration(1) NaN NaN NaN]);
net=thv_build(h); z1=thv_step(net,h.initial(:)-h.ambient, ...
    [c.idle_cpu+config.increment(1);c.idle_npu],s.finish(1));
z2=thv_step(net,z1.finish,[c.idle_cpu;c.idle_npu],c.window-s.finish(1));
p=h37_partial(c,s,h);
expected=max(z1.peak,z2.peak)'+h.ambient;
add('partial_running_stage_full_remaining',max(abs(p.peak-expected))<1e-9,'Committed stage runs through finish, then idle; external baseline not injected');
hband=h; hband.limit=p.peak;
add('threshold_band_unresolved',strcmp(h37_partial(c,s,hband).status,'unresolved'),'Evaluator boundary fixture only; no research parameters modified');
hbudget=h; hbudget.budget_s=-1;
timeout=h37_policy(c,hbudget,config,'P1',tic);
add('timeout_not_infeasible',strcmp(timeout.status,'timeout') && isempty(timeout.energy),'Control-flow fixture only');
% Original 35 alpha=.6 tie: do not manufacture a new research instance.
cases=cv_cases(); tied=cases(strcmp({cases.id},'R1_alpha_06')); cfg=h37_config(tied,tic);
add('original_R1_threshold_keeps_both_modes',numel(cfg)==2,'35 existing threshold tie');
a=h37_policy(tied,h,cfg(1),'P0',tic); b=h37_policy(tied,h,cfg(1),'P0',tic);
add('deterministic_tie_actions',isequaln(a.schedule,b.schedule) && isequaln(a.events,b.events),'Repeats only software determinism check');
% Software-only equal-priority fixture, and non-grid execution finish.
ce=c; ce.release=[0 0]; ce.deadline=[40 40]*1e-3;
equal=struct('modes',[1 1],'duration',[.0043 .0043 .002 .002],'increment',[.1 .1 1 1]);
eq=h37_policy(ce,h,equal,'P0',tic); ev=eq.events(strcmp({eq.events.kind},'start'));
add('equal_slack_request_id_tie',ev(1).stage==1,'Equal deadline/arrival/remaining time -> A');
add('non_grid_finish_not_rounded',abs(eq.schedule.finish(1)-.0043)<1e-12 && abs(eq.schedule.start(2)-.005)<1e-12,'Exact 4.3 ms finish, next legal grid dispatch; software fixture only');
% Diagnostics reuse existing HH hot g=0. Verify actual branch coverage.
covered_wait=false; covered_other=false;
for d=diagnostics
    if ~strcmp(d.version,'P1'), continue; end
    o=d.output; e=o.events; rej=find(strcmp({e.kind},'reject'));
    for j=rej
        later=e(j+1:end);
        covered_other=covered_other || any(strcmp({later.kind},'start') & abs([later.time_s]-e(j).time_s)<1e-12 & [later.stage]~=e(j).stage);
        covered_wait=covered_wait || any(strcmp({later.kind},'start') & [later.time_s]>e(j).time_s+1e-12 & [later.stage]==e(j).stage);
    end
end
add('HH_reject_then_other_device_runs',covered_other,'No global freeze or future resource reservation');
add('HH_rejected_stage_later_starts',covered_wait,'Existing diagnostic, not an optimal-energy gain');
% Static information boundary and historical source integrity.
policy=fileread(fullfile(here,'h37_policy.m')); adapter=fileread(fullfile(here,'h37_config.m'));
add('policy_no_oracle_io',isempty(regexp(policy,'\<(load|readtable|fileread|thv_search|cv_reference)\>','once')),'No historical I/O or reference solver inside dispatcher');
add('adapter_no_thermal_reference',isempty(regexp(adapter,'\<(load|readtable|thv_search)\>','once')),'No thermal answer selection');
for snap={'reports/run_20260923_170646_889','thermal_reports/run_20260923_204922_828'}
    files=dir(fullfile(here,snap{1},'source','*.m')); same=true;
    for f=files'
        same=same && strcmp(fileread(fullfile(f.folder,f.name)),fileread(fullfile(here,f.name)));
    end
    add(['historical_source_' snap{1}],same,sprintf('%d historical .m files identical',numel(files)));
end
checks=struct2table(rows);
    function add(name,passed,detail)
        rows(end+1)=struct('name',name,'passed',logical(passed),'detail',detail);
    end
end
