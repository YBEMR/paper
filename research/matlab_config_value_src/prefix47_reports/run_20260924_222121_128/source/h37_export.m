function h37_export(folder,trials,runs,diagnostics,reference)
summary=struct([]); schedules=struct([]); events=struct([]); diagrows=struct([]);
for k=1:numel(runs)
    r=runs(k); t=trials(r.trial);
    for j=1:numel(r.outputs)
        o=r.outputs{j}; row=make_row(t,o,reference{r.trial}.reference.best,r.elapsed_s);
        row.tie_index=j; row.tie_count=numel(r.configs); summary=append(summary,row);
        collect(t.id,o,j,'main');
    end
    if isempty(r.outputs)
        row=struct('trial',t.id,'role',t.role,'version',r.version,'modes','', ...
            'status',r.status,'reason',r.message,'energy_J',NaN,'lower_bound_J',reference{r.trial}.reference.best, ...
            'recovered',false,'thermal','not_evaluated','completion_A_s',NaN,'completion_B_s',NaN, ...
            'peak_CPU_C',NaN,'peak_NPU_C',NaN,'thermal_evaluations',0,'rejected',0, ...
            'unresolved_rejections',0,'elapsed_case_version_s',r.elapsed_s,'tie_index',0,'tie_count',numel(r.configs));
        summary=append(summary,row);
    end
end
for k=1:numel(diagnostics)
    d=diagnostics(k); t=trials(d.trial); o=d.output;
    diagrows=append(diagrows,make_row(t,o,reference{d.trial}.reference.best,o.elapsed_shared_s));
    collect(t.id,o,1,'diagnostic_HH');
end
writetable(struct2table(summary),fullfile(folder,'summary.csv'));
writetable(struct2table(diagrows),fullfile(folder,'diagnostics.csv'));
writetable(struct2table(schedules),fullfile(folder,'schedules.csv'));
writetable(struct2table(events),fullfile(folder,'events.csv'));
    function collect(id,o,tie,scope)
        s=o.schedule;
        for z=1:4
            schedules=append(schedules,struct('trial',id,'scope',scope,'version',o.version, ...
                'tie_index',tie,'stage',z,'mode',s.modes(mod(z-1,2)+1),'start_s',s.start(z), ...
                'finish_s',s.finish(z),'increment_W',s.increment(z),'state',o.state(z)));
        end
        for e=o.events
            row=struct('trial',id,'scope',scope,'version',o.version,'tie_index',tie);
            fields=fieldnames(e); for f=1:numel(fields), row.(fields{f})=e.(fields{f}); end
            events=append(events,row);
        end
    end
end
function row=make_row(t,o,bound,elapsed)
energy=NaN; completion=nan(1,2); peak=nan(1,2); thermal='not_evaluated'; recovered=false;
if strcmp(o.status,'completed')
    energy=o.energy.integral; completion=o.validation.completion; peak=o.thermal.peak; thermal=o.thermal.status;
    recovered=strcmp(thermal,'safe') && abs(energy-bound)<=max(t.case.energy_abs_tol,t.case.energy_rel_tol*abs(bound));
end
labels='LH';
row=struct('trial',t.id,'role',t.role,'version',o.version,'modes',labels(o.schedule.modes), ...
    'status',o.status,'reason',o.reason,'energy_J',energy,'lower_bound_J',bound, ...
    'recovered',recovered,'thermal',thermal,'completion_A_s',completion(1),'completion_B_s',completion(2), ...
    'peak_CPU_C',peak(1),'peak_NPU_C',peak(2),'thermal_evaluations',o.thermal_evaluations, ...
    'rejected',o.rejected,'unresolved_rejections',o.unresolved_rejections,'elapsed_case_version_s',elapsed);
end
function s=append(s,row)
if isempty(s), s=row; else, s(end+1)=row; end
end
