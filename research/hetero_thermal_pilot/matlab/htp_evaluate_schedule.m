function result = htp_evaluate_schedule(schedule_spec, output_json, python_executable, seconds)
%HTP_EVALUATE_SCHEDULE MATLAB nominal path plus exact continuous sidecar.
% schedule_spec: A03 fixture ID or path to an exact-decimal/rational JSON file.
if nargin<4, seconds=60; end
assert(seconds>0 && seconds<=60); started=tic;
root=fileparts(fileparts(mfilename('fullpath'))); [x,meta]=htp_load_a03;
ids={x.schedule_fixtures.id}; isfixture=any(strcmp(ids,schedule_spec));
expected_schedule_sha256='';
if isfixture, schedule=x.schedule_fixtures(strcmp(ids,schedule_spec)); kind='--fixture';
else
    assert(isfile(schedule_spec)); [schedule,expected_schedule_sha256]=read_schedule(schedule_spec); kind='--schedule';
end
raw_path=[char(output_json) '.certificate.json']; remaining=seconds-toc(started);
if remaining<=1e-8
    result=struct('state','UNRESOLVED','reason','ENTRY_BUDGET_EXHAUSTED','rankable_energy',false, ...
        'complete',false,'energy_J',[],'technical_issue',false,'entry_budget_exhausted',true, ...
        'entry_evidence_in_budget',false,'budget_admissible_violation',false,'entry_elapsed_s',toc(started),'input_sha256',meta.input_sha256);
    write_result(output_json,result); return
end
command=sprintf('%s -B %s %s %s --seconds %.9f --output %s', ...
    quoted(python_executable),quoted(fullfile(root,'evaluator','cli.py')),kind,quoted(schedule_spec),remaining,quoted(raw_path));
[code,console]=system(command);
assert(code==0 && isfile(raw_path),'htp:Sidecar','Certificate sidecar failed: %s',console);
certificate=jsondecode(fileread(raw_path));
assert(isfield(certificate,'input_sha256') && strcmp(certificate.input_sha256,meta.input_sha256),'htp:Binding','Certificate input identity mismatch.');
if isfixture
    assert(strcmp(certificate.fixture_id,schedule_spec),'htp:Binding','Fixture identity mismatch.');
else
    early_budget=strcmp(certificate.state,'UNRESOLVED') && isfield(certificate,'budget_exhausted') && certificate.budget_exhausted && ...
        ~certificate.complete && ~certificate.rankable_energy && isempty(certificate.energy_J) && ...
        ~isfield(certificate,'schedule_legal') && isempty(certificate.violations);
    if ~early_budget
        assert(strcmp(certificate.schedule_sha256,expected_schedule_sha256),'htp:Binding','Schedule changed during evaluation.');
    end
end
result=htp_certificate_state(certificate); result.certificate=certificate;
result.matlab_nominal=[]; result.input_sha256=meta.input_sha256;
if isfield(certificate,'schedule_legal') && certificate.schedule_legal
    try
        nominal=htp_schedule_nominal(x,schedule); result.matlab_nominal=nominal;
        raw=certificate.power_segments; assert(numel(raw)==numel(nominal.segments),'htp:CrossCheck','Segment count mismatch.');
        nodes=cellstr(string(x.thermal.node_order)); mismatch=0;
        for z=1:numel(raw)
            mismatch=max(mismatch,abs(scalar(raw(z).start_ms)/1000-nominal.segments(z).start_s));
            mismatch=max(mismatch,abs(scalar(raw(z).end_ms)/1000-nominal.segments(z).end_s));
            for j=1:numel(nodes)
                node=nodes{j}; s=nominal.segments(z);
                mismatch=max([mismatch,abs(scalar(raw(z).baseline_by_node_W.(node))-s.baseline_W(j)), ...
                    abs(scalar(raw(z).activity_by_node_W.(node))-s.activity_W(j)), ...
                    abs(scalar(raw(z).local_leakage_slope_W_per_K.(node))-s.lambda_W_per_K(j))]);
            end
        end
        assert(mismatch<=1e-12,'htp:CrossCheck','Event or accounting mismatch.');
        result.event_and_power_max_abs_discrepancy=mismatch;
        if certificate.complete
            result.energy_distance_to_interval_J=distance(nominal.energy_J,certificate.energy_J);
            result.final_temperature_distance_to_interval_K=0;
            for j=1:numel(nodes)
                result.final_temperature_distance_to_interval_K=max(result.final_temperature_distance_to_interval_K, ...
                    distance(nominal.final_temperature_degC(j),certificate.final_temperature_degC.(nodes{j})));
            end
            assert(result.energy_distance_to_interval_J<=1e-10 && result.final_temperature_distance_to_interval_K<=1e-8, ...
                'htp:CrossCheck','Nominal and certified propagation disagree.');
        end
    catch ME
        result.technical_issue=true; result.technical_details=ME.message;
        if ~strcmp(certificate.state,'THERMAL_VIOLATION'), result.state='UNRESOLVED'; end
        result.rankable_energy=false;
    end
end
result.entry_elapsed_s=toc(started);
result.entry_evidence_in_budget=result.entry_elapsed_s<=seconds;
result.budget_admissible_violation=strcmp(certificate.state,'THERMAL_VIOLATION') && result.entry_evidence_in_budget;
if result.entry_elapsed_s>seconds
    result.rankable_energy=false; result.entry_budget_exhausted=true;
    if ~strcmp(certificate.state,'THERMAL_VIOLATION'), result.state='UNRESOLVED'; end
end
result.numeric_scope='MATLAB doubles checked against independent exact-input Decimal interval evaluation; model uncertainty not included';
write_result(output_json,result);
end
function s=quoted(x)
x=char(x); assert(isempty(regexp(x,'["\r\n&|<>^%]','once')),'htp:Path','Unsupported shell metacharacter.'); s=['"' x '"'];
end
function value=scalar(x)
if isnumeric(x), value=x; else
    terms=split(string(x),'/'); value=str2double(terms(1));
    if numel(terms)==2, value=value/str2double(terms(2)); end
end
assert(isscalar(value) && isfinite(value));
end
function d=distance(value,interval)
lo=scalar(interval{1}); hi=scalar(interval{2}); d=max([0,lo-value,value-hi]);
end

function [schedule,digest_hex]=read_schedule(path)
fid=fopen(path,'rb'); assert(fid~=-1); closer=onCleanup(@() fclose(fid)); bytes=fread(fid,Inf,'*uint8');
schedule=jsondecode(native2unicode(bytes(:)','UTF-8'));
digest=java.security.MessageDigest.getInstance('SHA-256'); digest.update(bytes);
digest_hex=lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
end

function write_result(path,result)
fid=fopen(path,'w','n','UTF-8'); assert(fid~=-1); closer=onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(result,PrettyPrint=true));
end
