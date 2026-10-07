function checks=s55_tests(trials)
% Implementation fixtures only; never mutate trials or frozen JSON.
names={};passed=[];notes={};c=trials(1).case;h=trials(1).thermal;
add('frozen_case_counts',numel(trials)==10 && sum(strcmp({trials.cohort},'main'))==8,'8 main + 2 independent checks');
add('expanded_modes_and_ids',c.n==8 && isequal(cellfun(@(x)size(x,1),c.options),[4 5 4 4 4 5 4 4]) && isequal(c.terminal,[4 8]),'Explicit S3 terminals');
add('request_response_shared',isequal(c.options(1:4),c.options(5:8)),'A/B share types');
for i=1:4,add(sprintf('CPU_symmetry_%d',i),isequal(c.options{i}(1:2,2:4),c.options{i}(3:4,2:4)),'C1/C2 identical response');end

f=small(c);lib=s55_enumerate(f,budget());oracle=cartesian(f);
add('cartesian_complete_tuple_set',lib.complete && isequal(sortrows(double(lib.rows)),sortrows(oracle)),sprintf('%d independently legal leaves',size(oracle,1)));
add('cartesian_duplicate_free',size(unique(lib.rows,'rows'),1)==lib.count,'Each assignment exactly once');
fg=f;fg.options{2}=[fg.options{2};3 3 .001 1];fg.pred={[],1};
mapped=s55_enumerate(fg,budget());truth=cartesian(fg);
add('cartesian_optional_NPU_and_dependency',mapped.complete && isequal(sortrows(double(mapped.rows)),sortrows(truth)), ...
    'Independent Cartesian oracle includes CPU/NPU alternatives and precedence');
lib=s55_sort(f,lib,budget());
add('B_before_A_preserved',any(lib.rows(:,4)<lib.rows(:,3)),'Variable order does not impose time order');
add('waiting_and_same_time_preserved',any(all(lib.rows(:,3:4)>0,2)) && any(lib.rows(:,3)==lib.rows(:,4)),'Empty initial action and concurrency');

s=s55_schedule(f,[1 1 0 0]);add('same_unit_overlap_rejected',~s55_validate(f,s).feasible,'Both CPU1');
s=s55_schedule(f,[1 3 0 0]);add('same_frequency_parallel',s55_validate(f,s).feasible,'CPU1/CPU2 L');
sw=s55_schedule(f,[3 1 0 0]);se=s55_energy(f,s);we=s55_energy(f,sw);
add('symmetric_label_swap_equal',s55_validate(f,sw).feasible && abs(se.sum_J-we.sum_J)<1e-12,'Labels change, allocation remains parallel');
s=s55_schedule(f,[1 4 0 0]);add('shared_domain_mixed_rejected',~s55_validate(f,s).feasible,'L/H overlap');
s=s55_schedule(f,[1 4 0 1]);add('domain_empty_switch_allowed',s55_validate(f,s).feasible,'Half-open end/start');
g=f;g.options{2}=[3 3 .001 1];s=s55_schedule(g,[1 1 0 0]);
add('CPU_NPU_concurrency',s55_validate(g,s).feasible,'Independent service resources');
g.options{1}=[3 3 .001 1];s=s55_schedule(g,[1 1 0 0]);
add('NPU_overlap_rejected',~s55_validate(g,s).feasible,'Single NPU service');
g=f;g.options{1}=[1 1 .002 1];g.options{2}=[2 1 .001 1];s=s55_schedule(g,[1 1 0 1]);
add('same_frequency_offset_overlap',s55_validate(g,s).feasible,'No synchronized launch restriction');
g=f;g.options{1}=[1 1 .00125 1];g.options{2}=[2 1 .001 1];g.pred={[],1};
s=s55_schedule(g,[1 1 0 2]);add('noninteger_finish_kept',s55_validate(g,s).feasible && s.finish(1)==.00125,'Successor on grid2');
s=s55_schedule(g,[1 1 0 1]);add('noninteger_dependency_violation',~s55_validate(g,s).feasible,'Cannot round finish down');
g=f;g.deadline=[.001 .001];s=s55_schedule(g,[1 3 0 0]);add('deadline_equality',s55_validate(g,s).feasible,'Finish=deadline');
s.start(1)=.0002;s.finish(1)=.0012;add('off_grid_rejected',~s55_validate(f,s).feasible,'Grid applies to start');
g=f;g.release=[.001 0];s=s55_schedule(g,[1 3 0 0]);add('release_respected',~s55_validate(g,s).feasible,'No early start');
s=s55_schedule(f,[1 3 0 0]);s.choice(1)=9;add('illegal_mode_rejected',~s55_validate(f,s).feasible,'No absent mode');

