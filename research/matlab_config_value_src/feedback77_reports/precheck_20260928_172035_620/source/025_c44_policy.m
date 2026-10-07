function out=c44_policy(tr,version,filter_enabled)
c=tr.case; h=tr.thermal; timer=tic;
if nargin<3, filter_enabled=strcmp(version,'C1'); end
s=c44_schedule(c); log=struct('time',{},'candidates',{},'tested',{},'rejected',{}, ...
    'unresolved',{},'selected',{},'started',{},'prefix',{},'best_score',{},'attempts',{});
status='running'; message=''; libcount=0; evaluations=0; uncertain=false;
try
    lib=c44_library(c,timer); libcount=lib.count; net=thv_build(h);
    if libcount==0, status='no_noheat_configuration'; end
    for tick=0:floor((max(c.deadline)+c.time_tol)/c.grid)
        if ~strcmp(status,'running'), break; end
        budget(); t=tick*c.grid;
        ids=find(c44_prefix(c,lib.rows,s,t,false));
        if isempty(ids), status='prefix_infeasible'; break; end
        rr=lib.rows(ids,:); pending=~isfinite(s.start);
        at=abs(rr(:,5:8)-t)<=c.time_tol & pending;
        action=at.*[10*rr(:,3)+rr(:,1) 10*rr(:,4)+rr(:,2) ones(size(rr,1),2)];
        [~,first]=unique(action,'rows','stable'); ids=ids(first);
        rec=struct('time',t,'candidates',numel(ids),'tested',0,'rejected',0, ...
            'unresolved',0,'selected',0,'started',[],'prefix',s,'best_score',[],'attempts',{{}});
        selected=false;
        for j=1:numel(ids)
            budget(); row=lib.rows(ids(j),:); candidate=c44_commit(c,s,row,t);
            rec.tested=rec.tested+1;
            attempt=struct('start_set',find(~isfinite(s.start)&isfinite(candidate.start)), ...
                'modes',candidate.modes,'units',candidate.unit,'status','not_evaluated', ...
                'peak',[nan nan],'score_energy',lib.energy(ids(j)));
            if filter_enabled
                temp=c44_thermal(c,candidate,h,net); evaluations=evaluations+1;
                attempt.status=temp.status; attempt.peak=temp.peak;
                rec.attempts{end+1}=attempt;
                budget();
                if ~strcmp(temp.status,'safe')
                    rec.rejected=rec.rejected+1;
                    if strcmp(temp.status,'unresolved'), uncertain=true; rec.unresolved=rec.unresolved+1; end
                    continue;
                end
            else
                rec.attempts{end+1}=attempt;
            end
            rec.selected=j; rec.started=find(~isfinite(s.start)&isfinite(candidate.start));
            s=candidate; rec.prefix=s;
            plan=c44_schedule(c,row); rec.best_score=[lib.energy(ids(j)) sum(plan.finish(3:4)) max(plan.finish(3:4))];
            selected=true; break;
        end
        log(end+1)=rec; %#ok<AGROW>
        if ~selected
            if uncertain, status='unresolved'; else, status='thermal_blocked'; end
            break;
        end
        if all(isfinite(s.start)), status='complete'; break; end
    end
    if strcmp(status,'running'), status='prefix_infeasible'; end
    if uncertain && ismember(status,{'prefix_infeasible','thermal_blocked'}), status='unresolved'; end
catch err
    if strcmp(err.identifier,'c44:timeout'), status='timeout'; else, status='error'; end
    message=getReport(err,'extended','hyperlinks','off');
end
out=struct('version',version,'status',status,'message',message,'schedule',s,'events',log, ...
    'library_count',libcount,'thermal_evaluations',evaluations,'elapsed_s',toc(timer), ...
    'uncertainty_encountered',uncertain);
    function budget()
        if toc(timer)>c.budget_s, error('c44:timeout','Policy total budget exceeded'); end
    end
end
