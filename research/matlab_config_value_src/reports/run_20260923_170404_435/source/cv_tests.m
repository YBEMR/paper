function checks = cv_tests(cases,results)
names={}; passed=[]; detail={};
add('all_cases_complete',all(cellfun(@(x)strcmp(x.status,'complete'),results)), ...
    'All frozen cases finish within budget');
energy_error=0; legal=true;
for k=1:numel(cases)
    o=results{k};
    if ~strcmp(o.status,'complete'), continue; end
    if strcmp(o.kind,'global')
        refs={o.simple,o.task};
        for h=1:2
            for row=refs{h}.rows
                energy_error=max(energy_error,row.energy.difference);
            end
            for j=refs{h}.optimal_indices
                legal=legal && refs{h}.rows(j).validation.feasible;
            end
        end
    else
        for row=o.rows
            energy_error=max(energy_error,row.energy.difference);
            legal=legal && row.validation.feasible;
        end
    end
end
add('energy_integral_vs_sum',energy_error<1e-10,sprintf('max error %.17g J',energy_error));
add('optimal_and_fixed_schedules_legal',legal,'Precedence, resources, release, deadlines');
o=get('R1_alpha_02');
add('R1_strict_mode_change',strcmp(cv_mode_codes(o.simple),'HL') && ...
    strcmp(cv_mode_codes(o.task),'LL'),'Simple HL; task LL');
add('R1_common_replay_loss',all(arrayfun(@(z)z.energy.integral>o.task.best+1e-10, ...
    o.simple_replay)),'Compare common-model energies, not predictions');
o=get('R1_alpha_06');
add('R1_threshold_tie',strcmp(cv_mode_codes(o.task),'HL|LL'),'All optimal A modes retained');
add('R1_tie_no_replay_loss',all(arrayfun(@(z)abs(z.energy.integral-o.task.best)<1e-10, ...
    o.simple_replay)),'Different selected modes can still have equal energy');
o=get('R1_alpha_10');
same=strcmp(cv_mode_codes(o.simple),cv_mode_codes(o.task));
for j=1:16
    same=same && max(abs(o.simple.rows(j).schedule.finish-o.task.rows(j).schedule.finish))<1e-12;
end
add('alpha_one_models_identical',same,'All 16 representatives agree');
o=get('R1_pure_square');
add('pure_square_no_flip',strcmp(cv_mode_codes(o.simple),'LL') && ...
    strcmp(cv_mode_codes(o.task),'LL'),'Nonlinear duration alone does not imply different mode');
labels={'below','equal','above'}; expected={'LH','HL|LH','HL'};
for j=1:3
    o=get(['R2_' labels{j} '_tight']);
    add(['R2_' labels{j} '_optimal'],strcmp(cv_mode_codes(o.task),expected{j}),expected{j});
    add(['R2_' labels{j} '_local_merge_fails'],~any([o.local_merge.feasible]),'Local LL fails jointly');
    add(['R2_' labels{j} '_A_both_modes_feasible'],all(isfinite(o.conditional_energy(1,:))), ...
        'A local L still admits a globally feasible completion');
    k=find(strcmp({cases.id},['R2_' labels{j} '_tight'])); c=cases(k);
    [d,Q]=cv_response(c,'task'); inc=d.*Q;
    delta=inc(:,2)-inc(:,1);
    add(['R2_' labels{j} '_compensation_identity'], ...
        abs((o.conditional_energy(1,2)-o.conditional_energy(1,1))-(delta(1)-delta(2)))<1e-10, ...
        'V_A(H)-V_A(L) = delta_A-delta_B');
    o=get(['R2_' labels{j} '_loose']);
    add(['R2_' labels{j} '_loose_LL'],strcmp(cv_mode_codes(o.task),'LL'),'Relaxed deadline restores LL');
end
gaps=[]; ediff=[];
for n=[2 5 8]
    o=get(sprintf('N1_service_%02dms',n));
    gaps(end+1)=o.rows(1).schedule.finish(3)-o.rows(2).schedule.finish(3);
    ediff(end+1)=o.rows(2).energy.integral-o.rows(1).energy.integral;
end
add('N1_time_absorption',max(abs(gaps-[.002 .001 0]))<1e-10,'2,1,0 ms completion gain');
add('N1_energy_difference_unchanged',max(abs(ediff-ediff(1)))<1e-10 && ediff(1)>0, ...
    'High-minus-low energy unchanged across the three occupancies');
o=get('TEST_impossible');
add('infeasible_not_all_modes_tied',isinf(o.task.best) && isempty(o.task.optimal_indices) && ...
    strcmp(cv_mode_codes(o.task),'NONE'),'Impossible deadline gives empty optimum');
k=find(strcmp({cases.id},'R2_above_tight')); c=cases(k); o=results{k};
s=o.task.rows(o.task.optimal_indices(1)).schedule;
bad=s; bad.start(2)=bad.start(1); bad.finish(2)=bad.start(2)+bad.duration(2);
v=cv_validate(c,bad); add('validator_cpu_conflict',contains(v.reason,'cpu_overlap'),'Injected overlap detected');
bad=s; bad.start(4)=bad.start(3); bad.finish(4)=bad.start(4)+bad.duration(4);
v=cv_validate(c,bad); add('validator_npu_conflict',contains(v.reason,'npu_overlap'),'Injected overlap detected');
bad=s; bad.start(3)=0; bad.finish(3)=bad.duration(3);
v=cv_validate(c,bad); add('validator_dependency',contains(v.reason,'precedence'),'Injected early successor detected');
bad=s; bad.start(1)=-.001; bad.finish(1)=bad.start(1)+bad.duration(1);
v=cv_validate(c,bad); add('validator_release',contains(v.reason,'release'),'Injected pre-release start detected');
% Exercise necessary-delay replay, which the chosen R1 inputs need not trigger.
old=cv_schedule(c,'task',[1 1],[1 2],[1 2]);
slower=c; slower.alpha=[1 1];
played=cv_schedule(slower,'task',old.modes,old.cpu_order,old.npu_order,old.start);
add('replay_delays_without_reconfiguration', ...
    all(played.start>=old.start-c.time_tol) && any(played.start>old.start+c.time_tol) && ...
    isequal(played.modes,old.modes) && isequal(played.cpu_order,old.cpu_order) && ...
    isequal(played.npu_order,old.npu_order),'Unit fixture only, not a research case');
checks=table(names(:),logical(passed(:)),detail(:),'VariableNames',{'check','passed','detail'});
    function add(name,ok,why)
        names{end+1}=name; passed(end+1)=ok; detail{end+1}=why;
    end
    function o=get(id)
        index=find(strcmp({cases.id},id)); o=results{index};
    end
end
