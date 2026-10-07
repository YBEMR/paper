function s40_export(folder,trials,refs,runs,prefix)
summary=struct([]); mode_rows=struct([]); methods=struct([]); events=struct([]); schedules=struct([]); witnesses=struct([]);
labels='LH';
for k=1:numel(trials)
    t=trials(k); r=refs{k}; dec=r.decision;
    package='legacy'; rho=NaN; margin=NaN;
    if isfield(t,'package'), package=t.package; rho=t.rho; margin=t.margin; end
    opt=[r.modes.optimal]; good=[r.modes.has_safe]; ex=[r.modes.excluded];
    pending=opt&~good&~ex;
    row=struct('trial',t.id,'package',package,'rho',rho,'margin',margin,'initial_C',t.thermal.initial(1), ...
        'deadline_A_s',t.case.deadline(1),'deadline_B_s',t.case.deadline(2),'grid_s',t.thermal.grid, ...
        'class',dec.class,'reason',dec.reason,'E0_J',r.reference.best,'thermal_lower_J',dec.lower_J, ...
        'thermal_upper_J',dec.upper_J,'energy_exact',dec.energy_exact,'M0',modelabel(r.modes(opt)), ...
        'M0_safe',modelabel(r.modes(opt&good)),'M0_excluded',modelabel(r.modes(opt&ex)), ...
        'M0_pending',modelabel(r.modes(pending)),'M0_shrink_proved',any(opt&ex), ...
        'M0_survival_complete',~any(pending),'thermal_optimal_confirmed','','thermal_optimal_pending','', ...
        'elapsed_s',r.elapsed_s,'thermal_evaluations',sum([r.modes.evaluated]), ...
        'enumerated',sum([r.modes.enumerated]),'NPU_roles','dependency_tail;queue_resource;coupled_node;causality_not_isolated');
    if isfinite(dec.upper_J)
        tol=max(t.case.energy_abs_tol,t.case.energy_rel_tol*dec.upper_J);
        eligible=abs([r.modes.energy]-dec.upper_J)<=tol;
        if dec.energy_exact, row.thermal_optimal_confirmed=modelabel(r.modes(eligible&good)); end
        row.thermal_optimal_pending=modelabel(r.modes(eligible&~good&~ex));
    end
    summary=push(summary,row);
    for z=r.modes
        cert='none'; bound=NaN;
        if ~isempty(z.certificate), cert=z.certificate.kind; bound=z.certificate.bound_C; end
        mode_rows=push(mode_rows,struct('trial',t.id,'modes',labels(z.modes),'energy_J',z.energy, ...
            'no_heat_optimal',z.optimal,'has_safe',z.has_safe,'has_violation',z.has_violation,'all_safe',z.all_safe, ...
            'excluded',z.excluded,'status',z.status,'unresolved',z.unresolved,'evaluated',z.evaluated, ...
            'enumerated',z.enumerated,'exhausted',z.exhausted,'certificate',cert,'bound_C',bound));
        if z.has_safe, witness('safe',z.safe_schedule,z.safe_evaluation); end
        if z.has_violation, witness('violation',z.unsafe_schedule,z.unsafe_evaluation); end
    end
    for v=1:2
        run=runs{k,v}; versions={'P0','P1'};
        if isempty(run.outputs)
            mr=methodbase(); mr.status=run.status; methods=push(methods,mr); continue;
        end
        for j=1:numel(run.outputs)
            o=run.outputs{j}; mr=methodbase(); mr.tie_index=j; mr.tie_count=numel(run.configs);
            mr.modes=labels(o.schedule.modes); mr.status=o.status; mr.reason=o.reason;
            mr.thermal_evaluations=o.thermal_evaluations; mr.rejections=o.rejected;
            mr.advances_without_start=o.advances_without_start;
            if strcmp(o.status,'completed')
                mr.energy_J=o.energy.integral; mr.completion_A_s=o.validation.completion(1); mr.completion_B_s=o.validation.completion(2);
                mr.peak_CPU_C=o.thermal.peak(1); mr.peak_NPU_C=o.thermal.peak(2); mr.thermal=o.thermal.status;
                mr.valid=strcmp(o.thermal.status,'safe');
                if mr.valid&&dec.energy_exact&&isfinite(dec.upper_J)
                    mr.gap_J=mr.energy_J-dec.upper_J;
                    mr.reached_reference=abs(mr.gap_J)<=max(t.case.energy_abs_tol,t.case.energy_rel_tol*dec.upper_J);
                end
            end
            ix=find(arrayfun(@(z)isequal(z.modes,o.schedule.modes),r.modes),1);
            if ~mr.valid
                if strcmp(dec.class,'C'), mr.failure_scope='fixed_original_configuration_excluded';
                elseif r.modes(ix).has_safe
                    mr.failure_scope='same_mode_safe_witness_exists';
                    witness_s=r.modes(ix).safe_schedule;
                    starts=unique([witness_s.start o.schedule.start(isfinite(o.schedule.start))]);
                    for tt=starts
                        p=find(isfinite(o.schedule.start)&abs(o.schedule.start-tt)<t.case.time_tol);
                        q=find(abs(witness_s.start-tt)<t.case.time_tol);
                        if ~isequal(p,q), mr.first_witness_difference_s=tt; break; end
                    end
                elseif strcmp(dec.class,'D'), mr.failure_scope='whole_grid_problem_infeasible';
                else, mr.failure_scope='reference_evidence_incomplete'; end
            end
            methods=push(methods,mr);
            for z=1:4
                schedules=push(schedules,struct('trial',t.id,'version',versions{v},'tie_index',j,'stage',z, ...
                    'mode',o.schedule.modes(mod(z-1,2)+1),'start_s',o.schedule.start(z),'finish_s',o.schedule.finish(z), ...
                    'increment_W',o.schedule.increment(z),'state',o.state(z)));
            end
            for e=o.events
                er=struct('trial',t.id,'version',versions{v},'tie_index',j);
                fields=fieldnames(e); for q=1:numel(fields), er.(fields{q})=e.(fields{q}); end
                events=push(events,er);
            end
        end
    end
