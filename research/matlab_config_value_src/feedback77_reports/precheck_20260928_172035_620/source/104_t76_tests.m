function checks=t76_tests(trials)
names={};passed=[];details={};
tr=trials(strcmp({trials.id},'P_high_D6_hot'));c=tr.case;h=tr.thermal;
fixture=c;fixture.deadline=[.010 .010];p=b68_build(fixture);
fr=[2 5 2 1 4 5 4 3 0 1 2 5 0 2 3 5];
s=s55_schedule(fixture,fr);v=s55_validate(fixture,s);record('fixture_legal_noninteger_end',v.feasible && abs(s.finish(4)-.00625)<1e-12);
ids=t76_option_ids(fixture,p.columns,fr);times=[0 .0005 .001 .002 .003 .004 .005 .00625 .0081 .020];
net=thv_build(h);maxdiff=0;enclosed=true;
for t=times
 exact=point_nominal(fixture,s,h,net,t,false);
 for node=1:2
  row=t76_coefficients(fixture,h,p.columns,t,node);
  box=t76_iv('add',row.baseline_interval,t76_iv('sum',row.pulse_interval(ids,:)));
  enclosed=enclosed && exact(node)>=box(1) && exact(node)<=box(2);
  maxdiff=max(maxdiff,abs(mean(box)-exact(node)));
 end
end
record('option_superposition_vs_segment_propagation',enclosed,sprintf('max midpoint difference %.3g C',maxdiff));
ode=point_nominal(fixture,s,h,net,.020,true);nom=point_nominal(fixture,s,h,net,.020,false);
record('independent_piecewise_ODE',max(abs(ode-nom))<1e-7,sprintf('max %.3g C',max(abs(ode-nom))));
row=t76_coefficients(fixture,h,p.columns,.0081,1);
record('all_option_response_nonnegative',all(row.pulse_interval>=0,'all'));
record('external_power_not_node_heat',same_without_external(fixture,h,p.columns));
% Dedicated constant-input two-mode segment with a strict internal peak.
% CPU theta=30+30*z-20*z^2, z=exp(-20*t); vertex z=.75.
z=thv_step(net,[40;60],[2;0],.05);
record('continuous_internal_peak_supported',any(z.peak_time>0 & z.peak_time<.05));
record('internal_peak_analytic_value',abs(z.peak(1)-41.25)<1e-10 && abs(z.peak_time(1)+log(.75)/20)<1e-10);
en=s55_energy(fixture,s);record('energy_dual_integral',en.error_J<1e-12);
% Historical test witness only; not passed to either formal diagnostic.
bad=[2 2 2 2 4 5 4 4 0 1 3 5 0 1 2 4];good=bad;good(16)=5;
p6=b68_build(c);sel=t76_option_ids(c,p6.columns,[bad;good]);
tb=b64_thermal(c,s55_schedule(c,bad),h);tg=b64_thermal(c,s55_schedule(c,good),h);
record('historical_same_configuration_unsafe_and_wait_safe',strcmp(tb.status,'violation') && strcmp(tg.status,'safe'));
cut=t76_cut(c,h,p6.columns,sel(1,:),tb);
record('source_point_independently_excluded',strcmp(cut.kind,'temperature_row') && cut.source_lhs_interval(1)>cut.row.rhs_upper);
caught=false;try,t76_cut(c,h,p6.columns,repmat(sel(1,1),1,c.n),tb);catch,caught=true;end
record('repeated_selection_rejected',caught);
value=t76_point(cut.row,sel(2,:));record('same_configuration_safe_wait_preserved',value(2)<=cut.row.rhs_upper);
swap=bad;for i=1:8,if swap(i)==2,swap(i)=4;elseif swap(i)==4,swap(i)=2;end,end
ss=t76_option_ids(c,p6.columns,swap);value=t76_point(cut.row,ss);
record('global_CPU_swap_same_point_response',value(1)>cut.row.rhs_upper);
[orb,~]=t76_orbits(c,[bad;swap;good]);record('global_label_orbit_not_arbitrary_mapping',orb(1)==orb(2) && orb(1)~=orb(3));
u=tb;u.status='unresolved';cu=t76_cut(c,h,p6.columns,sel(1,:),u);record('unresolved_never_excluded',strcmp(cu.kind,'none'));
u=tb;u.peak_time=[0 0];cu=t76_cut(c,h,p6.columns,sel(1,:),u);record('nominal_time_not_violation_certificate',strcmp(cu.kind,'no_good'));
hf=h;hf.limit=[mean([tb.peak_lower(1),tb.peak_upper(1)]) 100];tu=b64_thermal(c,s55_schedule(c,bad),hf);
record('actual_peak_band_unresolved',strcmp(tu.status,'unresolved'));
hf=h;hf.capacity=[.003 .0025];caught=false;try,t76_coefficients(c,hf,p6.columns,.006,1);catch e,caught=strcmp(e.identifier,'t76:RC');end
record('unsupported_RC_rejected',caught);
caught=false;try,s55_budget(struct('timer',tic,'limit',60,'inject_phase','test76'),'test76');catch e,caught=strcmp(e.identifier,'s55:timeout');end
record('budget_exception_recognized',caught);
x=t76_iv('expneg',[0 1]);record('Taylor_full_declared_domain',x(1)<=exp(-1) && x(2)>=1);
checks=table(string(names(:)),logical(passed(:)),string(details(:)),'VariableNames',{'check','passed','detail'});
 function record(name,ok,detail)
  if nargin<3,detail='';end
  names{end+1}=name;passed(end+1)=ok;details{end+1}=detail;
 end
end
function yes=same_without_external(c,h,cols)
a=t76_coefficients(c,h,cols,.006,1);c.external=100;b=t76_coefficients(c,h,cols,.006,1);yes=isequal(a,b);
end
function temp=point_nominal(c,s,h,net,t,useODE)
events=unique([0 t s.start(s.start<t) s.finish(s.finish<t)]);theta=h.initial(:)-h.ambient;
for k=1:numel(events)-1
 a=events(k);b=events(k+1);mid=(a+b)/2;ix=find(s.start<=mid & mid<s.finish);kind=c.unit_kind(s.unit(ix));
 power=[c.idle_cpu+sum(s.increment(ix(kind==1)));c.idle_npu+sum(s.increment(ix(kind==2)))];
 if useODE
  [~,y]=ode45(@(~,x)net.A*x+net.C\power,[a b],theta,odeset('RelTol',1e-11,'AbsTol',1e-12));theta=y(end,:)';
 else,z=thv_step(net,theta,power,b-a);theta=z.finish;end
end
temp=theta+h.ambient;
end
