function r=f77_method(tr,inject)
% 68 control flow, with integer structure and floating thermal rows separated.
clock=tic;if nargin<2,inject=struct();end
testOnly=~isempty(fieldnames(inject));if testOnly,assert(isfield(inject,'test_only') && inject.test_only,'f77:hooks','Explicit test-only gate required');end
variant='thermal_row';if isfield(inject,'variant'),variant=inject.variant;end
c=tr.case;h=tr.thermal;budget=c.budget_s;d=b64_data(c);L0=d.base+sum(d.minE);
U=Inf;best=[];first=NaN;status='running';message='';roundNo=0;internal=NaN;
events={};cuts={};rounds={};boundlog=zeros(0,6);trace=[0 L0 Inf];callbackFields={};heatRows={};
cache=containers.Map('KeyType','char','ValueType','any');callbackError=[];pending=[];
stats=struct('candidates',0,'cache_hits',0,'thermal_calls',0,'cuts',0,'callbacks',0,'rounds',0,'bound_conflicts',0, ...
 'thermal_rows',0,'no_goods',0,'fallbacks',0,'duplicate_rows',0,'row_violations',0,'row_unresolved',0);
cost=struct('build',0,'solver_inclusive',0,'thermal',0,'decode',0,'cut',0,'row_check',0);
opts=optimoptions('intlinprog','Display','off','AbsoluteGapTolerance',0,'RelativeGapTolerance',0, ...
 'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6,'OutputFcn',@callback);
try
 check('input');buildTimer=tic;p=b68_build(c,@()check('build'));cost.build=toc(buildTimer);
 % p.A remains the exact structural + integer no-good matrix.
 Aall=p.A;ball=p.b;
 if isfield(inject,'initial_rows')
  heatRows=inject.initial_rows;
  for j=1:numel(heatRows),Aall=[Aall;sparse(heatRows{j}.coefficient_lower')];ball=[ball;heatRows{j}.rhs_upper];end
 end
 if p.empty_stage,status='independent_infeasible';else
 while strcmp(status,'running')
  check('round');roundNo=roundNo+1;stats.rounds=roundNo;opts.MaxTime=budget-toc(clock);check('before_solver');
  allocated=opts.MaxTime;solveTimer=tic;
  if isfield(inject,'replay_rows')
   % Deterministic branch fixture only; no production caller supplies inject.
   assert(roundNo<=size(inject.replay_rows,1),'f77:fixture','Replay exhausted');
   selected=t76_option_ids(c,p.columns,inject.replay_rows(roundNo,:));x=zeros(numel(p.f),1);x(selected)=1;
   fval=p.f'*x;flag=1;output=struct('test_only_replay',true);
  else
   [x,fval,flag,output]=intlinprog(p.f,1:numel(p.f),Aall,ball,p.Aeq,p.beq,zeros(numel(p.f),1),ones(numel(p.f),1),[],opts);
  end
  cost.solver_inclusive=cost.solver_inclusive+toc(solveTimer);
  rounds{end+1}=struct('round',roundNo,'allocated_s',allocated,'returned_s',toc(clock),'exitflag',flag,'fval',fval,'output',output); %#ok<AGROW>
  if ~isempty(callbackError),rethrow(callbackError);end
  check('solver_return');
  q=[];if ~isempty(x)
   q=evaluate(x,'return');
   if isfield(inject,'repeat_candidate') && inject.repeat_candidate,evaluate(x,'injected_duplicate');end
  end
  check('returned_candidate');
  if isfinite(U) && U==L0,status='independent_optimal';break;end
  if flag~=1
   if flag==-2,status='solver_reported_infeasible';if isfinite(U),status='numeric_unresolved';message='Solver infeasible conflicts with retained safe witness';end
   elseif flag==3 || flag==-9,status='numeric_unresolved';
   else,status='solver_stopped';end
   break;
  end
  assert(~isempty(q),'b68:numeric','Converged without candidate');
  if strcmp(q.thermal.status,'safe')
   if isempty(q.row_check.unresolved),status='solver_converged_safe';
   else,pending=q;status='numeric_unresolved';message='Safe trajectory retained; final thermal-row comparison unresolved';end
   break;
  elseif strcmp(q.thermal.status,'unresolved'),pending=q;status='numeric_unresolved';break;end
  cutTimer=tic;check('cut_before');
  proposal=f77_feedback(c,h,p.columns,q,heatRows,variant,@()check('cut_construct'),inject);
  check('cut_constructed');
  if strcmp(proposal.kind,'temperature_row')
   newrow=sparse(proposal.row.coefficient_lower');newrhs=proposal.row.rhs_upper;
  else
   newrow=sparse(1,q.selected,ones(1,numel(q.selected)),1,numel(p.f));newrhs=c.n-1;
  end
  nextA=[Aall;newrow];nextb=[ball;newrhs];
  if strcmp(proposal.kind,'no_good'),nextStructA=[p.A;newrow];nextStructb=[p.b;newrhs];end
  check('cut_before_commit');stamp=within_budget();
  Aall=nextA;ball=nextb;
  if strcmp(proposal.kind,'temperature_row')
   heatRows{end+1}=proposal.row;stats.thermal_rows=stats.thermal_rows+1;
  else
   p.A=nextStructA;p.b=nextStructb;stats.no_goods=stats.no_goods+1;
   if strcmp(variant,'thermal_row'),stats.fallbacks=stats.fallbacks+1;end
  end
  stats.duplicate_rows=stats.duplicate_rows+proposal.duplicate;
  cuts{end+1}=struct('time_s',stamp,'round',roundNo,'selected',q.selected,'schedule',q.schedule, ...
   'peak_lower',q.thermal.peak_lower,'kind',proposal.kind,'reason',proposal.reason, ...
   'duplicate',proposal.duplicate,'existing_row_violation',proposal.existing_row_violation,'certificate',proposal.certificate); %#ok<AGROW>
  stats.cuts=stats.cuts+1;cost.cut=cost.cut+toc(cutTimer);
 end
 end
catch err
 message=getReport(err,'extended','hyperlinks','off');
 if strcmp(err.identifier,'b68:timeout'),status='timeout';
 elseif strcmp(err.identifier,'b68:numeric') || strcmp(err.identifier,'f77:numeric'),status='numeric_unresolved';
 elseif contains(lower(err.message),'out of memory') || strcmp(err.identifier,'b68:resource'),status='resource_unresolved';
 else,status='error';end
end
elapsed=toc(clock);trace(end+1,:)=[elapsed L0 U];
r=struct('input_id',c.id,'method','thermal_row','status',status,'message',message,'schedule',best, ...
 'lower_J',L0*d.energy_unit,'upper_J',U*d.energy_unit,'solver_bound_J',internal*d.energy_unit, ...
 'optimal_value_proved',isfinite(U) && U==L0,'grid_infeasible_proved',strcmp(status,'independent_infeasible'), ...
 'optimal_set_complete',false,'coverage_valid',~strcmp(status,'error'),'elapsed_s',elapsed,'first_safe_s',first, ...
 'stats',stats,'cost_s',cost,'bound_trace',trace,'solver_trace',boundlog,'events',{events},'cuts',{cuts}, ...
 'rounds',{rounds},'unresolved',pending,'callback_fields',{callbackFields},'options_text',evalc('disp(opts)'), ...
 'thermal_rows',{heatRows},'test_hooks_used',testOnly,'variant',variant, ...
 'proof_scope','safe_U_and_independent_L0_only_solver_bounds_reported_separately');
if strcmp(status,'independent_infeasible'),r.lower_J=Inf;end
 function check(phase)
  if isfield(inject,'phase') && strcmp(inject.phase,phase),error('b68:timeout','Injected timeout at %s',phase);end
  if toc(clock)>budget,error('b68:timeout','Budget exhausted at %s',phase);end
 end
 function stamp=within_budget()
  stamp=toc(clock);if stamp>budget,error('b68:timeout','Budget exhausted before evidence commit');end
 end
 function q=evaluate(x,origin)
  check('candidate');decodeTimer=tic;[s,sel,E]=b68_decode(c,p,x);cost.decode=cost.decode+toc(decodeTimer);check('decoded');
  key=sprintf('%d,',sel);stats.candidates=stats.candidates+1;
  if isKey(cache,key),q=cache(key);stats.cache_hits=stats.cache_hits+1;
  else
   thermalTimer=tic;z=b64_thermal(c,s,h);cost.thermal=cost.thermal+toc(thermalTimer);stats.thermal_calls=stats.thermal_calls+1;
   q=struct('selected',sel,'schedule',s,'energy',E,'thermal',z);check('thermal_after');cache(key)=q;
  end
  % Cache stores only invariant complete-trajectory evidence, not row legality.
  rowTimer=tic;q.row_check=f77_rows(heatRows,sel,@()check('row_check'));cost.row_check=cost.row_check+toc(rowTimer);
  stats.row_violations=stats.row_violations+numel(q.row_check.violated);stats.row_unresolved=stats.row_unresolved+numel(q.row_check.unresolved);
  assert(~(strcmp(q.thermal.status,'safe') && ~isempty(q.row_check.violated)), ...
   'f77:numeric','Certified safe trajectory contradicts a certified thermal-row violation');
  check('accept');stamp=within_budget();
  if strcmp(q.thermal.status,'safe') && E<U
   U=E;best=s;if isnan(first),first=stamp;end
   trace(end+1,:)=[stamp L0 U]; %#ok<AGROW>
  end
  events{end+1}=struct('time_s',stamp,'round',roundNo,'origin',origin,'energy_units',E,'selected',sel, ...
   'thermal_status',q.thermal.status,'row_check',q.row_check); %#ok<AGROW>
  if isfinite(internal) && isfinite(U) && internal>U+1e-7,stats.bound_conflicts=stats.bound_conflicts+1;end
 end
 function stop=callback(x,v,state)
  stop=false;
  try
   check('callback');stats.callbacks=stats.callbacks+1;callbackFields=union(callbackFields,fieldnames(v));
   lb=NaN;fv=NaN;gap=NaN;nodes=NaN;
   if isfield(v,'lowerbound') && ~isempty(v.lowerbound) && isfinite(v.lowerbound)
    lb=v.lowerbound+d.base;if isnan(internal),internal=lb;else,internal=max(internal,lb);end
   end
   if isfield(v,'fval') && ~isempty(v.fval),fv=v.fval+d.base;end
   if isfield(v,'relativegap') && ~isempty(v.relativegap),gap=v.relativegap;end
   if isfield(v,'numnodes') && ~isempty(v.numnodes),nodes=v.numnodes;end
   boundlog(end+1,:)=[toc(clock) roundNo lb fv gap nodes]; %#ok<AGROW>
   if ~isempty(x) && isfield(v,'phase') && ismember(v.phase,{'heuristics','branching'}),evaluate(x,['callback_' state]);end
   check('callback_end');stop=isfinite(U) && U==L0;
  catch err,callbackError=err;stop=true;end
 end
end