% Eight-stage fixed-mode tiny fixture: no variable performance parameters used as research data.
g=c;g.grid=.001;g.window=.006;g.deadline=[.004 .004];
for i=1:8,g.options{i}=[1+(i>4) 2 .001 1];end
eight=s55_enumerate(g,budget());
add('eight_stage_single_schedule',eight.complete && eight.count==1,'Two pinned independent four-stage chains');
s=s55_schedule(g,eight.rows(1,:));v=s55_validate(g,s);
add('eight_stage_S3_completion',v.feasible && all(abs(v.completion-.004)<1e-12),'Terminal rows4,8');
swap=s;swap.unit=3-swap.unit;bad=s55_validate(g,swap);add('mode_table_cannot_be_rewritten',~bad.feasible,'Chosen unit must agree with mode table');
part=s;for fn={'choice','unit','mode','start','finish','duration','increment'},part.(fn{1})(4)=NaN;end
add('partial_is_not_complete',s55_validate(g,part,true).feasible && ~s55_validate(g,part).feasible,'NaN terminal cannot count as finished');
badpart=part;for fn={'choice','unit','mode','start','finish','duration','increment'},badpart.(fn{1})(2)=NaN;end
add('missing_committed_predecessor_rejected',~s55_validate(g,badpart,true).feasible,'Later committed stage needs predecessor');
rejected=false;try,s55_energy(g,part);catch,rejected=true;end
add('partial_energy_not_ranked',rejected,'Energy interface requires complete plan');

% Dynamic device classification and complete power accounting.
g=small(c);g.options{1}=[1 2 .001 2];g.options{2}=[2 2 .001 2;3 3 .001 2];
cpu=s55_schedule(g,[1 1 0 0]);npu=s55_schedule(g,[1 2 0 0]);
ec=s55_energy(g,cpu);en=s55_energy(g,npu);
add('energy_two_independent_sums',ec.error_J<1e-12 && en.error_J<1e-12,'Piecewise versus activity sum');
add('device_energy_reclassification',abs(ec.cpu_active_J-.004)<1e-12 && abs(en.cpu_active_J-.002)<1e-12 && abs(en.npu_active_J-.002)<1e-12,'Same stage remapped');
tc=s55_thermal(g,cpu,h);tn=s55_thermal(g,npu,h);
add('parallel_CPU_heat_summed',norm(tc.segments{1}.power-[4.2;.3])<1e-12,'Two active CPU increments');
add('mapping_changes_heat_node',norm(tn.segments{1}.power-[2.2;2.3])<1e-12,'NPU mode injects NPU heat');
delayed=s55_schedule(g,[1 1 1 1]);ed=s55_energy(g,delayed);
add('waiting_preserves_fixed_mode_energy',abs(ec.sum_J-ed.sum_J)<1e-12 && abs(ec.base_J-.004)<1e-12,'Base once across full window');
hot=h;hot.initial=[78 78];th=s55_thermal(g,cpu,hot);
add('initial_temperature_monotonicity',all(th.event_temperature(:)>=tc.event_temperature(:)-1e-10),'Same complete power trajectory');
band=h;band.limit=tc.peak;tb=s55_thermal(g,cpu,band);
add('threshold_equality_unresolved',strcmp(tb.status,'unresolved'),'No exclusion at threshold');
off=h;off.limit=[Inf Inf];tt=s55_thermal(g,cpu,off);add('thermal_disabled_safe',strcmp(tt.status,'safe'),'Does not change schedule');

net=thv_build(h);z=thv_step(net,[0;40],[0;0],.2);
add('RC_internal_peak',abs(z.peak(1)-5)<1e-9 && abs(z.peak_time(1)-log(2)/20)<1e-10,'Analytic internal maximum');
zz=thv_step(net,[20;20],[0;0],.06);add('RC_endpoint_and_zero_cooling',norm(zz.finish-20*exp(-1.2))<1e-10 && all(zz.peak_time==0),'Endpoint maximum');
idle=net.G\[.2;.3];zz=thv_step(net,idle,[.2;.3],.020);
add('RC_idle_equilibrium',norm(zz.finish-idle)<1e-10 && norm(idle-[4.5;5.5])<1e-10,'Nonzero idle injection');
hh=h;hh.g=0;nn=thv_build(hh);zz=thv_step(nn,[10;50],[.8;1.2],.03);
expect=[.8;1.2]/.05+([10;50]-[.8;1.2]/.05)*exp(-.6);
add('RC_repeated_eigenvalue',norm(zz.finish-expect)<1e-10,'Uncoupled analytic check');
opts=odeset('RelTol',1e-10,'AbsTol',1e-11,'MaxStep',.0001);theta=h.initial(:)-h.ambient;odeerr=0;
for j=1:numel(tc.segments)
    seg=tc.segments{j};[~,Y]=ode45(@(~,y)net.A*y+net.C\seg.power,[0 seg.duration],theta,opts);
    theta=Y(end,:)';odeerr=max(odeerr,norm(theta-seg.finish,Inf));
