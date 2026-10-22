function out = htp_schedule_nominal(x, schedule)
%HTP_SCHEDULE_NOMINAL Independent double event/accounting/trajectory path.
% Exact legality and continuous safety belong to the interval sidecar.
nodes=cellstr(string(x.thermal.node_order)); n=numel(nodes); entries=schedule.entries;
assert(numel(entries)==numel(x.workload.stages),'htp:Coverage','Missing Stage.');
a=zeros(numel(entries),1); b=a; chosen=cell(numel(entries),1);
for j=1:numel(entries)
    e=entries(j); m=x.mode_table(strcmp({x.mode_table.id},e.mode_id));
    assert(isscalar(m) && strcmp(m.stage_id,e.stage_id),'htp:Mode','Illegal Stage mode.');
    chosen{j}=m; a(j)=scalar(e.start_s); b(j)=a(j)+m.duration_s;
end
W=x.workload.window_s; events=unique([0;W;a;b]); assert(events(1)==0 && events(end)==W);
theta=x.thermal.initial_temperature_degC(:)-x.thermal.ambient_temperature_degC;
C=x.thermal.heat_capacity_J_per_K(:); G=x.thermal.conductance_W_per_K;
energy=0; baseline=0; activity_energy=0; trace=zeros(numel(events),n); trace(1,:)=theta'+x.thermal.ambient_temperature_degC;
segments=struct('start_s',{},'end_s',{},'baseline_W',{},'activity_W',{},'lambda_W_per_K',{},'energy_J',{});
for z=1:numel(events)-1
    left=events(z); right=events(z+1); active=find(a<=left & b>left);
    base=zeros(n,1); activity=zeros(n,1); leak=zeros(n,1);
    for k=1:numel(x.frequency_domains)
        d=x.frequency_domains(k); ids=cell(0,1);
        for j=active'
            if strcmp(chosen{j}.domain_id,d.id), ids{end+1}=chosen{j}.opp_id; end %#ok<AGROW>
        end
        ids=unique(ids); assert(numel(ids)<=1,'htp:DomainConflict','Mixed frequencies.');
        if isempty(ids), opp=d.opps(1); else, opp=d.opps(strcmp({d.opps.id},ids{1})); end
        for u=cellstr(string(d.unit_ids))'
            unit=x.execution_units(strcmp({x.execution_units.id},u{1})); at=find(strcmp(nodes,unit.thermal_node));
            base(at)=base(at)+opp.baseline_per_unit_W; leak(at)=leak(at)+opp.local_leakage_W_per_K;
        end
    end
    at=find(strcmp(nodes,x.shared_system.node)); base(at)=base(at)+x.shared_system.baseline_W; leak(at)=leak(at)+x.shared_system.leakage_W_per_K;
    for j=active'
        m=chosen{j}; unit=x.execution_units(strcmp({x.execution_units.id},m.unit_id)); at=find(strcmp(nodes,unit.thermal_node));
        activity(at)=activity(at)+m.local_activity_W;
        at=find(strcmp(nodes,x.shared_system.node)); activity(at)=activity(at)+m.shared_activity_W;
    end
    v=htp_thermal_segment(C,G,base+activity,leak,theta,right-left);
    theta=v.end_theta_K; energy=energy+v.energy_J;
    baseline=baseline+sum(base)*(right-left); activity_energy=activity_energy+sum(activity)*(right-left);
    trace(z+1,:)=theta'+x.thermal.ambient_temperature_degC;
    segments(end+1)=struct('start_s',left,'end_s',right,'baseline_W',base','activity_W',activity','lambda_W_per_K',leak','energy_J',v.energy_J); %#ok<AGROW>
end
out=struct('state','UNASSESSED','energy_J',energy,'baseline_J',baseline,'activity_J',activity_energy, ...
    'temperature_correction_J',energy-baseline-activity_energy,'final_temperature_degC',trace(end,:), ...
    'trace_time_s',events','trace_temperature_degC',trace,'segments',segments, ...
    'scope','Double precision nominal result; no continuous safety conclusion');
end
function value=scalar(x)
if isnumeric(x), value=x; else
    terms=split(string(x),'/'); value=str2double(terms(1));
    if numel(terms)==2, value=value/str2double(terms(2)); end
end
assert(isscalar(value) && isfinite(value));
end
