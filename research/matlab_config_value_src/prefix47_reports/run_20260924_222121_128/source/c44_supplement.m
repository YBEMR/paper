function checks=c44_supplement(folder)
% Targeted acceptance checks using frozen outputs. No new research cases.
x=load(fullfile(folder,'results.mat')); trials=x.trials; runs=x.runs;
names={}; passed=[]; notes={}; c=trials(1).case; h=trials(1).thermal;
s=c44_schedule(c); row=[2 1 1 2 0 .006 .004 .011];
s=c44_commit(c,s,row,0); s=c44_commit(c,s,row,.004);
z=c44_thermal(c,s,h); mids=(z.event_time(1:end-1)+z.event_time(2:end))/2;
ix=find(mids>.004 & mids<.007,1);
add('idle_cpu_running_npu',~isempty(ix) && abs(z.segments{ix}.power(2)-1.3)<1e-12 && abs(z.segments{ix}.power(1)-.2)<1e-12,'Partial trajectory preserves running NPU');
for k=1:numel(trials)
    disabled=c44_policy(trials(k),'C1',false);
    add([trials(k).id '_filter_off'],isequaln(disabled.schedule,runs{k,1}.schedule) && isequaln(disabled.events,runs{k,1}.events),'Same actions as frozen C0');
    for v=1:2
        r=runs{k,v}; c=trials(k).case;
        for ev=r.events
            s=ev.prefix; known=isfinite(s.start);
            add(sprintf('%s_%d_%.0f_no_future_commit',trials(k).id,v,ev.time/c.grid),all(s.start(known)<=ev.time+c.time_tol),'No reservation of future starts');
        end
    end
end
ev=runs{4,2}.events(1);
add('rejected_group_then_other_action',ev.rejected==1 && ev.selected>1 && numel(ev.started)==1 && isequal(ev.attempts{1}.start_set,[1 2]),'Reject pair, launch one CPU without freezing both');
c=trials(4).case; s=c44_schedule(c);
both=c44_commit(c,s,[2 2 1 2 0 0 .004 .007],0);
one=both; one.start(2)=nan; one.finish(2)=nan; one.duration(2)=nan; one.increment(2)=nan; one.unit(2)=nan; one.modes(2)=nan;
onlyB=both; onlyB.start(1)=nan; onlyB.finish(1)=nan; onlyB.duration(1)=nan; onlyB.increment(1)=nan; onlyB.unit(1)=nan; onlyB.modes(1)=nan;
a=c44_thermal(c,one,trials(4).thermal); b=c44_thermal(c,onlyB,trials(4).thermal); z=c44_thermal(c,both,trials(4).thermal);
add('individual_safe_joint_unsafe',strcmp(a.status,'safe') && strcmp(b.status,'safe') && strcmp(z.status,'violation'),'Joint candidate check is necessary for this fixture');
diag_fixture=trials(4); diag_fixture.id='fixture_first_loss';
rr=c44_reference(diag_fixture,runs{4,1});
add('all_optimal_suffix_first_loss',strcmp(rr.divergence.status,'first_loss_proved') && rr.divergence.time==0,'Diagnostic against C0 hot prefix, not a selected witness');
source=fileread(which('c44_policy'));
add('policy_no_reference_file_input',~any(contains(source,{'c44_reference','fileread','readtable','load(','fopen'})),'Raw case and self state only');
frozen=jsondecode(fileread(fullfile(folder,'freeze_manifest.json')));
same=true; here=fileparts(mfilename('fullpath'));
for a=frozen'
    [~,name,ext]=fileparts(a.path);
    if endsWith(a.path,'.m') || endsWith(a.path,'COORDINATION44_README.md')
        now=c44_audit({fullfile(here,[name ext])}); same=same && strcmp(now.sha256,a.sha256);
    end
end
add('formal_source_still_matches',same,'No executor/reference changes after formal results');
checks=table(names',passed',notes','VariableNames',{'name','passed','note'});
sub=fullfile(folder,'supplement'); if ~exist(sub,'dir'), mkdir(sub); end
copyfile(which('c44_supplement'),fullfile(sub,'c44_supplement.m'));
writetable(checks,fullfile(sub,'checks.csv'));
save(fullfile(sub,'checks.mat'),'checks','rr');
fid=fopen(fullfile(sub,'source_hash.json'),'w'); fprintf(fid,'%s',jsonencode(c44_audit({fullfile(sub,'c44_supplement.m')}),'PrettyPrint',true)); fclose(fid);
fprintf('SUPPLEMENT %d/%d\n',sum(checks.passed),height(checks)); assert(all(checks.passed),'Supplemental acceptance checks failed');
    function add(n,v,note), names{end+1}=n; passed(end+1)=logical(v); notes{end+1}=note; end
end
