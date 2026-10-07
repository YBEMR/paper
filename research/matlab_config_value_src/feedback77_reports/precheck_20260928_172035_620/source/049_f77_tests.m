function [checks,fixtures]=f77_tests(trials,folder)
names={};passed=[];notes={};fixtures={};
% Reuse coverage, numerical and continuous-thermal checks without old edits.
old=b68_tests(trials);
for j=1:height(old),add(['b68_' old.name{j}],old.passed(j),old.note{j});end
old=t76_tests(trials);
for j=1:height(old),add(['t76_' char(old.check(j))],old.passed(j),char(old.detail(j)));end
c=trials(1).case;h=trials(1).thermal;
f=c;f.n=2;f.request=[1 2];f.pred={[],[]};f.terminal=[1 2];f.stage_id={'A','B'};
f.deadline=[.003 .003];f.window=.004;f.release=[0 0];f.budget_s=15;f.id='fixture77';
f.options={ [1 1 .001 1;2 1 .001 1;1 2 .00125 2], [1 1 .001 1;2 1 .001 1;3 3 .001 1] };
tr=struct('case',f,'thermal',h,'id',f.id,'cohort','precheck');
a=b68_method(tr);b=f77_method(tr,struct('test_only',true,'variant','no_good'));fixtures=[fixtures {a b}];
add('no_good_compatibility',a.upper_J==b.upper_J && a.lower_J==b.lower_J && strcmp(a.status,b.status) && a.stats.cuts==b.stats.cuts,'Actual solver, unchanged legal domain and objective');
add('no_good_schedule_compatibility',isequaln(a.schedule,b.schedule),'Deterministic local fixture; not a general tie guarantee');
p=b68_build(f);row=[1 3 0 0];sel=t76_option_ids(f,p.columns,row);
taut=struct('coefficient_lower',ones(numel(p.f),1),'rhs_upper',f.n);
q=f77_rows({taut},sel);add('row_interval_unresolved',numel(q.unresolved)==1 && isempty(q.violated),'Exact equality enclosed');
easy=taut;easy.rhs_upper=f.n+1;q=f77_rows({easy},sel);add('row_interval_satisfied',isempty(q.unresolved) && isempty(q.violated),'Outward upper sum below rhs');
wrong=taut;wrong.rhs_upper=f.n-1;q=f77_rows({wrong},sel);add('row_interval_violated',numel(q.violated)==1,'Outward lower sum above rhs');
b=f77_method(tr,struct('test_only',true,'initial_rows',{{taut}},'replay_rows',row));fixtures{end+1}=b;
add('safe_with_row_unresolved_can_close_L0',isfinite(b.upper_J) && b.optimal_value_proved && b.stats.row_unresolved>0,'Full trajectory, independent L0, not a row-equality certificate');
b=f77_method(tr,struct('test_only',true,'initial_rows',{{wrong}},'replay_rows',row));fixtures{end+1}=b;
add('row_thermal_contradiction_rejected',strcmp(b.status,'numeric_unresolved') && ~isfinite(b.upper_J),'Deliberately invalid injected row must not accept safe witness');
% A legal safe row with nonminimal energy tests unresolved final status.
expensive=[3 3 0 0];
b=f77_method(tr,struct('test_only',true,'initial_rows',{{taut}},'replay_rows',expensive));fixtures{end+1}=b;
add('safe_U_preserved_final_row_unresolved',strcmp(b.status,'numeric_unresolved') && isfinite(b.upper_J) && ~b.optimal_value_proved && ~isempty(b.unresolved),'Solver flag retained separately');
% Historical test pair, never provided to frozen solver calls.
hot=trials(strcmp({trials.id},'P_high_D6_hot'));
bad=[2 2 2 2 4 5 4 4 0 1 3 5 0 1 2 4];good=bad;good(16)=5;
b=f77_method(hot,struct('test_only',true,'replay_rows',[bad;good]));fixtures{end+1}=b;
add('replay_violation_row_then_safe',isfinite(b.upper_J) && b.stats.thermal_rows==1 && b.stats.no_goods==0 && b.stats.rounds==2,'Scripted candidate stream, genuine full thermal evaluation');
alloc=cellfun(@(z)z.allocated_s,b.rounds);add('replay_shared_budget',all(diff(alloc)<0),'Remaining allocation never reset');
b=f77_method(hot,struct('test_only',true,'replay_rows',[bad;bad;good]));fixtures{end+1}=b;
add('cache_hit_rechecks_new_rows',b.stats.cache_hits>=1 && b.stats.row_violations>=1 && b.stats.thermal_calls==2,'Invariant trajectory cache, fresh row check');
add('duplicate_row_falls_back_integer',b.stats.thermal_rows==1 && b.stats.no_goods==1 && b.stats.duplicate_rows==1 && isfinite(b.upper_J),'No infinite identical-cut restart');
b=f77_method(hot,struct('test_only',true,'replay_rows',[bad;bad;bad]));fixtures{end+1}=b;
add('integer_no_good_violation_stops',strcmp(b.status,'numeric_unresolved') && b.stats.rounds==3 && b.stats.no_goods==1,'Exact matrix check intercepts third repeated candidate');
b=f77_method(hot,struct('test_only',true,'replay_rows',[bad;good],'point_at_zero',true));fixtures{end+1}=b;
add('point_certificate_fallback',b.stats.no_goods==1 && b.stats.thermal_rows==0 && b.stats.fallbacks==1 && isfinite(b.upper_J),'Global violation remains certified');
% Actual intlinprog re-solve after adding a constant invalid-at-entry thermal row.
one=f;one.n=1;one.request=1;one.pred={[]};one.terminal=1;one.stage_id={'X'};one.release=0;
one.window=.02;one.deadline=.002;one.options={[1 1 .001 0]};one.id='fixture77_initial_hot';
hh=h;hh.initial=[81 81];tt=struct('case',one,'thermal',hh);
b=f77_method(tt);fixtures{end+1}=b;
add('actual_solver_thermal_row_restart',strcmp(b.status,'solver_reported_infeasible') && b.stats.thermal_rows==1 && b.stats.rounds==2 && ~b.grid_infeasible_proved,'Solver infeasibility is not an independent integer certificate');
hh.initial=[80 80];tt.thermal=hh;b=f77_method(tt);fixtures{end+1}=b;
add('full_thermal_unresolved_no_cut',strcmp(b.status,'numeric_unresolved') && b.stats.cuts==0 && ~isempty(b.unresolved),'No exclusion from threshold band');
for phase={'input','build','thermal_after','row_check','accept'}
 b=f77_method(tr,struct('test_only',true,'phase',phase{1},'replay_rows',row));fixtures{end+1}=b;
 add(['timeout_' phase{1}],strcmp(b.status,'timeout') && ~isfinite(b.upper_J),'No late safety evidence');