end
add('piecewise_ODE_crosscheck',odeerr<=1e-6,sprintf('max error %.12g C',odeerr));

% Frozen47 witness adapter is ONLY a test fixture, not a new Stage53 case.
here=fileparts(mfilename('fullpath'));old=p47_cases(fullfile(fileparts(here),'prefix46_design','inputs_v1.json'));
oc=old(1).case;os=c44_schedule(oc,[2 2 1 2 .001 0 .009 .004]);og=small(c);
og.n=4;og.request=[1 2 1 2];og.pred={[],[],1,2};og.terminal=[3 4];og.stage_id={'A1','B1','A2','B2'};
og.deadline=oc.deadline;og.release=oc.release;og.window=oc.window;og.grid=oc.grid;
og.options=cell(1,4);for i=1:4,og.options{i}=[os.unit(i) 3 os.duration(i) os.increment(i)];end
og.options{1}(2)=2;og.options{2}(2)=2;
gs=s55_schedule(og,[ones(1,4) round(os.start/og.grid)]);eold=cv_energy(oc,os);eg=s55_energy(og,gs);
told=c44_thermal(oc,os,old(1).thermal);tg=s55_thermal(og,gs,old(1).thermal);
add('old47_energy_wrapper_equivalence',abs(eold.integral-eg.integral_J)<1e-12,'Frozen existing witness only');
add('old47_thermal_wrapper_equivalence',max(abs(told.peak-tg.peak))<1e-9 && max(abs(told.terminal-tg.terminal))<1e-9,'Dynamic nodes reproduce old serial identity');

% Exact representative selection cross-check, including wait and suffix omission.
tr=struct('case',f,'thermal',h);tr.thermal.limit=[Inf Inf];r=s55_method(tr,'full_suffix');
sl=s55_sort(f,s55_enumerate(f,budget()),budget());
act=sl.rows(:,1:2).*uint16(sl.rows(:,3:4)==0);[~,first]=unique(act,'rows','stable');
add('representative_first_safe_correct',strcmp(r.status,'complete_safe') && isequal(r.attempts{1}.row,sl.rows(first(1),:)),'Same ordered full-library truth');
add('action_keys_unique_and_wait',r.representative_count==size(unique(act,'rows'),1) && any(all(act==0,2)),'Stage-specific choice IDs no collision');
add('single_representative_early_stop',r.thermal_calls==1,'Thermal-off first representative only');
raw=sl;cfg=raw.rows(:,1:2);hasOmission=false;
for ii=1:size(act,1)
    same=all(act==act(ii,:),2);if size(unique(cfg(same,:),'rows'),1)>1,hasOmission=true;break;end
end
add('same_action_can_omit_config',hasOmission,'Full mode coverage != thermal representative coverage');
ref=s55_method(tr,'thermal_reference');
add('reference_thermal_off_matches_noheat',ref.optimal_value_proved && ref.optimal_set_complete && abs(ref.upper_J-min(sl.energy))<1e-10,'Complete optimal configuration layer');
tr.thermal.limit=[24 24];no=s55_method(tr,'full_suffix');nr=s55_method(tr,'thermal_reference');
add('representative_exhaustion_not_infeasibility',strcmp(no.status,'no_safe_representative'),'Baseline cannot exclude full domain');
add('reference_full_exclusion',strcmp(nr.status,'grid_thermal_infeasible') && all(nr.reference.state==2),'All configurations excluded');
tr.thermal.initial=[30 30];tr.thermal.limit=[30 30];
for i=1:f.n,tr.case.options{i}(:,4)=0;end
tr.case.idle_cpu=0;tr.case.idle_npu=0;tr.case.external=0;
ur=s55_method(tr,'thermal_reference');ub=s55_method(tr,'full_suffix');
add('unresolved_cannot_exclude',~strcmp(ur.status,'grid_thermal_infeasible') && all(ur.reference.state==3) && strcmp(ub.status,'thermal_unresolved'),'Initial equality then cooling');

% Energy layer fixture: 0, 0.75tol, 1.5tol; fixed anchor must yield 1,1,2.
g=f;g.n=1;g.request=1;g.pred={[]};g.terminal=1;g.release=0;g.deadline=.001;g.stage_id={'X'};
g.options={[1 1 .001 0;1 2 .001 7.5e-8;1 3 .001 1.5e-7]};
ll=struct('complete',true,'count',3,'rows',uint16([1 0;2 0;3 0]));ll=s55_sort(g,ll,budget());
add('energy_anchor_no_chaining',isequal(ll.rank,[1;1;2]),'Only fixed first anchor');
again=s55_sort(f,s55_enumerate(f,budget()),budget());add('deterministic_sort',isequal(again.rows,sl.rows),'Same full tuples and ties');

