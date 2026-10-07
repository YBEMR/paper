function checks=c44_tests(trials)
names={}; passed=[]; note={};
c=trials(1).case; h=trials(1).thermal;
add('frozen_counts',numel(trials)==10 && sum(strcmp({trials.role},'main'))==8,'8 main + 2 diagnostics');
add('domains_decoded',isequal(trials(1).case.domain,[1 1]) && isequal(trials(9).case.domain,[1 2]),'Derived from membership');
s=c44_schedule(c,[2 2 1 2 0 .001 .004 .007]);
add('same_frequency_staggered_overlap',c44_validate(c,s).feasible,'Overlap on distinct units permitted');
bad=s; bad.unit(2)=1; add('same_unit_overlap_rejected',~c44_validate(c,bad).feasible,'Physical exclusion');
bad=c44_schedule(c,[2 1 1 2 0 0 .004 .007]);
add('shared_domain_mixed_overlap_rejected',~c44_validate(c,bad).feasible,'H and L overlap');
ind=c; ind.domain=[1 2]; add('independent_domain_mixed_overlap',c44_validate(ind,bad).feasible,'Same work, different legal domain');
serial=c44_schedule(c,[2 1 1 2 0 .004 .004 .009]);
add('idle_boundary_frequency_switch',c44_validate(c,serial).feasible,'H ends exactly when L starts');
e=cv_energy(c,serial); moved=serial; moved.start=moved.start+.001; moved.finish=moved.finish+.001;
e2=cv_energy(c,moved); add('energy_wait_invariant',abs(e.integral-e2.integral)<1e-12,'Fixed window idle once');
z=c44_thermal(c,s,h); powers=cellfun(@(a)a.power(1),z.segments);
add('double_cpu_heat_sum',any(abs(powers-4.2)<1e-12),'0.2 + 2 + 2 W');
partial=c44_schedule(c); partial=c44_commit(c,partial,[2 2 1 2 0 0 .004 .007],0);
zp=c44_thermal(c,partial,h);
add('partial_includes_both_running',abs(zp.segments{1}.power(1)-4.2)<1e-12,'Entire launch group');
eq=thv_build(h); opts=odeset('RelTol',1e-10,'AbsTol',1e-11,'MaxStep',.0001);
theta=h.initial(:)-h.ambient; err=0;
for k=1:numel(z.segments)
    seg=z.segments{k}; [~,Y]=ode45(@(~,y)eq.A*y+eq.C\seg.power,[0 seg.duration],theta,opts);
    theta=Y(end,:)'; err=max(err,max(abs(theta-seg.finish)));
