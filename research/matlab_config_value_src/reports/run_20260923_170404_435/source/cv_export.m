function cv_export(folder,cases,results)
summary={}; schedules={}; queue={};
for k=1:numel(cases)
    c=cases(k); o=results{k};
    if ~strcmp(o.status,'complete'), continue; end
    if strcmp(o.kind,'fixed_suffix')
        for j=1:2
            z=o.rows(j); s=z.schedule;
            queue(end+1,:)={c.id,c.n(2),j,z.validation.feasible,s.finish(3),s.finish(4), ...
                z.energy.integral,'not_evaluated'};
            record(c.id,'fixed_suffix',j,false,s,z.validation,z.energy);
        end
        continue;
    end
    refs={o.simple,o.task}; labels={'simple','task'};
    for h=1:2
        ref=refs{h};
        for j=1:numel(ref.rows)
            z=ref.rows(j);
            record(c.id,labels{h},j,ismember(j,ref.optimal_indices),z.schedule,z.validation,z.energy);
        end
    end
    replays={o.simple_replay,o.task_replay};
    for h=1:2
        for z=replays{h}
            record(c.id,[labels{h} '_raw_common'],z.source_index,false,z.raw_common,z.raw_validation,cv_energy(c,z.raw_common));
            record(c.id,[labels{h} '_replay'],z.source_index,false,z.replayed,z.validation,z.energy);
        end
    end
    er=arrayfun(@(z)z.energy.integral,o.simple_replay);
    if isempty(er), lo=nan; hi=nan; else, lo=min(er); hi=max(er); end
    localA='NONE'; localB='NONE'; names='LH';
    if ~isempty(o.local_modes{1}), localA=names(o.local_modes{1}); end
    if ~isempty(o.local_modes{2}), localB=names(o.local_modes{2}); end
    summary(end+1,:)={c.id,c.family,o.task.best,cv_mode_codes(o.task), ...
        numel(o.task.optimal_indices),o.simple.best,cv_mode_codes(o.simple),lo,hi, ...
        localA,localB,any([o.local_merge.feasible]), ...
        o.conditional_energy(1,1),o.conditional_energy(1,2), ...
        o.conditional_energy(2,1),o.conditional_energy(2,2), ...
        all(arrayfun(@(z)z.validation.feasible,o.simple_replay)),numel(er),o.elapsed_s,'not_evaluated'};
end
writetable(cell2table(summary,'VariableNames',{'case_id','family','task_best_J','task_modes', ...
    'task_optimal_representatives','simple_predicted_best_J','simple_modes','simple_replay_min_J', ...
    'simple_replay_max_J','local_A','local_B','local_joint_any_feasible', ...
    'conditional_A_L_J','conditional_A_H_J','conditional_B_L_J','conditional_B_H_J', ...
    'simple_replays_all_feasible','simple_replay_count','elapsed_s','thermal'}),fullfile(folder,'summary.csv'));
writetable(cell2table(queue,'VariableNames',{'case_id','B_npu_duration_s','A_mode','feasible', ...
    'A_completion_s','B_completion_s','energy_J','thermal'}),fullfile(folder,'queue.csv'));
writetable(cell2table(schedules,'VariableNames',{'case_id','evaluation','row_id','optimal_representative', ...
    'mode_A','mode_B','cpu_order','npu_order','start_CA_s','start_CB_s','start_NA_s','start_NB_s', ...
    'end_CA_s','end_CB_s','end_NA_s','end_NB_s','feasible','reason', ...
    'energy_J','formula_J','base_J','cpu_J','npu_J','thermal'}),fullfile(folder,'schedules.csv'));
    function record(id,kind,j,opt,s,v,e)
        schedules(end+1,:)=[{id,kind,j,opt,s.modes(1),s.modes(2), ...
            sprintf('%d%d',s.cpu_order),sprintf('%d%d',s.npu_order)}, ...
            num2cell(s.start),num2cell(s.finish),{v.feasible,v.reason, ...
            e.integral,e.formula,e.base,e.cpu,e.npu,'not_evaluated'}];
    end
end
