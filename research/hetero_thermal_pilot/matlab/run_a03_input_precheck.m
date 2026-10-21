function report = run_a03_input_precheck(output_json)
%RUN_A03_INPUT_PRECHECK Loader and mode-table checks, no thermal propagation.
root=fileparts(fileparts(mfilename('fullpath'))); [x,meta]=htp_load_a03;
checks=struct('name',{},'passed',{},'detail',{}); max_d=0; max_q=0;
addcheck('frozen_source_hash_loaded', @() assert(numel(meta.input_sha256)==64));
addcheck('five_node_physical_conductance', @physical);
addcheck('all_36_response_values_from_existing_kernel', @durations);
addcheck('all_36_local_and_shared_activity_values', @powers);
addcheck('continuous_starts_and_fractional_ms_endpoints_retained', @time_domain);
addcheck('two_complete_fixture_records_read_without_evaluation', @fixtures);
addcheck('modified_source_rejected_by_loader', @modified_input);
report=struct('kind','INPUT_ONLY_TEST','matlab_version',version,'passed',all([checks.passed]), ...
    'checks',checks,'input_sha256',meta.input_sha256,'modes_checked',numel(x.mode_table), ...
    'max_duration_abs_error_s',max_d,'max_local_power_abs_error_W',max_q, ...
    'research_calls',0,'thermal_propagations',0,'safety_status','UNASSESSED');
if nargin>0
    fid=fopen(output_json,'w','n','UTF-8'); assert(fid~=-1); closer=onCleanup(@() fclose(fid));
    fprintf(fid,'%s\n',jsonencode(report,PrettyPrint=true));
end
fprintf('A03 MATLAB input checks: %d/%d; 36 modes; no thermal evaluation.\n',sum([checks.passed]),numel(checks));
assert(report.passed,'htp:A03PrecheckFailed','One or more A03 input checks failed.');
    function addcheck(name,fn)
        try, fn(); ok=true; detail='';
        catch ME, ok=false; detail=ME.message; fprintf(2,'FAILED %s: %s\n',name,ME.message); end
        checks(end+1)=struct('name',name,'passed',ok,'detail',detail);
    end
    function physical
        t=x.thermal; G=t.conductance_W_per_K; C=t.heat_capacity_J_per_K(:);
        assert(isequal(size(G),[5 5]) && norm(G-G',Inf)==0 && all(C>0));
        assert(norm(sum(G,2)-t.ambient_conductance_W_per_K(:),Inf)<1e-14);
        worst=[.003;.003;.006;.005;.003]; [~,flag]=chol(G-diag(worst)); assert(flag==0);
    end
    function [pr,o,j]=parts(m)
        pr=x.profiles(strcmp({x.profiles.id},m.profile_id));
        d=x.frequency_domains(strcmp({x.frequency_domains.id},m.domain_id));
        j=find(strcmp({d.opps.id},m.opp_id)); o=d.opps(j); assert(isscalar(pr) && isscalar(o));
    end
    function durations
        for z=1:numel(x.mode_table)
            m=x.mode_table(z); [pr,o,~]=parts(m);
            computed=htp_stage_duration(pr.response,o.frequency_Hz);
            max_d=max(max_d,abs(computed-m.duration_s));
            assert(abs(computed-m.duration_s)<=5e-14);
        end
    end
    function powers
        for z=1:numel(x.mode_table)
            m=x.mode_table(z); [pr,o,j]=parts(m); a=pr.activity;
            if strcmp(a.model,'effective_capacitance'), c=a.coefficient_F;
            else, c=a.capacitance_F*a.utilization_by_opp(j); end
            computed=c*o.frequency_Hz*o.voltage_V^2;
            max_q=max(max_q,abs(computed-m.local_activity_W));
            assert(abs(computed-m.local_activity_W)<=5e-14);
            assert(pr.shared_activity_W(j)==m.shared_activity_W);
        end
    end
    function time_domain
        assert(strcmp(x.execution.start_domain,'CONTINUOUS_NONNEGATIVE'));
        m=x.mode_table(strcmp({x.mode_table.id},'A.pre@CPU0@L'));
        assert(m.duration_s==24/1024 && m.duration_s*1000~=round(m.duration_s*1000));
        assert(x.workload.window_s==1 && x.workload.requests(1).absolute_deadline_s==.5);
    end
    function fixtures
        assert(numel(x.schedule_fixtures)==2);
        for z=1:2
            f=x.schedule_fixtures(z); assert(numel(f.entries)==6);
            assert(numel(unique({f.entries.stage_id}))==6);
            for j=1:6
                e=f.entries(j); m=x.mode_table(strcmp({x.mode_table.id},e.mode_id));
                assert(isscalar(m) && strcmp(m.stage_id,e.stage_id));
                assert(e.start_s>=0 && e.start_s+m.duration_s<=.5);
            end
        end
    end
    function modified_input
        cache=fullfile(root,'.runtime_a03_input_check'); if ~isfolder(cache), mkdir(cache); end
        target=fullfile(cache,'modified.json');
        fid=fopen(target,'w'); assert(fid~=-1); fprintf(fid,'{}'); fclose(fid);
        caught=false;
        try, htp_load_a03(target);
        catch ME, caught=strcmp(ME.identifier,'htp:A03HashMismatch'); end
        assert(caught);
    end
end