end
for phase={'cut_before','cut_construct','cut_constructed','cut_before_commit'}
 b=f77_method(hot,struct('test_only',true,'phase',phase{1},'replay_rows',bad));fixtures{end+1}=b;
 add(['timeout_' phase{1}],strcmp(b.status,'timeout') && b.stats.cuts==0 && isempty(b.cuts),'No uncommitted feedback counted');
end
b=f77_method(tr,struct('test_only',true,'phase','returned_candidate','replay_rows',row));fixtures{end+1}=b;
add('post_accept_timeout_retains_evidence',strcmp(b.status,'timeout') && isfinite(b.upper_J) && b.first_safe_s<=f.budget_s,'Proof formed before interruption');
late=a;late.bound_trace(:,1)=100;late=f77_budget_audit(late,0,101,60);
add('outer_clock_rejects_late_best',~isfinite(late.upper_J) && late.budget_evidence_ambiguous && ~isempty(late.budget_late_output),'Original evidence preserved but not ranked');
crossing=a;crossing.elapsed_s=59.5;crossing.bound_trace(:,1)=59.4;
crossing=f77_budget_audit(crossing,.1,60.2,60);
add('outer_offset_upper_controls_admission',~isfinite(crossing.upper_J) && crossing.budget_evidence_ambiguous,'59.4+0.1 fits; 59.4+0.7 does not');
lateStatus=a;lateStatus.elapsed_s=59.5;lateStatus.bound_trace(:,1)=1;
lateStatus=f77_budget_audit(lateStatus,.1,60.2,60);
add('late_status_not_promoted',isfinite(lateStatus.upper_J) && ~lateStatus.final_status_within_budget && ~lateStatus.final_solver_bound_within_budget && strcmp(lateStatus.status,'budget_stopped_with_evidence'),'Timely U preserved; solver termination remains raw');
ontime=f77_budget_audit(a,0,a.elapsed_s+.001,60);
df=b64_data(f);ontime.common_L0_J=(df.base+sum(df.minE))*df.energy_unit;
add('outer_clock_preserves_timely_best',ontime.upper_J==a.upper_J && ~ontime.budget_evidence_ambiguous,'Common to both methods');
% Export smoke test uses isolated two-Stage fixtures, not any study results.
if nargin>1
 exportdir=fullfile(folder,'export_fixture');mkdir(exportdir);
 trials=tr;results={ontime ontime};methods={'no_good','thermal_row'}; %#ok<NASGU>
 save(fullfile(exportdir,'results.mat'),'trials','results','methods');f77_export(exportdir);
 add('export_fixture_safe_output',isfile(fullfile(exportdir,'summary.csv')) && isfile(fullfile(exportdir,'postchecks.csv')),'Independent export recheck without search');
end
src=fileread(which('f77_method'));
add('no_reference_candidates',~contains(src,'s55_enumerate(') && ~contains(src,'b64_search(') && ~contains(src,'thermal76_reports'),'No historical or reference schedule reads');
add('production_hooks_guarded',contains(src,'Explicit test-only gate required'),'Frozen entry never supplies inject');
checks=table(names',logical(passed'),notes','VariableNames',{'name','passed','note'});
 function add(name,ok,note),names{end+1}=name;passed(end+1)=ok;notes{end+1}=note;end
end