end
add('parallel_trajectory_ODE',err<1e-6,sprintf('max endpoint error %.12g',err));
st=thv_step(eq,[0;40],[0;0],.2);
add('continuous_internal_peak',abs(st.peak(1)-5)<1e-9 && abs(st.peak_time(1)-log(2)/20)<1e-10,'Analytic interior maximum');
h0=h; h0.g=0; net0=thv_build(h0); st=thv_step(net0,[10;50],[.8;1.2],.03);
expect=[.8;1.2]./h0.g_env(:)+([10;50]-[.8;1.2]./h0.g_env(:))*exp(-20*.03);
add('repeated_eigenvalue',max(abs(st.finish-expect))<1e-10,'Uncoupled exact solution');
legacy=thv_cases(); lc=legacy(1).case; lh=legacy(1).thermal;
ls=cv_schedule(lc,'task',[2 1],[1 2],[1 2]); old=thv_evaluate(lc,ls,lh);
lc.grid=lh.grid; lc.domain=[1 1]; lc.npu_increment=lc.w; ls.unit=[1 1 3 3]; fresh=c44_thermal(lc,ls,lh);
add('legacy_serial_thermal_equal',max(abs(old.peak-fresh.peak))<1e-10 && max(abs(old.terminal-fresh.terminal))<1e-10,'Old engine unchanged');
% Small independent full Cartesian grid: no production bounds, library or validator.
f=c; f.dref=[.0015 .001]; f.alpha=[0 0]; f.u=[1 1]; f.v=[0 0];
f.n=[.001 .001]; f.deadline=[.004 .005]; f.window=.008;
lib=c44_library(f,tic); brute=bruteforce(f);
add('independent_grid_full_set',isequal(sortrows(lib.rows),sortrows(brute)),sprintf('%d legal labelled schedules',lib.count));
add('noninteger_finish_grid',any(abs(lib.rows(:,5)+.0015-round((lib.rows(:,5)+.0015)/f.grid)*f.grid)>f.time_tol),'Finish remains continuous');
ff=trials(1); ff.case=f;
ref=c44_reference(ff); add('tied_optimal_mode_set',ref.energy_exact && numel(ref.optimal_modes)==4,'Equal powers and times across modes');
r0=c44_policy(ff,'C0'); r1=c44_policy(ff,'C1',false);
add('thermal_filter_disabled_identical',strcmp(r0.status,'complete') && isequaln(r0.schedule,r1.schedule) && isequaln(r0.events,r1.events),'Same policy mechanics');
pr=r0.events(1); idx=c44_prefix(f,lib.rows,pr.prefix,pr.time,true);
add('prefix_frozen_and_no_hidden_starts',any(idx) && all(all(lib.rows(idx,5:8)>=0)),'After-action prefix retains at least selected suffix');
row=lib.rows(1,:); full=c44_schedule(f,row); perm=full; perm.unit(1:2)=3-full.unit(1:2);
add('core_label_symmetry',c44_validate(f,perm).feasible && abs(cv_energy(f,full).integral-cv_energy(f,perm).integral)<1e-12,'Identical cores');
tiny=ff; tiny.case.deadline=[.001 .001]; rn=c44_reference(tiny);
add('noheat_infeasible',strcmp(rn.status,'noheat_infeasible'),'Insufficient time is not thermal');
timed=ff; timed.case.budget_s=-1;
rt=c44_reference(timed); pt=c44_policy(timed,'C1');
add('timeout_not_infeasible',strcmp(rt.status,'timeout') && strcmp(pt.status,'timeout') && ~rt.energy_exact,'Explicit uncompleted state');
unc=ff; unc.case.u=[0 0]; unc.case.v=[0 0]; unc.case.npu_increment=[0 0]; unc.case.idle_cpu=0; unc.case.idle_npu=0;
unc.thermal.limit=unc.thermal.initial;
ru=c44_reference(unc);
add('unresolved_not_excluded',all(strcmp({ru.modes.status},'unresolved')) && ~ru.energy_exact && isinf(ru.upper_J),'At threshold throughout initial instant');
fail=ff; fail.thermal.initial=[25 25]; fail.thermal.limit=[25.0001 25.0001]; rd=c44_reference(fail);
add('grid_infeasible_requires_exhaustion',strcmp(rd.status,'grid_thermal_infeasible') && all(strcmp({rd.modes.status},'excluded')),'All valid schedules evaluated');
checks=table(names',passed',note','VariableNames',{'name','passed','note'});
    function add(n,p,msg), names{end+1}=n; passed(end+1)=logical(p); note{end+1}=msg; end
end
function rows=bruteforce(c)
rows=zeros(0,8); [a,b,n,m]=ndgrid(0:c.grid:max(c.deadline)); S=[a(:) b(:) n(:) m(:)];
for ma=1:2
    for mb=1:2
        dur=[c.dref c.n]; F=S+dur;
        basic=all(F<=c.window+c.time_tol,2) & all(S(:,1:2)>=c.release-c.time_tol,2) & ...
            all(S(:,3:4)>=F(:,1:2)-c.time_tol,2) & all(F(:,3:4)<=c.deadline+c.time_tol,2) & ...
            (F(:,3)<=S(:,4)+c.time_tol | F(:,4)<=S(:,3)+c.time_tol);
        for ua=1:2
            for ub=1:2
                ok=basic;
                if ua==ub || (c.domain(ua)==c.domain(ub)&&ma~=mb)
                    ok=ok & (F(:,1)<=S(:,2)+c.time_tol | F(:,2)<=S(:,1)+c.time_tol);
                end
                rows=[rows;repmat([ma mb ua ub],sum(ok),1) S(ok,:)]; %#ok<AGROW>
            end
        end
    end
end
end
