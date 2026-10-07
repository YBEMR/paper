function out=c44_reference(tr,policy)
c=tr.case; h=tr.thermal; timer=tic;
mode=repmat(struct('code','','energy',nan,'legal_count',0,'status','not_searched', ...
    'evaluated',0,'uncertain',0,'witness',[]),1,4);
codes={'LL','LH','HL','HH'}; for m=1:4, mode(m).code=codes{m}; end
out=struct('status','running','noheat_energy',nan,'noheat_modes',[], ...
    'noheat_representatives',{{}},'library_count',0,'modes',mode, ...
    'lower_J',nan,'upper_J',inf,'energy_exact',false,'optimal_modes',[], ...
    'optimal_modes_complete',false,'elapsed_s',0,'message','', ...
    'divergence',struct('status','not_needed','time',nan,'evaluations',0));
lib=[]; known=[];
try
    lib=c44_library(c,timer); out.library_count=lib.count; net=thv_build(h);
    if lib.count==0
        out.status='noheat_infeasible'; out.lower_J=inf; out.elapsed_s=toc(timer); return;
    end
    out.noheat_energy=min(lib.energy); tol=etol(out.noheat_energy);
    out.noheat_modes=unique(lib.mode_id(abs(lib.energy-out.noheat_energy)<=tol))';
    for m=out.noheat_modes
        k=find(lib.mode_id==m,1); out.noheat_representatives{end+1}=c44_schedule(c,lib.rows(k,:));
    end
    known=zeros(lib.count,1,'uint8'); % 0 unchecked, 1 safe, 2 violation, 3 unresolved
    for m=1:4
        mode(m).energy=lib.mode_energy(m); mode(m).legal_count=sum(lib.mode_id==m);
        if mode(m).legal_count==0, mode(m).status='noheat_infeasible'; end
    end
    found_layer=inf;
    for layer=unique(lib.mode_rank)'
        if layer>found_layer, break; end
        for m=find(lib.mode_rank'==layer)
            if mode(m).legal_count==0, continue; end
            mode(m).status='searching';
            ix=find(lib.mode_id==m);
            for k=ix'
                budget(); z=c44_thermal(c,c44_schedule(c,lib.rows(k,:)),h,net);
                mode(m).evaluated=mode(m).evaluated+1;
                if strcmp(z.status,'safe')
                    known(k)=1; mode(m).status='safe';
                    mode(m).witness=c44_schedule(c,lib.rows(k,:)); found_layer=layer; break;
                elseif strcmp(z.status,'violation'), known(k)=2;
                else, known(k)=3; mode(m).uncertain=mode(m).uncertain+1;
                end
            end
            if strcmp(mode(m).status,'searching')
                if mode(m).uncertain>0, mode(m).status='unresolved'; else, mode(m).status='excluded'; end
            end
        end
    end
    out.status='complete';
catch err
    if strcmp(err.identifier,'c44:timeout'), out.status='timeout'; else, out.status='error'; end
    out.message=getReport(err,'extended','hyperlinks','off');
end
out.modes=mode; out=bound(out);
% Diagnostic only after the policies have finished. It uses the remaining
% reference budget; no separate enlarged budget or arbitrary witness target.
if ~isempty(lib) && out.energy_exact && nargin>=2 && ~strcmp(out.status,'error')
    valid=c44_validate(c,policy.schedule);
    good=false;
    if strcmp(policy.status,'complete') && valid.feasible
        e=cv_energy(c,policy.schedule); z=c44_thermal(c,policy.schedule,h);
        good=strcmp(z.status,'safe') && abs(e.integral-out.upper_J)<=etol(out.upper_J);
    end
    if ~good
        diag=struct('status','no_loss_proved','time',nan,'evaluations',0);
        try
            opt=abs(lib.energy-out.upper_J)<=etol(out.upper_J);
            for event=policy.events
                budget(); eligible=find(opt & c44_prefix(c,lib.rows,event.prefix,event.time,true));
                if any(known(eligible)==1), continue; end
                safe=false; uncertain=any(known(eligible)==3);
                for k=eligible(known(eligible)==0)'
                    budget(); z=c44_thermal(c,c44_schedule(c,lib.rows(k,:)),h,net);
                    diag.evaluations=diag.evaluations+1;
                    if strcmp(z.status,'safe'), known(k)=1; safe=true; break;
                    elseif strcmp(z.status,'violation'), known(k)=2;
                    else, known(k)=3; uncertain=true; end
                end
                if safe, continue; end
                if uncertain, diag.status='unresolved'; else, diag.status='first_loss_proved'; end
                diag.time=event.time; break;
            end
        catch err
            if strcmp(err.identifier,'c44:timeout'), diag.status='budget_unresolved';
            else, diag.status='error'; out.message=[out.message getReport(err,'extended','hyperlinks','off')]; end
        end
        out.divergence=diag;
    end
end
out.elapsed_s=toc(timer);
    function t=etol(e), t=max(c.energy_abs_tol,c.energy_rel_tol*abs(e)); end
    function budget()
        if toc(timer)>c.budget_s, error('c44:timeout','Reference including diagnostics exceeded budget'); end
    end
    function r=bound(r)
        safe=strcmp({r.modes.status},'safe');
        possible=~ismember({r.modes.status},{'excluded','noheat_infeasible'});
        if all(isnan([r.modes.energy]))
            r.lower_J=(c.idle_cpu+c.idle_npu+c.external)*c.window; return;
        end
        if any(safe), r.upper_J=min([r.modes(safe).energy]); end
        if any(possible), r.lower_J=min([r.modes(possible).energy]); else, r.lower_J=inf; end
        r.energy_exact=isfinite(r.upper_J) && abs(r.upper_J-r.lower_J)<=etol(r.upper_J);
        if r.energy_exact
            layer=abs([r.modes.energy]-r.upper_J)<=etol(r.upper_J);
            r.optimal_modes=find(safe & layer);
            r.optimal_modes_complete=all(ismember({r.modes(layer).status},{'safe','excluded','noheat_infeasible'}));
        end
        if all(ismember({r.modes.status},{'excluded','noheat_infeasible'})), r.status='grid_thermal_infeasible'; end
    end
end
