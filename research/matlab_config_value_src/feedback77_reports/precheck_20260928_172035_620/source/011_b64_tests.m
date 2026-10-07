function checks=b64_tests(trials)
names={};passed=[];notes={};c=trials(1).case;h=trials(1).thermal;
old=s55_tests(trials);for i=1:height(old),add(['legacy_' old.name{i}],old.passed(i),old.note{i});end
for i=1:numel(trials),d=b64_data(trials(i).case);add(['lattice_' trials(i).id],d.g==4 && d.w==80,'Exact quarter-ms units, starts every four units');end
f=c;f.n=2;f.request=[1 2];f.pred={[],[]};f.terminal=[1 2];f.stage_id={'A','B'};
f.deadline=[.003 .003];f.window=.004;f.release=[0 0];f.budget_s=10;
f.options={ [1 1 .001 1;2 1 .001 1;1 2 .00125 2], [1 1 .001 1;2 1 .001 1;3 3 .001 1] };
truth=oracle(f);rows=b64_cover(f);
add('independent_cartesian_coverage',isequal(rows,truth),sprintf('%d complete tuples',size(rows,1)));
add('unique_orientation_coverage',size(unique(rows,'rows'),1)==size(rows,1),'No duplicate leaves');
add('B_first_wait_and_concurrent',any(rows(:,4)<rows(:,3)) && any(all(rows(:,3:4)>0,2)) && any(rows(:,3)==rows(:,4)),'All time patterns retained');
g=f;g.pred={[],1};add('dependency_coverage',isequal(b64_cover(g),oracle(g)),'Independent enumeration');
g=f;g.domain=[1 2 0];add('independent_domain_coverage',isequal(b64_cover(g),oracle(g)),'Cross-frequency overlap allowed in different domains');
variants={'full','no_repair','simple_order','bare'};
expected=Inf;for k=1:size(truth,1),e=s55_energy(f,s55_schedule(f,truth(k,:)));expected=min(expected,e.sum_J);end
for j=1:4
 rr=b64_search(struct('case',f,'thermal',h),variants{j});
 add(['oracle_optimum_' variants{j}],rr.optimal_value_proved && abs(rr.upper_J-expected)<1e-12 && rr.lower_J<=expected+1e-12,'Same optimum despite ordering');
end
d=b64_data(f);N=b64_root(d);N.m=[1 1];N.adj(1,2)=true;N.s=[0 0];
[ok,~]=b64_propagate(d,N);add('fixed_start_not_shifted',~ok,'Fixed equality violation');
N.s=[NaN NaN];N.adj(2,1)=true;[ok,~]=b64_propagate(d,N);add('cycle_excluded',~ok,'Positive-duration cycle');
for phase={'input','popped','expand','child','commit','thermal_after','accept'}
 rr=b64_search(struct('case',f,'thermal',h),'full',struct('phase',phase{1}));
 add(['interrupt_' phase{1}],strcmp(rr.status,'timeout') && ~rr.optimal_value_proved && ~rr.grid_infeasible_proved && rr.lower_J<=expected+1e-12,'Active parent retains lower bound');
end
rr=b64_search(struct('case',f,'thermal',h),'full',struct('phase','child','identifier','b64:resource'));
add('resource_not_infeasible',strcmp(rr.status,'resource_unresolved') && ~rr.coverage_valid && rr.lower_J<=expected+1e-12,'Root lower bound retained');
% One-stage fixtures only; not research inputs.
one=f;one.n=1;one.request=1;one.pred={[]};one.terminal=1;one.stage_id={'X'};one.release=0;one.deadline=.008;one.window=.02;one.options={[1 2 .004 4]};
hot=h;hot.initial=[78 78];dd=b64_data(one);NN=b64_root(dd);NN.m=1;NN.phase=3;
[~,tt]=b64_propagate(dd,NN);ss=b64_schedule(dd,1,tt);z=b64_thermal(one,ss,hot);
add('clear_thermal_enclosure',all(z.peak_lower<=z.peak+1e-10) && all(z.peak_upper>=z.peak-1e-10) && strcmp(z.status,'violation'),'Outward interval encloses nominal analytic peak');
rr=b64_search(struct('case',one,'thermal',hot),'full');
add('single_step_repair_safe',rr.optimal_value_proved && rr.stats.repair_safe==1,'One independent delay succeeds');
one.options={[1 2 .004 8]};one.deadline=.018;
rr=b64_search(struct('case',one,'thermal',hot),'full');
add('repair_failure_retains_waiting',rr.optimal_value_proved && rr.stats.repair_trials>0 && rr.stats.repair_safe==0 && rr.schedule.start>.001,'Systematic multi-step wait remains');
% Entire initial state on threshold makes all low-power full leaves unresolved.
u=f;u.n=1;u.request=1;u.pred={[]};u.terminal=1;u.stage_id={'U'};u.release=0;u.deadline=.001;u.options={[1 1 .001 0]};
hu=h;hu.initial=[80 80];rr=b64_search(struct('case',u,'thermal',hu),'full');
add('full_unresolved_retained',strcmp(rr.status,'numeric_unresolved') && ~rr.grid_infeasible_proved && ~isempty(rr.unresolved),'No false thermal exclusion');
u.deadline=.0005;rr=b64_search(struct('case',u,'thermal',h),'full');
add('whole_noheat_infeasible',rr.grid_infeasible_proved,'No feasible isolated stage');
% Independent cross-check of all tiny schedules and warm/cold entrances.
width=0;contained=true;
for k=1:size(truth,1)
 s=s55_schedule(f,truth(k,:));z=b64_thermal(f,s,hot);
 contained=contained && all(z.peak>=z.peak_lower-1e-10) && all(z.peak<=z.peak_upper+1e-10);
 width=max(width,z.enclosure_width);
end
add('tiny_all_analytic_enclosures',contained && width<1e-6,sprintf('maximum enclosure width %.4g C',width));
% Reuse existing independent ODE, internal peak, half-open and legacy47 checks above.
checks=table(names',passed',notes','VariableNames',{'name','passed','note'});
    function add(name,yes,note),names{end+1}=name;passed(end+1)=logical(yes);notes{end+1}=note;end
end
function rows=oracle(c)
% Cartesian products independent of orientation propagation / b64_expand.
rows=zeros(0,2*c.n);assert(c.n==2);
for a=1:size(c.options{1},1)
 for b=1:size(c.options{2},1)
  for x=0:floor(c.window/c.grid)
   for y=0:floor(c.window/c.grid)
    row=[a b x y];s=s55_schedule(c,row);v=s55_validate(c,s);if v.feasible,rows(end+1,:)=row;end %#ok<AGROW>
   end
  end
 end
end
rows=sortrows(rows);
end
