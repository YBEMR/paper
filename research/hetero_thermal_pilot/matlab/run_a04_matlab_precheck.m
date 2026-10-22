function report = run_a04_matlab_precheck(output_dir, python_executable)
%RUN_A04_MATLAB_PRECHECK Existing A03 plumbing fixtures only, not a search.
if ~isfolder(output_dir), mkdir(output_dir); end
root=fileparts(fileparts(mfilename('fullpath'))); [x,meta]=htp_load_a03;
checks=struct('name',{},'passed',{},'detail',{}); results=cell(1,2);
addcheck('parallel_fixture_full_MATLAB_and_interval_path',@() full(1));
addcheck('shifted_fixture_full_MATLAB_and_interval_path',@() full(2));
addcheck('independent_events_power_and_final_states_agree',@agreement);
addcheck('idle_tail_and_shared_node_fully_present',@tail);
addcheck('unchanged_frozen_source_and_two_request_completion',@binding);
addcheck('illegal_schedule_has_no_rankable_energy',@invalid);
addcheck('technical_and_partial_certificate_states_preserved',@states);
addcheck('early_entry_expiry_is_structured_unresolved',@early_expiry);
report=struct('kind','TEST_ONLY','matlab_version',version,'passed',all([checks.passed]), ...
    'checks',checks,'input_sha256',meta.input_sha256,'research_optimizer_calls',0, ...
    'scope','Two pre-existing A03 evaluator fixtures; no device selection or method comparison');
fid=fopen(fullfile(output_dir,'matlab_precheck.json'),'w','n','UTF-8'); assert(fid~=-1); closer=onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,PrettyPrint=true));
fprintf('A04 MATLAB integration: %d/%d checks passed.\n',sum([checks.passed]),numel(checks));
assert(report.passed,'htp:A04PrecheckFailed','One or more A04 MATLAB checks failed.');
    function addcheck(name,fn)
        try, fn(); ok=true; detail='';
        catch ME, ok=false; detail=ME.message; fprintf(2,'FAILED %s: %s\n',name,ME.message); end
        checks(end+1)=struct('name',name,'passed',ok,'detail',detail);
    end
    function full(j)
        id=x.schedule_fixtures(j).id;
        results{j}=htp_evaluate_schedule(id,fullfile(output_dir,[id '.json']),python_executable,60);
        r=results{j}; assert(strcmp(r.state,'SAFE') && r.rankable_energy && ~r.technical_issue);
        assert(r.certificate.complete && r.certificate.energy_accuracy_met);
    end
    function agreement
        for j=1:2
            r=results{j}; assert(~isempty(r) && ~r.technical_issue);
            assert(r.event_and_power_max_abs_discrepancy<=1e-12);
            assert(r.energy_distance_to_interval_J<=1e-10 && r.final_temperature_distance_to_interval_K<=1e-8);
            assert(numel(r.matlab_nominal.final_temperature_degC)==5);
        end
    end
    function tail
        for j=1:2
            r=results{j}; last=r.certificate.power_segments(end);
            assert(strcmp(last.end_ms,'1000') && isempty(last.active_stage_ids));
            assert(strcmp(last.domain_opps.C,'L') && strcmp(last.domain_opps.G,'L') && strcmp(last.domain_opps.N,'L'));
            assert(strcmp(last.baseline_by_node_W.U,'13/20') && last.external_common_power_W==0);
            assert(r.matlab_nominal.trace_time_s(end)==1);
        end
    end
    function binding
        [~,again]=htp_load_a03; assert(strcmp(meta.input_sha256,again.input_sha256));
        for j=1:2
            r=results{j}; assert(strcmp(r.input_sha256,meta.input_sha256));
            assert(numel(fieldnames(r.certificate.request_completion_s))==2);
        end
    end
    function states
        c=struct('state','SAFE','complete',true,'rankable_energy',true,'energy_accuracy_met',true,'energy_J',{{'1','2'}},'violations',[],'technical_issue',false,'reason','COMPLETE_CONTINUOUS_ENCLOSURE');
        r=htp_certificate_state(c); assert(strcmp(r.state,'SAFE') && r.rankable_energy && ~r.technical_issue);
        bad=c; bad.technical_issue=true; r=htp_certificate_state(bad); assert(strcmp(r.state,'UNRESOLVED') && ~r.rankable_energy && r.technical_issue);
        bad=c; bad.state='UNRESOLVED'; bad.reason='NUMERICAL_ERROR'; r=htp_certificate_state(bad); assert(r.technical_issue && ~r.rankable_energy);
        bad.reason='RESOURCE_LIMIT'; r=htp_certificate_state(bad); assert(r.technical_issue);
        bad=c; bad.complete=false; r=htp_certificate_state(bad); assert(strcmp(r.state,'UNRESOLVED') && ~r.rankable_energy);
        bad=c; bad.state='THERMAL_VIOLATION'; bad.reason='NUMERICAL_ERROR'; bad.violations=1;
        r=htp_certificate_state(bad); assert(strcmp(r.state,'THERMAL_VIOLATION') && r.technical_issue && ~r.rankable_energy);
    end
    function early_expiry
        r=htp_evaluate_schedule(x.schedule_fixtures(1).id,fullfile(output_dir,'early_budget.json'),python_executable,1e-6);
        assert(strcmp(r.state,'UNRESOLVED') && ~r.rankable_energy && ~r.technical_issue && r.entry_budget_exhausted);
    end
    function invalid
        cache=fullfile(root,'.runtime_a04'); if ~isfolder(cache), mkdir(cache); end
        s=x.schedule_fixtures(1); s.entries(end)=[]; path=fullfile(cache,'missing_stage.json');
        fid2=fopen(path,'w','n','UTF-8'); assert(fid2~=-1); fprintf(fid2,'%s',jsonencode(s)); fclose(fid2);
        r=htp_evaluate_schedule(path,fullfile(output_dir,'invalid_missing_stage.json'),python_executable,60);
        assert(strcmp(r.state,'INVALID_SCHEDULE') && ~r.rankable_energy && isempty(r.matlab_nominal));
    end
end
