function checks=c44_postchecks(trials,runs,refs)
names={}; passed=[]; notes={};
for k=1:numel(trials)
    c=trials(k).case; h=trials(k).thermal;
    for j=1:2
        r=runs{k,j}; tag=[trials(k).id '_' r.version];
        add([tag '_no_program_error'],~strcmp(r.status,'error'),r.message);
        v=c44_validate(c,r.schedule,true); add([tag '_partial_legal'],v.feasible,v.reason);
        previous=c44_schedule(c);
        for p=1:numel(r.events)
            ev=r.events(p); s=ev.prefix; old=isfinite(previous.start);
            invariant=isequaln(s.start(old),previous.start(old)) && isequaln(s.finish(old),previous.finish(old)) && isequaln(s.unit(old),previous.unit(old));
            add(sprintf('%s_prefix_%d',tag,p),invariant,'Committed stage unchanged');
            previous=s;
            if j==2 && ev.selected>0
                z=c44_thermal(c,s,h); add(sprintf('%s_partial_safe_%d',tag,p),strcmp(z.status,'safe'),'Independent reevaluation');
            end
        end
        if strcmp(r.status,'complete')
            v=c44_validate(c,r.schedule); e=cv_energy(c,r.schedule); z=c44_thermal(c,r.schedule,h);
            add([tag '_full_legal'],v.feasible,v.reason);
            add([tag '_energy_dual'],e.difference<max(c.energy_abs_tol,c.energy_rel_tol*abs(e.integral)),'Independent integral');
            if j==2, add([tag '_full_safe'],strcmp(z.status,'safe'),'Continuous peaks including idle tail'); end
            if j==1 && isfinite(refs{k}.noheat_energy)
                add([tag '_noheat_optimal'],abs(e.integral-refs{k}.noheat_energy)<=max(c.energy_abs_tol,c.energy_rel_tol*abs(e.integral)),'Exact no-heat rolling execution');
            end
        end
    end
    add([trials(k).id '_reference_no_error'],~strcmp(refs{k}.status,'error'),refs{k}.message);
    for m=1:4
        a=refs{k}.modes(m);
        if strcmp(a.status,'safe')
            v=c44_validate(c,a.witness); z=c44_thermal(c,a.witness,h); e=cv_energy(c,a.witness);
            add(sprintf('%s_witness_%d',trials(k).id,m),v.feasible && strcmp(z.status,'safe') && abs(e.integral-a.energy)<c.energy_abs_tol,'Reference witness independently checked');
        end
    end
end
checks=table(names',passed',notes','VariableNames',{'name','passed','note'});
    function add(n,v,detail), names{end+1}=n; passed(end+1)=logical(v); notes{end+1}=detail; end
end
