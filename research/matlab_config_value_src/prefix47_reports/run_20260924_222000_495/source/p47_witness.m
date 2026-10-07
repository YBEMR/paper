function out=p47_witness(tr)
% One best no-heat full representative per initial action, in original order.
% First certified full witness is returned as a plan; no online claim.
c=tr.case; h=tr.thermal; timer=tic; s=c44_schedule(c);
out=struct('version','full_suffix_witness','status','running','schedule',s, ...
    'attempts',{{}},'thermal_evaluations',0,'library_count',0,'elapsed_s',0,'message','');
try
    lib=c44_library(c,timer); out.library_count=lib.count; net=thv_build(h);
    if lib.count==0, out.status='no_noheat_configuration'; else
        ids=find(c44_prefix(c,lib.rows,s,0,false)); rr=lib.rows(ids,:);
        at=abs(rr(:,5:8))<=c.time_tol;
        actions=at.*[10*rr(:,3)+rr(:,1) 10*rr(:,4)+rr(:,2) ones(size(rr,1),2)];
        [~,first]=unique(actions,'rows','stable'); ids=ids(first);
        uncertain=false; out.status='no_safe_representative';
        for k=ids'
            budget(); candidate=c44_schedule(c,lib.rows(k,:));
            z=c44_thermal(c,candidate,h,net); out.thermal_evaluations=out.thermal_evaluations+1;
            out.attempts{end+1}=struct('start_set',find(abs(candidate.start)<=c.time_tol), ...
                'representative',candidate,'thermal',z.status,'peak',z.peak, ...
                'score',[lib.energy(k),sum(candidate.finish(3:4)),max(candidate.finish(3:4))]);
            budget();
            if strcmp(z.status,'safe'), out.schedule=candidate; out.status='complete'; break; end
            uncertain=uncertain || strcmp(z.status,'unresolved');
        end
        if uncertain && ~strcmp(out.status,'complete'), out.status='unresolved'; end
    end
catch err
    if strcmp(err.identifier,'c44:timeout'), out.status='timeout'; else, out.status='error'; end
    out.message=getReport(err,'extended','hyperlinks','off');
end
out.elapsed_s=toc(timer);
    function budget()
        if toc(timer)>c.budget_s, error('c44:timeout','Full-suffix witness budget exceeded'); end
    end
end
