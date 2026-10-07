function test_waiting_baseline()
% Regression tests for history semantics and physically meaningful invariants.
c=config_default(); c.H_ms=28; c.D_A_ms=24; c.D_B_ms=28;
p=[1 2 2 2 0 10 4 15]; earlier=p; earlier(6)=8;
assert(isnan(first_optimal_divergence(p,[earlier;p],c)), 'Waiting must retain a matching optimum.');
assert(first_optimal_divergence(p,earlier,c)==8, 'All completions diverge at 8.');
othermap=p; othermap(2)=1;
assert(first_optimal_divergence(p,othermap,c)==10, 'Future B1 mapping must not cause t*=0.');
swap=p; swap(1:2)=3-swap(1:2);
assert(isnan(first_optimal_divergence(p,swap,c,true)), 'A consistent symmetric permutation is allowed.');
assert(first_optimal_divergence(p,swap,c,false)==0);
asym=c; asym.g_env(1)=0.06;
try
    first_optimal_divergence(p,swap,asym,true);
    error('test:no_rejection','Asymmetric swap was accepted.');
catch err
    assert(strcmp(err.identifier,'first_optimal_divergence:asymmetric'));
end
st=schedule_state_before(p,c,0);
assert(isequal(st.ready,{'A1','B1'}) && isempty(st.running) && numel(st.free)==3);
st=schedule_state_before(p,c,1);
assert(isequal(st.ready,{'B1'}) && isequal(st.running,{'A1'}));
st=schedule_state_before(p,c,4);
assert(isequal(st.ready,{'B1','A2'}) && isequal(st.done,{'A1'}));

% Cooling trajectories must retain their initial peak; overshoot starts fail.
cool=c; cool.T0=79; cool.P_A1=[.5 .5]; cool.P_B1=[.5 .5];
cool.P_A2=1; cool.P_B2=1;
r=eval_schedules(p,cool,thermal_build(cool)); assert(r.Tmax==79 && r.tr_ok);
cool.T0=81; r=eval_schedules(p,cool,thermal_build(cool));
assert(r.Tmax==81 && ~r.tr_ok);

% With inactive thermal limits, simultaneous ready tasks must both start,
% cheaper modes win, and tightening a future-wait window must not matter.
c.T_lim=200; th=thermal_build(c);
w=waiting_scheduler(c,th); z=waiting_scheduler(c,th,struct('max_wait',0));
assert(w.complete && z.complete && isequal(w.pi,z.pi));
assert(all(w.pi(3:4)==2) && all(w.pi(5:6)==0));
v=validate_schedule(w.pi,c,th); assert(v.ok && abs(v.E_mJ-w.E_mJ)<1e-9);
partial=w.pi; partial(8)=NaN; v=validate_schedule(partial,c,th); assert(~v.ok && isnan(v.E_mJ));
illegal=w.pi; illegal(8)=illegal(7); v=validate_schedule(illegal,c,th); assert(~v.legal);
c.rB_ms=10; w=waiting_scheduler(c,th); assert(w.pi(6)>=10);
fprintf('PASS: divergence, symmetry, readiness, initial peak, energy, release and validation tests.\n');
end