end
write('summary',summary); write('modes',mode_rows); write('methods',methods);
write('events',events); write('schedules',schedules); write('witnesses',witnesses);
    function mr=methodbase()
        mr=struct('trial',t.id,'version',versions{v},'class',dec.class,'status','','reason','','modes','', ...
            'tie_index',0,'tie_count',numel(run.configs),'valid',false,'reached_reference',false, ...
            'energy_J',NaN,'gap_J',NaN,'thermal','not_evaluated','completion_A_s',NaN,'completion_B_s',NaN, ...
            'peak_CPU_C',NaN,'peak_NPU_C',NaN,'thermal_evaluations',0,'rejections',0,'advances_without_start',0, ...
            'elapsed_version_s',run.elapsed_s,'failure_scope','','first_witness_difference_s',NaN);
    end
    function witness(kind,s,ev)
        witnesses=push(witnesses,struct('trial',t.id,'modes',labels(s.modes),'kind',kind, ...
            'start_CA_s',s.start(1),'start_CB_s',s.start(2),'start_NA_s',s.start(3),'start_NB_s',s.start(4), ...
            'peak_CPU_C',ev.peak(1),'peak_NPU_C',ev.peak(2),'peak_time_CPU_s',ev.peak_time(1),'peak_time_NPU_s',ev.peak_time(2)));
    end
    function write(name,x)
        if isempty(x), writetable(table(),fullfile(folder,[prefix '_' name '.csv']));
        else, writetable(struct2table(x),fullfile(folder,[prefix '_' name '.csv'])); end
    end
end
function a=push(a,b)
if isempty(a), a=b; else, a(end+1)=b; end
end
function label=modelabel(m)
label=''; letters='LH';
for z=m
    if ~isempty(label), label=[label ';']; end %#ok<AGROW>
    label=[label letters(z.modes)]; %#ok<AGROW>
end
end
