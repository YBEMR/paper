function checks=p47_tests(trials)
names={}; values=[]; notes={}; c=trials(1).case;
lib=c44_library(c,tic); [d,q]=cv_response(c,'task');
add('frozen_mode_durations',max(abs(d-[.016 .008;.008 .004]),[],'all')<1e-12,'Response evaluated from raw input');
add('frozen_active_power',max(abs(q-[1.25 2;1.25 2]),[],'all')<1e-12,'Shared base excluded from activity');
% Independent Cartesian fixture in milliseconds: explicit frozen task equations,
% not c44_validate or c44_prefix. NPU candidates include both orders initially.
[a,b,n,m]=ndgrid(0:1,0:1,0:14,0:14);
ok=n>=a+8 & m>=b+4 & n+5<=14 & m+1<=6 & (n>=m+1 | m>=n+5);
starts=[a(ok),b(ok),n(ok),m(ok)]/1000;
expected=[repmat([2 2 1 2],size(starts,1),1) starts; repmat([2 2 2 1],size(starts,1),1) starts];
add('independent_cartesian_18',size(expected,1)==18 && isequal(size(expected),size(lib.rows)) && ...
    max(abs(sortrows(expected)-sortrows(lib.rows)),[],'all')<=c.time_tol,'Independent mask matched within declared time tolerance; division and multiplication need not be bit-identical');
add('only_HH_90mJ',all(lib.mode_id==4) && max(abs(lib.energy-.09))<1e-10,'Deadline removes low-frequency choices');
add('sanitized_policy_input',~isfield(trials,'predeclared_witnesses_ms') && ~isfield(c,'predeclared_action_order'),'Only case and thermal structures');
for k=1:numel(trials)
    z=trials(k); labels={'C1','witness','reference'};
    z.case.budget_s=-1;
    p=c44_policy(z,'C1'); w=p47_witness(z); r=p47_reference(z,p);
    for j=1:3
        results={p,w,r}; add([z.id '_timeout_' labels{j}],strcmp(results{j}.status,'timeout'),'Fixture only; never inferred infeasible');
    end
end
% Partial state must include A's future committed work but not unstarted B/NPU.
s=c44_schedule(c); s=c44_commit(c,s,[2 2 1 2 0 .001 .008 .005],0);
z=c44_thermal(c,s,trials(1).thermal);
add('committed_single_safe',strcmp(z.status,'safe') && isequal(isfinite(s.start),[true false false false]),'No future schedule injected');
keep=c44_prefix(c,lib.rows,s,0,true);
add('actual_prefix_has_two_suffixes',sum(keep)==2,'CPU label is fixed in actual prefix');
checks=table(names',logical(values'),notes','VariableNames',{'name','passed','note'});
    function add(n,v,t), names{end+1}=n; values(end+1)=v; notes{end+1}=t; end
end
