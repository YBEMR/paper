function r=b68_method(tr,inject)
% Engineering MILP reference. Only verified complete assignments are excluded.
clock=tic;if nargin<2,inject=struct();end
c=tr.case;h=tr.thermal;budget=c.budget_s;d=b64_data(c);L0=d.base+sum(d.minE);
U=Inf;best=[];first=NaN;status='running';message='';roundNo=0;internal=NaN;
events={};cuts={};rounds={};boundlog=zeros(0,6);trace=[0 L0 Inf];callbackFields={};
cache=containers.Map('KeyType','char','ValueType','any');callbackError=[];pending=[];
stats=struct('candidates',0,'cache_hits',0,'thermal_calls',0,'cuts',0,'callbacks',0,'rounds',0,'bound_conflicts',0);
cost=struct('build',0,'solver_inclusive',0,'thermal',0,'decode',0,'cut',0);
opts=optimoptions('intlinprog','Display','off','AbsoluteGapTolerance',0,'RelativeGapTolerance',0, ...
 'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6,'OutputFcn',@callback);
try
 check('input');timer=tic;p=b68_build(c,@()check('build'));cost.build=toc(timer);
 if p.empty_stage,status='independent_infeasible';else
 while strcmp(status,'running')
  check('round');roundNo=roundNo+1;stats.rounds=roundNo;opts.MaxTime=budget-toc(clock);check('before_solver');
  allocated=opts.MaxTime;timer=tic;
  [x,fval,flag,output]=intlinprog(p.f,1:numel(p.f),p.A,p.b,p.Aeq,p.beq,zeros(numel(p.f),1),ones(numel(p.f),1),[],opts);
  cost.solver_inclusive=cost.solver_inclusive+toc(timer);
  rounds{end+1}=struct('round',roundNo,'allocated_s',allocated,'returned_s',toc(clock),'exitflag',flag,'fval',fval,'output',output); %#ok<AGROW>
  if ~isempty(callbackError),rethrow(callbackError);end
  check('solver_return');
  if isfinite(U) && U==L0,status='independent_optimal';break;end
  q=[];if ~isempty(x),q=evaluate(x,'return');end
  check('returned_candidate');
  if isfinite(U) && U==L0,status='independent_optimal';break;end
  if flag~=1
   if flag==-2,status='solver_reported_infeasible';if isfinite(U),status='numeric_unresolved';message='Solver infeasible conflicts with retained safe witness';end
   elseif flag==3 || flag==-9,status='numeric_unresolved';
   else,status='solver_stopped';end
   break;
  end
  assert(~isempty(q),'b68:numeric','Converged without candidate');
  if strcmp(q.thermal.status,'safe'),status='solver_converged_safe';break;
  elseif strcmp(q.thermal.status,'unresolved'),pending=q;status='numeric_unresolved';break;
  end
  % No-good removes only the complete selected assignment, not its modes.
  timer=tic;row=sparse(1,q.selected,ones(1,numel(q.selected)),1,numel(p.f));
  p.A=[p.A;row];p.b=[p.b;c.n-1];check('cut');cost.cut=cost.cut+toc(timer);
  cuts{end+1}=struct('time_s',toc(clock),'round',roundNo,'selected',q.selected,'schedule',q.schedule,'peak_lower',q.thermal.peak_lower); %#ok<AGROW>
  stats.cuts=stats.cuts+1;
 end
 end
catch err
 message=getReport(err,'extended','hyperlinks','off');
 if strcmp(err.identifier,'b68:timeout'),status='timeout';
 elseif strcmp(err.identifier,'b68:numeric'),status='numeric_unresolved';
 elseif contains(lower(err.message),'out of memory') || strcmp(err.identifier,'b68:resource'),status='resource_unresolved';
 else,status='error';end
end
elapsed=toc(clock);trace(end+1,:)=[elapsed L0 U];
r=struct('input_id',c.id,'method','milp_engineering','status',status,'message',message,'schedule',best, ...
 'lower_J',L0*d.energy_unit,'upper_J',U*d.energy_unit,'solver_bound_J',internal*d.energy_unit, ...
 'optimal_value_proved',isfinite(U) && U==L0,'grid_infeasible_proved',strcmp(status,'independent_infeasible'), ...
 'optimal_set_complete',false,'coverage_valid',~strcmp(status,'error'),'elapsed_s',elapsed,'first_safe_s',first, ...
 'stats',stats,'cost_s',cost,'bound_trace',trace,'solver_trace',boundlog,'events',{events},'cuts',{cuts}, ...
 'rounds',{rounds},'unresolved',pending,'callback_fields',{callbackFields},'options_text',evalc('disp(opts)'), ...
 'proof_scope','safe_U_and_independent_L0_only_solver_bounds_reported_separately');
if strcmp(status,'independent_infeasible'),r.lower_J=Inf;end
    function check(phase)
     if isfield(inject,'phase') && strcmp(inject.phase,phase),error('b68:timeout','Injected timeout at %s',phase);end
     if toc(clock)>budget,error('b68:timeout','Budget exhausted at %s',phase);end
    end
    function q=evaluate(x,origin)
     check('candidate');timer=tic;[s,sel,E]=b68_decode(c,p,x);cost.decode=cost.decode+toc(timer);check('decoded');
     key=sprintf('%d,',sel);stats.candidates=stats.candidates+1;
     if isKey(cache,key),q=cache(key);stats.cache_hits=stats.cache_hits+1;
     else
      timer=tic;z=b64_thermal(c,s,h);cost.thermal=cost.thermal+toc(timer);stats.thermal_calls=stats.thermal_calls+1;
      q=struct('selected',sel,'schedule',s,'energy',E,'thermal',z);check('thermal_after');cache(key)=q;
     end
     check('accept');
     events{end+1}=struct('time_s',toc(clock),'round',roundNo,'origin',origin,'energy_units',E,'selected',sel,'thermal_status',q.thermal.status); %#ok<AGROW>
     if strcmp(q.thermal.status,'safe') && E<U
      U=E;best=s;if isnan(first),first=toc(clock);end
      trace(end+1,:)=[toc(clock) L0 U]; %#ok<AGROW>
     end
     if isfinite(internal) && isfinite(U) && internal>U+1e-7
      stats.bound_conflicts=stats.bound_conflicts+1;
     end
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
      if ~isempty(x) && isfield(v,'phase') && ismember(v.phase,{'heuristics','branching'})
       evaluate(x,['callback_' state]);
      end
      check('callback_end');stop=isfinite(U) && U==L0;
     catch err,callbackError=err;stop=true;end
    end
end
