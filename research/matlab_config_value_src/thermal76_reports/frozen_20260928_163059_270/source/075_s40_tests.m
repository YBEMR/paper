function checks=s40_tests(trials)
% Software fixtures only; not new research cases.
names={}; passed=[];
t=trials(end); c=t.case; h=t.thermal;
check('60_frozen_conditions',numel(trials)==60 && numel(unique({trials.id}))==60);
check('fixed_parameters',all(arrayfun(@(x)x.thermal.grid==.001 && x.case.window==.060 && x.thermal.g==.025,trials)));
check('deadline_and_margin',all(arrayfun(@(x)max(abs(x.case.deadline-x.rho*.007))<1e-12 && max(abs(x.thermal.initial-(80-x.margin*55)))<1e-12,trials)));
% Tiny independent 4-D Cartesian enumeration, includes non-grid CPU finish.
c.dref=[.0013 .001]; c.alpha=[0 0]; c.n=[.001 .001];
c.deadline=[.004 .004]; c.window=.005; h.initial=[25 25];
r=s40_reference(c,h,tic); allcounts=zeros(2); energies=[]; keys={};
for a=1:2
    for b=1:2
        m=[a b]; base=cv_schedule(c,'task',m,[1 2],[1 2]); independent={};
        for t1=0:4
            for t2=0:4
                for t3=0:4
                    for t4=0:4
                        s=base; s.start=[t1 t2 t3 t4]*h.grid; s.finish=s.start+s.duration;
                        v=cv_validate(c,s);
                        if v.feasible, independent{end+1}=sprintf('%d_', [t1 t2 t3 t4]); end %#ok<AGROW>
                    end
                end
            end
        end
        keys={}; w=s40_walk(c,h,m,@collect,tic); allcounts(a,b)=numel(independent);
        check(sprintf('grid_enumeration_%d%d',a,b),strcmp(w.status,'exhausted') && w.count==numel(independent) && isequal(sort(keys),sort(independent)) && numel(unique(keys))==numel(keys));
        ix=find(arrayfun(@(z)isequal(z.schedule.modes,m)&&z.validation.feasible,r.rows));
        check(sprintf('earliest_completeness_%d%d',a,b),~isempty(ix)==~isempty(independent));
        if ~isempty(independent), energies(end+1)=sum(base.increment.*base.duration)+(c.idle_cpu+c.idle_npu+c.external)*c.window; end %#ok<AGROW>
    end
end
check('reference_energy_independent',abs(r.best-min(energies))<1e-12);
s=r.rows(1).schedule;
check('fractional_end_not_rounded',abs(s.finish(1)-.0013)<1e-12 && abs(s.start(3)-.002)<1e-12);
c.deadline=[.0023 .004]; r2=s40_reference(c,h,tic);
check('deadline_not_rounded',~r2.rows(1).validation.feasible);
c.deadline=[.003 .004]; r3=s40_reference(c,h,tic); check('exact_deadline_allowed',r3.rows(1).validation.feasible);
hh=h; hh.budget_s=-1; w=s40_walk(c,h,[1 1],@(s)false,tic);
check('enumeration_count_positive',w.count>0);
w=s40_walk(c,hh,[1 1],@(s)false,tic); check('timeout_not_exclusion',strcmp(w.status,'timeout')&&w.count==0);
% All classes and partial evidence, independent of numerical thermal traces.
z=struct('optimal',true,'has_safe',false,'has_violation',false,'excluded',false,'all_safe',false,'energy',1);
v=z; d=s40_decide(v,1,c); check('single_unknown_U',strcmp(d.class,'U'));
v.has_safe=true; d=s40_decide(v,1,c); check('safe_witness_not_A',strcmp(d.class,'U')&&d.energy_exact);
v.all_safe=true; d=s40_decide(v,1,c); check('proof_A',strcmp(d.class,'A'));
v.all_safe=false; v.has_violation=true; d=s40_decide(v,1,c); check('two_witnesses_B',strcmp(d.class,'B'));
v2=z; v2.optimal=false; v2.energy=2; v2.has_safe=true;
v=z; v.excluded=true; d=s40_decide([v v2],1,c); check('exclusion_and_witness_C',strcmp(d.class,'C')&&d.lower_J==2&&d.upper_J==2);
v2.has_safe=false; v2.excluded=true; d=s40_decide([v v2],1,c); check('full_exclusion_D',strcmp(d.class,'D'));
d=s40_decide([v v2],inf,c); check('no_heat_N',strcmp(d.class,'N'));
v=z; v2=z; v2.optimal=false; v2.energy=2; v2.has_safe=true;
d=s40_decide([v v2],1,c); check('uncertain_optimal_not_C',strcmp(d.class,'U')&&d.lower_J==1&&d.upper_J==2&&~d.energy_exact);
v.has_safe=true; v.has_violation=true; v2=z;
d=s40_decide([v v2],1,c); check('B_with_tied_mode_unresolved',strcmp(d.class,'B')&&d.energy_exact);
original=cv_cases(); tie=original(strcmp({original.id},'R1_alpha_06'));
cfg=s40_config(tie,t.thermal,tic); check('all_tied_modes',numel(cfg)==2);
check('config_no_schedule_fields',isequal(sort(fieldnames(cfg)),sort({'modes';'duration';'increment'})));
% Independent full evaluator and closed-form certificates share boundaries.
ref=s40_reference(t.case,t.thermal,tic); ss=ref.rows(ref.optimal_indices(1)).schedule;
cert=s40_certificate(t.case,t.thermal,ss); ev=thv_evaluate(t.case,ss,t.thermal);
check('certificate_safe_crosscheck',~cert.safe||strcmp(ev.status,'safe'));
filteroff=h37_policy(t.case,t.thermal,s40_config(t.case,t.thermal,tic),'P1',tic,false);
p0=h37_policy(t.case,t.thermal,s40_config(t.case,t.thermal,tic),'P0',tic);
check('disabled_filter_actions_equal',isequaln(filteroff.schedule,p0.schedule)&&strcmp(filteroff.status,p0.status));
policy=fileread(which('h37_policy'));
check('policy_no_oracle_io',isempty(regexp(policy,'\<(load|readtable|fopen|s40_classify|thv_search)\s*\(','once')));
checks=table(string(names'),logical(passed'),'VariableNames',{'check','passed'});
assert(all(checks.passed),'s40 preflight checks failed');
    function check(name,value)
        names{end+1}=name; passed(end+1)=logical(value);
    end
    function stop=collect(s)
        vv=cv_validate(c,s); assert(vv.feasible);
        keys{end+1}=sprintf('%d_',round(s.start/h.grid)); stop=false;
    end
end