tr=struct('case',f,'thermal',h);
for ph={'enumerate','sort','thermal'}
    rr=s55_method(tr,'full_suffix',ph{1});
    add(['injected_timeout_' ph{1}],strcmp(rr.status,'timeout') && ~rr.optimal_value_proved,'No fake optimality or infeasibility');
    if strcmp(ph{1},'enumerate'),add('partial_library_not_exact',~rr.enumeration_complete && isempty(rr.attempts),'No representatives from incomplete library');end
end
for id={'s55:resource','s55:io'}
    rr=s55_method(tr,'full_suffix',struct('phase','sort','identifier',id{1}));
    add(['resource_state_' strrep(id{1},':','_')],strcmp(rr.status,'resource_unresolved') && ~rr.optimal_value_proved && isempty(rr.attempts), ...
        'Resource/I-O interruption is neither infeasibility nor a baseline counterexample');
end
% Check known source semantics; no reference schedule is an input parameter.
source=fileread(fullfile(here,'s55_method.m'));
add('method_no_file_reads',~contains(source,'fileread(') && ~contains(source,'load('),'Method uses only trial/method/test injection');
add('no_shared_library_cache',~contains(source,'persistent ') && ~contains(source,'global '),'Invocation-local candidate space');
% Export regression after field-initialization bug: tiny eight-stage fixture only.
gx=c;gx.id='fixture_export';gx.cohort='check';gx.deadline=[.004 .004];gx.window=.006;
for i=1:8,gx.options{i}=[1+(i>4) 2 .001 1];end
tx=struct('id',gx.id,'cohort',gx.cohort,'case',gx,'thermal',h);
rj=s55_method(tx,'joint_noheat');rb=s55_method(tx,'full_suffix');rt=s55_method(tx,'thermal_reference');
exportFolder=tempname(fullfile(here,'stage55_reports'));mkdir(exportFolder);
[tab,xc]=s55_export(exportFolder,tx,{rj,rb},{rt});
add('export_summary_and_representatives',height(tab)==3 && all(xc.passed) && ...
    isfile(fullfile(exportFolder,'fixture_export_full_suffix_attempts.csv')) && ...
    isfile(fullfile(exportFolder,'fixture_export_reference_configurations.csv')),exportFolder);
checks=table(names',logical(passed'),notes','VariableNames',{'name','passed','note'});
    function add(name,ok,note),names{end+1}=name;passed(end+1)=logical(ok);notes{end+1}=note;end
end
function b=budget(),b=struct('timer',tic,'limit',60);end
function f=small(c)
f=c;f.id='fixture';f.n=2;f.request=[1 2];f.pred={[],[]};f.terminal=[1 2];f.stage_id={'X','Y'};
f.release=[0 0];f.deadline=[.003 .003];f.window=.004;f.grid=.001;
f.options={[1 1 .001 1;1 2 .001 2;2 1 .001 1;2 2 .001 2], ...
           [1 1 .001 1;1 2 .001 2;2 1 .001 1;2 2 .001 2]};
end
function rows=cartesian(c)
% Separate Cartesian oracle with direct predicates (does NOT call validator).
rows=zeros(0,2*c.n);mi=zeros(1,c.n);kk=zeros(1,c.n);rec(1);
    function rec(i)
        if i<=c.n
            for m=1:size(c.options{i},1)
                for k=0:floor(c.window/c.grid),mi(i)=m;kk(i)=k;rec(i+1);end
            end
            return;
        end
        u=zeros(1,c.n);f=u;st=kk*c.grid;en=st;
        for a=1:c.n,o=c.options{a}(mi(a),:);u(a)=o(1);f(a)=o(2);en(a)=st(a)+o(3);end
        for a=1:c.n
            if st(a)<c.release(c.request(a))-c.time_tol || en(a)>min(c.window,c.deadline(c.request(a)))+c.time_tol,return;end
            if any(en(c.pred{a})>st(a)+c.time_tol),return;end
            for bb=1:a-1
                if st(a)<en(bb)-c.time_tol && st(bb)<en(a)-c.time_tol
                    if u(a)==u(bb),return;end
                    if c.unit_kind(u(a))==1 && c.unit_kind(u(bb))==1 && c.domain(u(a))==c.domain(u(bb)) && f(a)~=f(bb),return;end
                end
            end
        end
        rows(end+1,:)=[mi kk]; %#ok<AGROW>
    end
end
