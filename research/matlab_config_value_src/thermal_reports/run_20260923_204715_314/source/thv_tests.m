function checks = thv_tests(trials,results)
names={}; ok=[]; notes={}; h=trials(1).thermal; net=thv_build(h);
add('stable_network',all(eig(net.A)<0),'Both decay modes stable');
add('time_constants',max(abs(sort(net.tau)-[.025;.050]))<1e-12,'25 and 50 ms');
p=[.2;.3]; eq=net.G\p; z=thv_step(net,eq,p,.060);
add('idle_equilibrium',max(abs(z.finish-eq))<1e-10,'No equilibrium drift');
z=thv_step(net,[20;20],[0;0],.060);
add('zero_input_uniform_cooling',max(abs(z.finish-20*exp(-20*.060)))<1e-10, ...
    'Zero input does not imply every nonuniform node cools monotonically');
g0=h; g0.g=0; n0=thv_build(g0); theta=[10;50]; p=[.8;1.2];
z=thv_step(n0,theta,p,.030); expect=p./g0.g_env(:)+(theta-p./g0.g_env(:))*exp(-20*.030);
add('uncoupled_repeated_eigenvalue',max(abs(z.finish-expect))<1e-10,'Independent analytic RC solutions');
z=thv_step(net,[0;40],[0;0],.2);
add('internal_peak',abs(z.peak(1)-5)<1e-9 && abs(z.peak_time(1)-log(2)/20)<1e-10, ...
    'CPU initially cold, NPU hot: internal CPU peak 5 K at log(2)/20 s');
z2=thv_step(net,[20;20],[0;0],.060);
add('endpoint_peak',max(abs(z2.peak-[20;20]))<1e-10 && all(z2.peak_time==0),'Maximum at initial endpoint');
opts=odeset('RelTol',1e-10,'AbsTol',1e-11,'MaxStep',.0001);
requested=sort(unique([0:.001:.2 log(2)/20 .2]));
[t,Y]=ode45(@(~,y)net.A*y,requested,[0;40],opts);
analytic=(z.equilibrium+z.coeff*exp(-net.lambda*t'))';
add('internal_peak_ODE_crosscheck',max(abs(Y(:)-analytic(:)))<1e-6, ...
    sprintf('max ODE error %.12g K',max(abs(Y(:)-analytic(:)))));
% Cross-check every segment of a full power trajectory, not only constant input.
c=trials(1).case; s=cv_schedule(c,'task',[2 1],[1 2],[1 2]);
ev=thv_evaluate(c,s,h,net); ode_theta=h.initial(:)-h.ambient; ode_error=0;
for k=1:numel(ev.segments)
    seg=ev.segments{k};
    if seg.duration==0, continue; end
    [~,yy]=ode45(@(~,y)net.A*y+net.C\seg.power,[0 seg.duration],ode_theta,opts);
    ode_theta=yy(end,:)'; ode_error=max(ode_error,max(abs(ode_theta-seg.finish)));
end
add('full_schedule_segment_ODE',ode_error<1e-6,sprintf('max endpoint error %.12g K',ode_error));
cold=h; hot=h; hot.initial=[78 78];
ec=thv_evaluate(c,s,cold,net); eh=thv_evaluate(c,s,hot,net);
[tc,Tc]=thv_trace(ec,cold,.0001); [th,Th]=thv_trace(eh,hot,.0001);
% Trace stationary points differ: compare propagated endpoint states directly,
% and evaluate a common dense grid in each identical power segment.
mono=all(eh.event_temperature(:)>=ec.event_temperature(:)-1e-9);
for k=1:numel(ec.segments)
    a=ec.segments{k}; b=eh.segments{k}; ts=linspace(0,a.duration,21);
    delta=(b.equilibrium+b.coeff*exp(-net.lambda*ts))-(a.equilibrium+a.coeff*exp(-net.lambda*ts));
    mono=mono && all(delta(:)>=-1e-9);
end
add('hot_entry_order_preserved',mono,'Same power, componentwise hotter initial state');
add('sample_below_analytic_peak',all(max(Tc,[],1)<=ec.peak+1e-9) && ...
    all(max(Th,[],1)<=eh.peak+1e-9),'Sampling is a diagnostic, not the classifier'); %#ok<NASGU>
badband=h; badband.limit=ec.peak;
atbound=thv_evaluate(c,s,badband,net);
add('threshold_band_unresolved',strcmp(atbound.status,'unresolved'),'Equality is not declared safe');
shifted=s; shifted.start=s.start+.001; shifted.finish=s.finish+.001;
e1=cv_energy(c,s); e2=cv_energy(c,shifted);
add('waiting_no_duplicate_idle_energy',abs(e1.integral-e2.integral)<1e-10,'Identical modes and fixed window');
for id={'R1_alpha_02','R1_alpha_10','R2_above_tight'}
    idx=find(strcmp(arrayfun(@(x)x.case.id,trials,'UniformOutput',false),id{1}),1);
    tr=trials(idx); tr.thermal.limit=[Inf Inf];
    off=thv_search(tr);
    add(['thermal_off_' id{1}],off.all_modes_resolved && ...
        abs(off.best_found-off.reference.best)<1e-10 && ...
        strcmp(codes(off),cv_mode_codes(off.reference)),'Recover document 35 without thermal restriction');
end
all_valid=true; all_safe=true; all_energy=true; grid_ok=true;
for k=1:numel(results)
    r=results{k}; tr=trials(k);
    add(['completed_' tr.id],strcmp(r.status,'completed'),'Error is not infeasibility');
    for m=r.modes
        if strcmp(m.status,'feasible')
            v=cv_validate(tr.case,m.witness); all_valid=all_valid && v.feasible;
            all_safe=all_safe && strcmp(m.evaluation.status,'safe');
            e=cv_energy(tr.case,m.witness); all_energy=all_energy && abs(e.integral-m.energy)<1e-10;
            grid_ok=grid_ok && max(abs(m.witness.start/tr.thermal.grid-round(m.witness.start/tr.thermal.grid)))<1e-6;
        end
    end
end
add('all_witnesses_resource_deadline_legal',all_valid,'No overlap, dependency, release or deadline violation');
add('all_witnesses_continuous_peak_safe',all_safe,'Endpoints and internal stationary points checked');
add('all_witness_energy_checks',all_energy,'Integral, sum and mode energy agree');
add('all_witness_start_grid',grid_ok,'Durations are not rounded');
for k=13:15
    fine=trials(k); coarseid=strrep(fine.id,'dt05','dt1'); j=find(strcmp({trials.id},coarseid));
    retained=true;
    for m=results{j}.modes
        if strcmp(m.status,'feasible')
            retained=retained && max(abs(m.witness.start/fine.thermal.grid-round(m.witness.start/fine.thermal.grid)))<1e-6;
            e=thv_evaluate(fine.case,m.witness,fine.thermal);
            retained=retained && strcmp(e.status,'safe');
        end
    end
    add(['coarse_witness_on_fine_' fine.case.id],retained,'Revalidate witnesses; timeout does not negate retention');
end
checks=table(names(:),logical(ok(:)),notes(:),'VariableNames',{'check','passed','detail'});
    function add(name,value,detail)
        names{end+1}=name; ok(end+1)=value; notes{end+1}=detail;
    end
end
function text=codes(r)
labels='LH'; values={};
for j=r.optimal_mode_indices, values{end+1}=labels(r.modes(j).mode); end
text=strjoin(sort(values),'|');
end
