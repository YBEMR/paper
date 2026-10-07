function r=f77_budget_audit(r,setup,outer,budget)
% Common conservative wall-clock audit, including uninstrumented call overhead.
% A method-local proof timestamp + offset_upper bounds its external timestamp.
offsetUpper=max(setup,outer-r.elapsed_s);
r.input_setup_s=setup;r.method_elapsed_s=r.elapsed_s;r.elapsed_s=outer;
r.time_origin_offset_interval_s=[setup offsetUpper];
r.raw_method_status=r.status;r.final_status_within_budget=outer<=budget;
r.final_solver_bound_within_budget=outer<=budget;
r.first_safe_interval_s=r.first_safe_s+[setup offsetUpper];
r.budget_evidence_ambiguous=false;r.budget_late_output=[];
if isfinite(r.upper_J)
 target=r.upper_J/(1/16000);trace=r.bound_trace;
 hit=find(isfinite(trace(:,3)) & abs(trace(:,3)-target)<1e-7,1);
 if isempty(hit) || trace(hit,1)+offsetUpper>budget
  % Preserve all raw evidence, but do not rank a witness without a budget proof.
  r.budget_late_output=struct('schedule',r.schedule,'upper_J',r.upper_J,'status',r.status, ...
   'first_safe_s',r.first_safe_s,'bound_trace',r.bound_trace);
  r.budget_evidence_ambiguous=true;r.upper_J=Inf;r.schedule=[];r.optimal_value_proved=false;
  r.status='budget_evidence_unresolved';r.first_safe_s=NaN;
  r.first_safe_interval_s=[NaN NaN];
 end
end
if outer>budget && ~r.budget_evidence_ambiguous
 % Timely witnesses survive; late solver termination is not a timely proof.
 r.status='budget_stopped_with_evidence';
 r.grid_infeasible_proved=false;
 if isfinite(r.upper_J)
  r.optimal_value_proved=(r.upper_J==r.lower_J);
 else
  r.optimal_value_proved=false;
 end
end
r.first_safe_s=r.first_safe_s+setup;r.bound_trace(:,1)=r.bound_trace(:,1)+setup;
r.solver_trace(:,1)=r.solver_trace(:,1)+setup;
r.trace_time_basis='enclosing elapsed lower estimate; upper = stored time + offset interval width';
r.event_time_origin='method-local; add time_origin_offset_interval_s for enclosing wall times';
end
