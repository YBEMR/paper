function [summary,checks]=s55_export(folder,trials,runs,refs)
% Post-run verifier only. No schedule construction, repair or search.
records=struct([]);scheduleRows=struct([]);names={};passed=[];notes={};
for k=1:numel(trials)
    tr=trials(k);c=tr.case;h=tr.thermal;ref=refs{k};allr={runs{k,1},runs{k,2},ref};
    for j=1:3
        r=allr{j};tag=[tr.id '_' r.method];s=r.schedule;
        complete=all(isfinite(s.start));valid=false;E=NaN;pk=[NaN NaN];C=nan(size(c.terminal));therm='not_evaluated';gap=NaN;gaplo=NaN;
        if complete
            v=s55_validate(c,s);add([tag '_complete_legal'],v.feasible,v.reason);C=v.completion;
            if v.feasible
                e=s55_energy(c,s);z=s55_thermal(c,s,h);E=e.integral_J;pk=z.peak;therm=z.status;valid=strcmp(therm,'safe');
                add([tag '_energy_dual'],e.error_J<=max(c.energy_abs_tol,c.energy_rel_tol*abs(E)),'Event integration vs base plus activity');
                if all(h.initial==30),add([tag '_cold_bound'],all(pk<=44.68280900068348+1e-6),'53 sufficient bound, not actual prediction');end
                if strcmp(r.status,'complete_safe'),add([tag '_certified_safe'],valid,'Baseline claimed certified plan');end
                if valid && ref.optimal_value_proved,gap=E-ref.upper_J;end
                if valid && isfinite(ref.upper_J),gaplo=max(0,E-ref.upper_J);end
                plotplan(folder,tr,r,s,z);
            end
        end
        if ~r.enumeration_complete
            add([tag '_partial_not_optimal'],~r.optimal_value_proved && ~r.sort_complete,'Partial minimum is not a proof');
        end
        if strcmp(tr.id,'check_noheat_infeasible'),add([tag '_chain_infeasible'],strcmp(r.status,'noheat_infeasible'),'4ms below isolated5ms');end
        if strcmp(r.method,'full_suffix') && ~r.enumeration_complete
            add([tag '_no_partial_representatives'],isempty(r.attempts),'No fake exact representatives');
        end
        row=struct('case_id',tr.id,'cohort',tr.cohort,'method',r.method,'status',r.status, ...
            'enumeration_complete',r.enumeration_complete,'sort_complete',r.sort_complete, ...
            'library_count',r.library_count,'visited',r.visited,'complete_schedule',complete, ...
            'valid_safe_schedule',valid,'completion_A_ms',C(1)*1000,'completion_B_ms',C(2)*1000, ...
            'energy_mJ',E*1000,'peak_CPU_C',pk(1),'peak_NPU_C',pk(2),'thermal_status',therm, ...
            'bound_scope',ternary(j==1,'noheat','thermal'),'lower_mJ',r.lower_J*1000,'upper_mJ',r.upper_J*1000, ...
            'optimal_value_proved',r.optimal_value_proved,'optimal_set_complete',r.optimal_set_complete, ...
            'gap_to_proved_reference_mJ',gap*1000,'proved_gap_lower_mJ',gaplo*1000, ...
            'thermal_calls',r.thermal_calls,'representatives',r.representative_count,'elapsed_s',r.elapsed_s, ...
            'S1_A_unit',s.unit(2),'S1_B_unit',s.unit(6));
        records=[records;row]; %#ok<AGROW>
        for i=1:c.n
            sr=struct('case_id',tr.id,'method',r.method,'stage_id',c.stage_id{i}, ...
                'unit',s.unit(i),'mode',s.mode(i),'start_ms',s.start(i)*1000,'finish_ms',s.finish(i)*1000, ...
                'duration_ms',s.duration(i)*1000,'active_increment_W',s.increment(i));
            scheduleRows=[scheduleRows;sr]; %#ok<AGROW>
        end
        if ~isempty(r.attempts)
            aa=struct([]);
            for a=1:numel(r.attempts)
                q=r.attempts{a};aa(a)=struct('attempt',a,'action_key',mat2str(q.action_key), ...
                    'row',mat2str(q.row),'energy_mJ',q.energy_J*1000,'thermal_status',q.thermal_status, ...
                    'peak_CPU_C',q.peak_C(1),'peak_NPU_C',q.peak_C(2));
            end
            writetable(struct2table(aa),fullfile(folder,[tag '_attempts.csv']));
        end
    end
    if isfield(ref.reference,'configs')
        rr=ref.reference;names2=arrayfun(@(i)sprintf('choice_%d',i),1:c.n,'UniformOutput',false);
        tab=array2table([double(rr.configs) rr.energy_J rr.rank rr.total_schedules rr.evaluated rr.state rr.has_unresolved], ...
            'VariableNames',[names2 {'energy_J','energy_rank','legal_schedules','evaluated','state','has_unresolved'}]);
        writetable(tab,fullfile(folder,[tr.id '_reference_configurations.csv']));
    end
end
summary=struct2table(records);writetable(struct2table(scheduleRows),fullfile(folder,'schedules.csv'));
checks=table(names',logical(passed'),notes','VariableNames',{'name','passed','note'});
    function add(n,q,t),names{end+1}=n;passed(end+1)=logical(q);notes{end+1}=t;end
end
function plotplan(folder,tr,r,s,z)
fig=figure('Visible','off','Position',[30 30 1100 600]);guard=onCleanup(@()close(fig)); %#ok<NASGU>
tiledlayout(2,1);nexttile;hold on;colors=lines(tr.case.n);
for i=1:tr.case.n
    rectangle('Position',[s.start(i)*1000 s.unit(i)-.28 s.duration(i)*1000 .56],'FaceColor',colors(i,:));
    text((s.start(i)+s.duration(i)/2)*1000,s.unit(i),tr.case.stage_id{i},'HorizontalAlignment','center','FontSize',8);
end
ylim([.5 3.5]);yticks(1:3);yticklabels({'CPU1','CPU2','NPU'});xlim([0 tr.case.window*1000]);grid on;xlabel('Time (ms)');
title([tr.id ' / ' r.method ' / L3 fixed input'],'Interpreter','none');
nexttile;[t,T]=thv_trace(z,tr.thermal,.0001);plot(t*1000,T,'LineWidth',1.2);hold on;
for i=1:2,xline(z.peak_time(i)*1000,':');end
yline(tr.thermal.limit(1),'--');xlim([0 tr.case.window*1000]);grid on;xlabel('Time (ms)');ylabel('Temperature (C)');
legend('CPU','NPU','Location','best');title(['Full schedule + idle tail; ' z.status]);
exportgraphics(fig,fullfile(folder,[tr.id '_' r.method '.png']),'Resolution',130);
end
function s=ternary(q,a,b),if q,s=a;else,s=b;end,end
