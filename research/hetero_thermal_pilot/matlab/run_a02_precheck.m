function report = run_a02_precheck(output_json)
%RUN_A02_PRECHECK TEST_ONLY algebraic fixtures, not a scheduling experiment.
% No hardware calibration, optimiser, parameter sweep, or energy ranking.
checks = struct('name',{},'passed',{});
addcheck('alpha_inverse_limit', @check_alpha_inverse);
addcheck('alpha_frequency_insensitive_limit', @check_alpha_flat);
addcheck('illegal_frequency_rejected', @check_illegal);
addcheck('piecewise_cycles_divided_by_frequency', @check_cycles);
addcheck('table_has_no_hidden_interpolation', @check_table);
addcheck('scalar_temperature_closed_form', @check_scalar);
addcheck('scalar_leakage_energy_closed_form', @check_leakage);
addcheck('zero_power_cools_without_energy', @check_cooling);
addcheck('split_segments_preserve_history_and_energy', @check_split);
addcheck('coupling_has_internal_temperature_peak', @check_internal_peak);
addcheck('matrix_exponential_vs_independent_ode45', @check_ode);
addcheck('zero_duration_identity', @check_zero);
addcheck('unstable_feedback_never_becomes_safe', @check_unstable);
addcheck('nonphysical_conductance_rejected', @check_invalid);
report = struct('kind','TEST_ONLY','matlab_version',version,'research_calls',0, ...
    'passed',all([checks.passed]),'checks',checks, ...
    'safety_certification_implemented',false, ...
    'notes','Synthetic algebraic fixtures only; no physical input set frozen.');
if nargin>0
    fid=fopen(output_json,'w','n','UTF-8'); assert(fid~=-1); closer=onCleanup(@() fclose(fid));
    fprintf(fid,'%s\n',jsonencode(report,PrettyPrint=true));
end
fprintf('A02 TEST_ONLY: %d/%d checks passed; research calls 0.\n',sum([checks.passed]),numel(checks));
assert(report.passed,'htp:PrecheckFailure','One or more model prechecks failed.');

    function addcheck(name, fn)
        try
            fn(); ok=true;
        catch ME
            ok=false; fprintf(2,'FAILED %s: %s\n',name,ME.message);
        end
        checks(end+1)=struct('name',name,'passed',ok);
    end
end

function s=alpha_spec(x)
s=struct('kind','alpha','freq_Hz',[1 2],'dref_s',3,'fref_Hz',2,'sensitivity',x);
end
function check_alpha_inverse
assert(htp_stage_duration(alpha_spec(1),1)==6);
end
function check_alpha_flat
assert(htp_stage_duration(alpha_spec(0),1)==3);
end
function check_illegal
expect_error(@() htp_stage_duration(alpha_spec(.5),1.5),'htp:IllegalOPP');
end
function check_cycles
s=struct('kind','cycles_pwl','freq_Hz',[1 2 4 8],'a_s',[0;1],'b_cycles',[4;0]);
x=arrayfun(@(f) htp_stage_duration(s,f),s.freq_Hz);
assert(isequal(x,[4 2 1 1]));
end
function check_table
s=struct('kind','table','freq_Hz',[1 2],'duration_s',[3 2.5]);
assert(htp_stage_duration(s,2)==2.5);
expect_error(@() htp_stage_duration(s,1.5),'htp:IllegalOPP');
end
function check_scalar
x=htp_thermal_segment(2,.5,1,0,.4,3);
assert(abs(x.end_theta_K-(2+(.4-2)*exp(-.75)))<1e-12);
assert(abs(x.energy_J-3)<1e-12);
end
function check_leakage
c=2;g=.5;l=.1;b=1;t=3;x0=.4; a=-(g-l)/c; eq=b/(g-l);
x=htp_thermal_segment(c,g,b,l,x0,t);
integ=eq*t+(x0-eq)*expm1(a*t)/a;
assert(abs(x.end_theta_K-(eq+(x0-eq)*exp(a*t)))<1e-12);
assert(abs(x.energy_J-(b*t+l*integ))<1e-12);
end
function check_cooling
x=htp_thermal_segment(2,.5,0,0,2,3);
assert(abs(x.end_theta_K-2*exp(-.75))<1e-12 && x.energy_J==0);
end
function check_split
c=[2;3];g=[.8 -.2;-.2 .7];b=[1;.2];l=[.02;.01];x0=[2;1];
a=htp_thermal_segment(c,g,b,l,x0,3);
p=htp_thermal_segment(c,g,b,l,x0,1);
q=htp_thermal_segment(c,g,b,l,p.end_theta_K,2);
assert(norm(a.end_theta_K-q.end_theta_K,inf)<1e-12);
assert(abs(a.energy_J-p.energy_J-q.energy_J)<1e-12);
end
function check_internal_peak
x=htp_thermal_segment([1;1],[2 -1;-1 2],[0;0],[0;0],[10;0],3);
t=log(3)/2; p=x.sample(t); start=x.sample(0);
expected=5*(exp(-t)-exp(-3*t));
assert(abs(p.theta_K(2)-expected)<1e-12);
assert(p.theta_K(2)>start.theta_K(2) && p.theta_K(2)>x.end_theta_K(2));
assert(strcmp(x.safety_status,'UNASSESSED'));
end
function check_ode
c=[2;3];g=[.8 -.2;-.2 .7];b=[1;.2];l=[.02;.01];x0=[2;1];
x=htp_thermal_segment(c,g,b,l,x0,3);
rhs=@(~,z) [(-g*z(1:2)+b+l.*z(1:2))./c;sum(b+l.*z(1:2))];
[ts,z]=ode45(rhs,linspace(0,3,17),[x0;0],odeset('RelTol',1e-11,'AbsTol',1e-12));
for j=1:numel(ts)
 s=x.sample(ts(j)); assert(norm([s.theta_K;s.energy_J]-z(j,:)',inf)<1e-9);
end
end
function check_zero
x=htp_thermal_segment(2,.5,1,.01,2,0);
assert(x.end_theta_K==2 && x.energy_J==0);
end
function check_unstable
x=htp_thermal_segment(1,1,1,2,0,1);
assert(~x.stable_numerical_indicator && strcmp(x.safety_status,'UNASSESSED'));
end
function check_invalid
expect_error(@() htp_thermal_segment([1;1],[2 1;1 2],[0;0],[0;0],[0;0],1),'htp:PassiveConductance');
expect_error(@() htp_thermal_segment([1;1],[1 -1;-1 1],[0;0],[0;0],[0;0],1),'htp:NoHeatSink');
end
function expect_error(fn,id)
try
 fn();
catch ME
 assert(strcmp(ME.identifier,id),'Unexpected error identifier.'); return;
end
error('htp:ExpectedError','Expected invalid input to be rejected.');
end
