function out=s40_classify(t)
c=t.case; h=t.thermal; clock=tic; net=thv_build(h);
r=s40_reference(c,h,clock); modes=struct([]);
for a=1:2
    for b=1:2
        ix=find(arrayfun(@(z)isequal(z.schedule.modes,[a b]),r.rows));
        ok=ix(arrayfun(@(z)z.validation.feasible,r.rows(ix)));
        en=r.rows(ix(1)).energy; optimal=isfinite(r.best)&&abs(en-r.best)<=max(c.energy_abs_tol,c.energy_rel_tol*abs(r.best))&&~isempty(ok);
        z=struct('modes',[a b],'energy',en,'optimal',optimal,'has_safe',false, ...
            'has_violation',false,'all_safe',false,'excluded',isempty(ok),'status','not_searched', ...
            'unresolved',0,'evaluated',0,'enumerated',0,'exhausted',false,'certificate',[], ...
            'safe_schedule',[],'safe_evaluation',[],'unsafe_schedule',[],'unsafe_evaluation',[], ...
            'earliest_indices',ok);
        if isempty(ok), z.status='no_heat_infeasible'; end
        modes=s40_append(modes,z);
    end
end
[~,ord]=sortrows([[modes.energy]' vertcat(modes.modes)],[1 2 3]); modes=modes(ord);
for k=1:numel(modes)
    if modes(k).excluded, continue; end
    dec=s40_decide(modes,r.best,c);
    if ~modes(k).optimal && dec.energy_exact && isfinite(dec.upper_J) && modes(k).energy>dec.upper_J+max(c.energy_abs_tol,c.energy_rel_tol*dec.upper_J)
        modes(k).status='not_needed_above_proven_optimum'; continue;
    end
    if toc(clock)>h.budget_s, modes(k).status='timeout_not_started'; continue; end
    s=r.rows(modes(k).earliest_indices(1)).schedule;
    cert=s40_certificate(c,h,s); modes(k).certificate=cert;
    if cert.safe
        ev=thv_evaluate(c,s,h,net); assert(strcmp(ev.status,'safe'));
        modes(k).has_safe=true; modes(k).all_safe=true; modes(k).status='all_safe_certificate';
        modes(k).safe_schedule=s; modes(k).safe_evaluation=ev; modes(k).evaluated=1;
        continue;
    end
    for ix=modes(k).earliest_indices
        if toc(clock)>h.budget_s, break; end
        probe(r.rows(ix).schedule);
    end
    if enough(), modes(k).status='witnesses_sufficient'; continue; end
    walk=s40_walk(c,h,modes(k).modes,@probe,clock);
    modes(k).enumerated=walk.count; modes(k).exhausted=strcmp(walk.status,'exhausted');
    modes(k).status=walk.status;
    if modes(k).exhausted && modes(k).unresolved==0
        modes(k).excluded=~modes(k).has_safe;
        modes(k).all_safe=~modes(k).has_violation;
    end
end
out=struct('reference',r,'modes',modes,'decision',s40_decide(modes,r.best,c), ...
    'elapsed_s',toc(clock),'domain','start_grid_continuous_peak','grid',h.grid);
    function stop=probe(s)
        ev=thv_evaluate(c,s,h,net); modes(k).evaluated=modes(k).evaluated+1;
        if strcmp(ev.status,'safe')
            if ~modes(k).has_safe, modes(k).safe_schedule=s; modes(k).safe_evaluation=ev; end
            modes(k).has_safe=true;
        elseif strcmp(ev.status,'violation')
            if ~modes(k).has_violation, modes(k).unsafe_schedule=s; modes(k).unsafe_evaluation=ev; end
            modes(k).has_violation=true;
        else, modes(k).unresolved=modes(k).unresolved+1; end
        stop=enough();
    end
    function stop=enough()
        stop=modes(k).has_safe && (~modes(k).optimal || modes(k).has_violation);
    end
end
