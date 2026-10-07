function [checks,fixtures,certificate]=p78_tests(trials,rules,base,folder)
[checks,fixtures]=f77_tests(base,folder);
names={};passed=[];notes={};
for k=1:numel(trials)
 t=trials(k);b=base(strcmp({base.id},t.base_id));c=t.case;c.id=b.case.id;h=t.thermal;h.initial=b.thermal.initial;
 add(sprintf('p78_only_initial_%02d',k),isequaln(c,b.case) && isequaln(h,b.thermal),'No model or numeric changes beyond ID/initial');
 p=b68_build(t.case);q=b68_build(b.case);p.d.id=q.d.id;
 add(sprintf('p78_same_MILP_%02d',k),isequaln(p,q),'Initial thermal state never changes first master MILP');
end
add('p78_call_counts',sum([rules.calls.trial_index]==1)==2 && sum([rules.calls.trial_index]>1)==64,'Diagnostic separated');
for rep=1:2
 for i=2:17
  ix=find([rules.calls.repeat]==rep & [rules.calls.trial_index]==i);
  if rep==1,expected={'no_good','thermal_row'};else,expected={'thermal_row','no_good'};end
  add(sprintf('p78_call_order_%d_%02d',rep,i),isequal({rules.calls(ix).method},expected),'Balanced order, not randomized candidates');
 end
end
% Discovery schedules exist only in precheck; never passed to either method.
t=trials(1);c=t.case;h=t.thermal;p=b68_build(c);
bad=[2 5 2 4 4 5 4 2 0 2 3 5 0 1 2 5];
good=[2 5 2 2 2 5 4 4 0 1 2 5 1 2 3 5];
sb=s55_schedule(c,bad);sg=s55_schedule(c,good);
vb=s55_validate(c,sb);vg=s55_validate(c,sg);
add('p78_discovery_legal',vb.feasible && vg.feasible,'Both complete original-domain schedules');
iv=@(x)t76_iv('wide',x);pt=@(x)t76_iv('point',x);
addv=@(a,b)t76_iv('add',a,b);mul=@(a,b)t76_iv('mul',a,b);sub=@(a,b)t76_iv('sub',a,b);
expv=@(x)t76_iv('expneg',t76_iv('nonnegative',iv(x)));
e20=expv(.02);e40=expv(.04);
% Independent point formula from [0,1ms) pCPU=4.2, pNPU=.3, T0=78.
at78=sub(addv(pt(89.5),mul(pt(8),e20)),mul(pt(19.5),e40));
delta=sub(iv(h.initial(1)),pt(78));point=addv(at78,mul(delta,e20));
add('p78_discovery_fixed_point_violation',point(1)>80+h.band,'Not nominal peak time paired with global peak lower');
old=h;old.initial=[78 78];oldGood=b64_thermal(c,sg,old);
safeBound=addv(iv(max(oldGood.peak_upper)),delta);
add('p78_discovery_monotone_full_bound',safeBound(2)<80-h.band,'Old whole-window bound + positive common initial increment');
newBad=b64_thermal(c,sb,h);newGood=b64_thermal(c,sg,h);
add('p78_discovery_full_evaluation',strcmp(newBad.status,'violation') && strcmp(newGood.status,'safe'),'Full continuous envelope including idle tail');
ids=t76_option_ids(c,p.columns,bad);r=t76_coefficients(c,h,p.columns,.001,1);
sumiv=t76_iv('sum',r.pulse_interval(ids,:));sumiv=addv(r.baseline_interval,sumiv);
add('p78_point_superposition',max(point(1),sumiv(1))<=min(point(2),sumiv(2)) && sumiv(1)>80+h.band,'Independent analytic point and all-option coefficients agree');
for temp=[78 79 79.5 79.75]
 ht=h;ht.initial=[temp temp];dd=sub(pt(temp),pt(78));
 for tm=[0 .001 .006 .02]
  for node=1:2
   ro=t76_coefficients(c,old,p.columns,tm,node);rn=t76_coefficients(c,ht,p.columns,tm,node);
   expected=addv(ro.baseline_interval,mul(dd,expv(20*tm)));
   ok=isequal(ro.pulse_interval,rn.pulse_interval) && max(expected(1),rn.baseline_interval(1))<=min(expected(2),rn.baseline_interval(2));
   add(sprintf('p78_initial_shift_%g_%g_%d',temp,tm,node),ok,'Only baseline shifts by delta exp(-20t)');
  end
 end
end
certificate=struct('test_only',true,'initial_C',h.initial,'bad_row',bad,'good_row',good, ...
 'point_time_s',.001,'independent_point_interval_C',point,'superposition_point_interval_C',sumiv, ...
 'old_good_peak_upper_C',oldGood.peak_upper,'whole_window_safe_bound_C',safeBound, ...
 'new_bad',newBad,'new_good',newGood,'meaning','Discovery justification, not a solver hint or performance result');
% Smoke export from a small fixture already solved during inherited checks.
if nargin>3
 oldfixture=load(fullfile(folder,'export_fixture','results.mat'));
 rr=oldfixture.results{1};tt=oldfixture.trials;tt.base_id='export_fixture';tt.initial_C=tt.thermal.initial;
 rec=struct('trial_index',1,'repeat',1,'method','no_good','call_index',1,'result',rr);
 records={rec};savefolder=fullfile(folder,'p78_export_fixture');mkdir(savefolder);
 save(fullfile(savefolder,'results.mat'),'records');trials=tt;save(fullfile(savefolder,'results.mat'),'trials','-append');
 p78_export(savefolder);
 add('p78_export_smoke',isfile(fullfile(savefolder,'summary.csv')) && isfile(fullfile(savefolder,'postchecks.csv')),'No research call, saved fixture only');
end
checks=[checks;table(names',logical(passed'),notes','VariableNames',{'name','passed','note'})];
 function add(name,ok,note),names{end+1}=name;passed(end+1)=ok;notes{end+1}=note;end
end
