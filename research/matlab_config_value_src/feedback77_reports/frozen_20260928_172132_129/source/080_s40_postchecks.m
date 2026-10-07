function checks=s40_postchecks(trials,refs,runs,legacy,lrefs,lruns,here)
names={}; values=[];
for scope=1:2
    if scope==1, ts=trials; rs=refs; ps=runs; else, ts=legacy; rs=lrefs; ps=lruns; end
    for k=1:numel(ts)
        t=ts(k); r=rs{k}; c=t.case; h=t.thermal;
        add('energy_bounds',r.decision.lower_J<=r.decision.upper_J+c.energy_abs_tol);
        for z=r.modes
            if z.has_safe, verify(z.safe_schedule,'safe'); end
            if z.has_violation, verify(z.unsafe_schedule,'violation'); end
            if z.excluded && ~isempty(z.earliest_indices), add('exclusion_exhausted',z.exhausted&&z.unresolved==0&&~z.has_safe); end
            if z.all_safe, add('all_safe_evidence',(~isempty(z.certificate)&&z.certificate.safe)||(z.exhausted&&z.unresolved==0&&~z.has_violation)); end
        end
        for v=1:2
            rr=ps{k,v}; add('policy_no_error',~strcmp(rr.status,'error'));
            for j=1:numel(rr.outputs)
                o=rr.outputs{j}; mask=isfinite(o.schedule.start);
                add('all_committed_starts_on_grid',all(abs(o.schedule.start(mask)/h.grid-round(o.schedule.start(mask)/h.grid))*h.grid<c.time_tol));
                if strcmp(o.status,'completed')
                    vv=cv_validate(c,o.schedule); en=cv_energy(c,o.schedule); ev=thv_evaluate(c,o.schedule,h);
                    add('policy_complete_legal',vv.feasible);
                    add('policy_independent_thermal',strcmp(ev.status,o.thermal.status)&&max(abs(ev.peak-o.thermal.peak))<1e-10);
                    add('policy_energy_double',abs(en.formula-en.integral)<max(c.energy_abs_tol,c.energy_rel_tol*en.formula));
                end
            end
        end
    end
end
% Legacy results are read only after all new policy executions.
old=load(fullfile(here,'h37_reports','run_20260924_101336_425','results.mat'),'runs');
for k=1:numel(legacy)
    c=legacy(k).case;
    if strcmp(c.id,'R1_alpha_02'), expected=.084;
    elseif strcmp(c.id,'R1_alpha_10'), expected=.089; else, expected=.071; end
    add('legacy_reference_lower_bound',abs(lrefs{k}.reference.best-expected)<1e-12&&lrefs{k}.decision.energy_exact);
    if ~strcmp(c.id,'R1_alpha_10'), add('legacy_10_A',strcmp(lrefs{k}.decision.class,'A'));
    elseif all(legacy(k).thermal.initial==78), add('legacy_3_B',strcmp(lrefs{k}.decision.class,'B')); end
    for v=1:2
        oldrun=old.runs((k-1)*2+v); o=lruns{k,v}.outputs{1};
        add('legacy_policy_exact_schedule',isequaln(o.schedule,oldrun.outputs{1}.schedule));
        add('legacy_policy_safe_optimal',strcmp(o.thermal.status,'safe')&&abs(o.energy.integral-expected)<1e-12);
    end
end
% T0 and deadline monotonicity applies per mode, not to A/B/C labels.
for i=1:numel(trials)
    for j=i+1:numel(trials)
        if ~strcmp(trials(i).package,trials(j).package), continue; end
        sameT=trials(i).margin==trials(j).margin;
        sameD=trials(i).rho==trials(j).rho;
        if ~(sameT||sameD), continue; end
        for a=1:2
            for b=1:2
                ii=find(arrayfun(@(z)isequal(z.modes,[a b]),refs{i}.modes));
                jj=find(arrayfun(@(z)isequal(z.modes,[a b]),refs{j}.modes));
                x=refs{i}.modes(ii); y=refs{j}.modes(jj);
                % Trial ordering: deadlines increase, and headroom increases (colder).
                add('per_mode_monotonic_evidence',~(x.has_safe&&y.excluded));
            end
        end
    end
end
checks=table(string(names'),logical(values'),'VariableNames',{'check','passed'});
    function add(name,value)
        names{end+1}=sprintf('%s_%d',name,numel(names)+1); values(end+1)=logical(value);
    end
    function verify(s,status)
        v=cv_validate(c,s); e=cv_energy(c,s); ev=thv_evaluate(c,s,h);
        add('reference_witness_legal',v.feasible&&all(abs(s.start/h.grid-round(s.start/h.grid))*h.grid<c.time_tol));
        add('reference_witness_replay',strcmp(ev.status,status));
        add('reference_energy_double',abs(e.integral-e.formula)<c.energy_abs_tol);
    end
end
