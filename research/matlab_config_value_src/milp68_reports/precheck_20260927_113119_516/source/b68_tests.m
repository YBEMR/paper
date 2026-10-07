function checks=b68_tests(trials)
names={};passed=[];notes={};
add('optimization_license',license('test','Optimization_Toolbox')==1,'R2023b license test');
old=b64_tests(trials);for j=1:height(old),add(['reused_' old.name{j}],old.passed(j),old.note{j});end
c=trials(1).case;h=trials(1).thermal;
f=c;f.n=2;f.request=[1 2];f.pred={[],[]};f.terminal=[1 2];f.stage_id={'A','B'};
f.deadline=[.003 .003];f.window=.004;f.release=[0 0];f.budget_s=15;
f.options={ [1 1 .001 1;2 1 .001 1;1 2 .00125 2], [1 1 .001 1;2 1 .001 1;3 3 .001 1] };
for fixture=1:3
 g=f;if fixture==2,g.pred={[],1};elseif fixture==3,g.domain=[1 2 0];end
 p=b68_build(g);truth=[];encoded=[];
 for a=1:size(g.options{1},1)
  for b=1:size(g.options{2},1)
   for x=0:floor(g.window/g.grid)
    for y=0:floor(g.window/g.grid)
     row=[a b x y];s=s55_schedule(g,row);v=s55_validate(g,s);
     if v.feasible,truth(end+1,:)=row;end %#ok<AGROW>
     idx=[];for i=1:2
      q=find(p.columns(:,1)==i & p.columns(:,2)==row(i) & p.columns(:,3)==row(2+i)*p.d.g);idx=[idx;q]; %#ok<AGROW>
     end
     if numel(idx)==2
      yy=zeros(numel(p.f),1);yy(idx)=1;
      if all(p.A*yy<=p.b) && all(p.Aeq*yy==p.beq),encoded(end+1,:)=row;end %#ok<AGROW>
     end
    end
   end
  end
 end
 add(sprintf('independent_matrix_coverage_%d',fixture),isequal(sortrows(truth),sortrows(encoded)),sprintf('%d schedules',size(truth,1)));
end
p=b68_build(f);x=zeros(numel(p.f),1);x(p.groups{1}(1))=1;x(p.groups{2}(find(p.columns(p.groups{2},5)==3,1)))=1;
[s,sel,E]=b68_decode(f,p,x);ee=s55_energy(f,s);add('decode_energy_noninteger',ee.error_J<1e-12 && E>=p.L0,'Independent decode and energy');
bad=x;bad(sel(1))=.99;ok=false;try,b68_decode(f,p,bad);catch err,ok=strcmp(err.identifier,'b68:numeric');end
add('noninteger_rejected',ok,'No unsafe rounding');
bad=x;bad(sel(1))=1-5e-7;[s2,~,~]=b68_decode(f,p,bad);add('near_integer_rechecked',isequal(s,s2),'Rounded candidate undergoes exact matrix and full validation');
bad=x;bad(sel(1))=0;ok=false;try,b68_decode(f,p,bad);catch err,ok=strcmp(err.identifier,'b68:numeric');end
add('invalid_assignment_rejected',ok,'One mode per stage');
rr=b68_method(struct('case',f,'thermal',h));add('actual_solver_safe_L0',rr.optimal_value_proved && isfinite(rr.upper_J),rr.status);
add('actual_callback_fields',all(ismember({'lowerbound','fval','phase','time'},rr.callback_fields)) && rr.stats.callbacks>0,'Native R2023b callback');
add('duplicate_candidate_cache',rr.stats.cache_hits>0,'Callback/final repeated candidate');
u=f;u.options={ [1 1 .002 0;1 2 .002 1], [2 2 .002 0;2 1 .002 1] };u.deadline=[.002 .002];
rr=b68_method(struct('case',u,'thermal',h));add('safe_not_independent_optimum',strcmp(rr.status,'solver_converged_safe') && ~rr.optimal_value_proved && rr.upper_J>rr.lower_J,'Incompatible cheap frequencies force energy above L0');
one=f;one.n=1;one.request=1;one.pred={[]};one.terminal=1;one.stage_id={'X'};one.release=0;one.window=.02;one.deadline=.008;one.options={[1 2 .004 4]};
hot=h;hot.initial=[78 78];p=b68_build(one);states=cell(1,numel(p.f));
for j=1:numel(p.f),xx=zeros(numel(p.f),1);xx(j)=1;[ss,~,~]=b68_decode(one,p,xx);z=b64_thermal(one,ss,hot);states{j}=z.status;end
bad=find(strcmp(states,'violation'),1);good=find(strcmp(states,'safe'),1);row=sparse(1,bad,1,1,numel(p.f));
add('no_good_retains_same_configuration',~isempty(bad) && ~isempty(good) && row(good)==0 && row(bad)==1,'Only one start is excluded; safe waiting remains');
u=one;u.options={[1 1 .001 0]};u.deadline=.002;hot.initial=[81 81];
rr=b68_method(struct('case',u,'thermal',hot));add('outer_restarts_and_reported_infeasible',strcmp(rr.status,'solver_reported_infeasible') && ~rr.grid_infeasible_proved && rr.stats.cuts==2,'Two complete assignments, then numerical solver infeasibility');
alloc=cellfun(@(z)z.allocated_s,rr.rounds);add('remaining_budget_decreases',all(diff(alloc)<0),'No fresh 60 seconds on restart');
hot.initial=[80 80];rr=b68_method(struct('case',u,'thermal',hot));add('unresolved_not_cut',strcmp(rr.status,'numeric_unresolved') && rr.stats.cuts==0 && ~isempty(rr.unresolved) && ~rr.grid_infeasible_proved,'Threshold band remains');
u.deadline=.0005;rr=b68_method(struct('case',u,'thermal',h));add('empty_stage_independent_infeasible',rr.grid_infeasible_proved && rr.stats.rounds==0,'No legal option');
for phase={'input','build','callback','thermal_after'}
 rr=b68_method(struct('case',f,'thermal',h),struct('phase',phase{1}));
 add(['injected_' phase{1}],strcmp(rr.status,'timeout') && ~rr.optimal_value_proved && ~isfinite(rr.upper_J),'No post-deadline safety proof');
end
hot.initial=[81 81];u.deadline=.002;rr=b68_method(struct('case',u,'thermal',hot),struct('phase','cut'));
add('interrupted_restart_unresolved',strcmp(rr.status,'timeout') && ~rr.grid_infeasible_proved,'Cut interruption is not an exclusion proof of all schedules');
src=fileread(which('b68_method'));add('no_reference_or_search_candidates',~contains(src,'b64_search(') && ~contains(src,'s55_enumerate(') && ~contains(src,'search64_reports'),'Only shared evaluation functions');
checks=table(names',passed',notes','VariableNames',{'name','passed','note'});
    function add(n,p,note),names{end+1}=n;passed(end+1)=logical(p);notes{end+1}=note;end
end
