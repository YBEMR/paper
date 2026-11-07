function solve_lp_once(workdir, guard_seconds)
% One independent R2023b continuous-LP diagnostic; never repeats a solve.
% Python's absolute method deadline is authoritative. Local clocks only
% reduce the one native MaxTime and stop waiting; they never grant more time.
t0 = tic;
validateattributes(guard_seconds, {'numeric'}, ...
    {'scalar','real','finite','positive'}, mfilename, 'guard_seconds');
if ~isfolder(workdir)
    error('lpDiagnostic:Workdir', 'Work directory does not exist');
end
ready = struct('version',version,'release',version('-release'), ...
    'linprog_path',which('linprog'), ...
    'license_test',license('test','Optimization_Toolbox'));
[license_ok,license_message] = license('checkout','Optimization_Toolbox');
ready.license_checkout = logical(license_ok);
ready.license_message = license_message;
ready.worker_elapsed_seconds = toc(t0);
if license_ok && ~isempty(ready.linprog_path)
    ready.status = 'READY';
else
    ready.status = 'TOOLBOX_UNAVAILABLE';
end
write_json_atomic(fullfile(workdir,'ready.json'),ready);
if ~strcmp(ready.status,'READY'), return; end

request_path = fullfile(workdir,'request.json');
payload_path = fullfile(workdir,'payload.mat');
while ~(isfile(request_path) && isfile(payload_path))
    if toc(t0)>=guard_seconds || stopped(workdir), return; end
    pause(min(.01,max(0,guard_seconds-toc(t0))));
end
request_clock = tic;
result = struct('status','ERROR','x',[],'fval',[],'exitflag',[], ...
    'output',struct(),'lambda',struct(),'linprog_entered',false, ...
    'phase_seconds',struct(),'options',struct(), ...
    'solver_warning_message','','solver_warning_identifier','', ...
    'native_console_file','native_console.txt', ...
    'solver_information_is_independently_certified',false, ...
    'thermal_integrations',0,'new_safe_U',false, ...
    'deadline_authority','Python absolute monotonic method deadline', ...
    'interface_scope','independent linprog; not intlinprog internal root LP');
x=[]; fval=[]; exitflag=[]; output=struct(); lambda=struct(); opts=[];
native_error=struct(); warning_message=''; warning_identifier='';
console_cleanup=[];
try
    phase_clock=tic;
    req=jsondecode(fileread(request_path));
    if ~isfield(req,'remaining_s')
        error('lpDiagnostic:RequestBudget','Request has no remaining_s');
    end
    validateattributes(req.remaining_s, {'numeric'}, ...
        {'scalar','real','finite','positive','<=',300}, mfilename, 'remaining_s');
    result.request_remaining_s=req.remaining_s;
    names={'c','A','b','Aeq','beq','lb','ub'};
    file_variables=whos('-file',payload_path);
    if ~isequal(sort({file_variables.name}),sort(names))
        error('lpDiagnostic:PayloadFields', ...
            'Payload must contain exactly c/A/b/Aeq/beq/lb/ub');
    end
    p=load(payload_path,names{:});
    result.payload_fields=names;
    result.phase_seconds.request_and_mat_load=toc(phase_clock);

    phase_clock=tic;
    opts=optimoptions('linprog','Algorithm','dual-simplex', ...
        'Display','off','ConstraintTolerance',1e-9, ...
        'OptimalityTolerance',1e-7,'MaxIterations',2049240);
    % R2023b explicitly supports this hidden property. It must not silently
    % fall back to the default preprocessing setting.
    opts.Preprocess='none';
    opts.MaxTime=remaining_time(req,request_clock,t0,guard_seconds);
    actual=read_selected_options(opts);
    check_selected_options(actual);
    options_guard=struct('status','PASS','actual',actual, ...
        'worker_elapsed_seconds',toc(t0), ...
        'request_elapsed_seconds',toc(request_clock), ...
        'MaxTime_scope','provisional readback; reduced again at native entry', ...
        'expected',struct('Algorithm','dual-simplex','Preprocess','none', ...
        'ConstraintTolerance',1e-9,'OptimalityTolerance',1e-7, ...
        'MaxIterations',2049240,'Display','off'));
    write_json_atomic(fullfile(workdir,'options_guard.json'),options_guard);
    result.phase_seconds.options_preparation=toc(phase_clock);

    if stopped(workdir) || remaining_time(req,request_clock,t0,guard_seconds)<=0
        result.status='BUDGET_EXHAUSTED_BEFORE_SOLVER';
    else
        % This marker says the unique invocation is about to be attempted.
        % Its serialization is charged before the final native allocation.
        entered=struct('kind','solver_entered','request_number',1, ...
            'worker_elapsed_seconds',toc(t0), ...
            'request_elapsed_seconds',toc(request_clock), ...
            'meaning','unique native invocation prepared; response.linprog_entered confirms entry', ...
            'native_call_may_be_cancelled_before_entry',true, ...
            'MaxTime_before_final_entry_update',opts.MaxTime);
        write_json_atomic(fullfile(workdir,'solver_entered.json'),entered);
        diary(fullfile(workdir,'native_console.txt'));
        diary on;
        console_cleanup=onCleanup(@()diary('off'));
        % Include payload loading, option readback and publication in this
        % request's remaining time. No x0 or integer-index argument exists.
        opts.MaxTime=remaining_time(req,request_clock,t0,guard_seconds);
        actual=read_selected_options(opts);
        check_selected_options(actual);
        result.options=actual;
        if stopped(workdir) || opts.MaxTime<=0
            result.status='BUDGET_EXHAUSTED_BEFORE_SOLVER';
        else
            result.linprog_entered=true;
            result.native_entered_worker_seconds=toc(t0);
            result.native_entered_request_seconds=toc(request_clock);
            phase_clock=tic;
            lastwarn('');
            [x,fval,exitflag,output,lambda]=linprog( ...
                p.c,p.A,p.b,p.Aeq,p.beq,p.lb,p.ub,opts);
            result.phase_seconds.linprog_call=toc(phase_clock);
            result.native_returned_worker_seconds=toc(t0);
            result.native_returned_request_seconds=toc(request_clock);
            [warning_message,warning_identifier]=lastwarn;
            result.x=x(:)'; result.fval=fval; result.exitflag=exitflag;
            result.output=output; result.lambda=lambda;
            result.status='SOLVED';
        end
    end
catch err
    if result.linprog_entered && exist('phase_clock','var')
        result.phase_seconds.linprog_call=toc(phase_clock);
    end
    [warning_message,warning_identifier]=lastwarn;
    native_error=struct('identifier',err.identifier, ...
        'message',err.message,'report',getReport(err,'extended','hyperlinks','off'));
    result.error_identifier=err.identifier;
    result.error_message=native_error.report;
end
if ~isempty(console_cleanup), clear console_cleanup; end
result.solver_warning_message=warning_message;
result.solver_warning_identifier=warning_identifier;
result.warning_capture_scope='native_console.txt plus lastwarn; no warning policy changed';
if isempty(fieldnames(result.options)) && ~isempty(opts)
    try
        result.options=read_selected_options(opts);
    catch option_error
        result.option_archive_error=option_error.message;
    end
end
% Native MAT preserves every result field, including nonfinite values that
% JSON represents as null. Archival does not create a new numerical result.
phase_clock=tic;
try
    temporary_native=fullfile(workdir,'native.tmp.mat');
    save(temporary_native,'x','fval','exitflag','output','lambda','opts', ...
        'native_error','warning_message','warning_identifier');
    atomic_move(temporary_native,fullfile(workdir,'native.mat'));
    result.phase_seconds.native_result_archive=toc(phase_clock);
catch archive_error
    result.native_archive_error=struct('identifier',archive_error.identifier, ...
        'message',archive_error.message);
end
result.matlab_request_wall_seconds=toc(request_clock);
result.worker_elapsed_seconds=toc(t0);
result.request_count_max=1;
write_json_atomic(fullfile(workdir,'response.json'),result);
end

function seconds=remaining_time(req,request_clock,t0,guard_seconds)
seconds=max(0,min(req.remaining_s-toc(request_clock),guard_seconds-toc(t0)));
end

function flag=stopped(workdir)
flag=isfile(fullfile(workdir,'stop')) || isfile(fullfile(workdir,'cancel'));
end

function actual=read_selected_options(opts)
names={'Algorithm','Preprocess','ConstraintTolerance','OptimalityTolerance', ...
    'MaxIterations','Display','MaxTime'};
actual=struct();
for i=1:numel(names), actual.(names{i})=opts.(names{i}); end
end

function check_selected_options(actual)
expected=struct('Algorithm','dual-simplex','Preprocess','none', ...
    'ConstraintTolerance',1e-9,'OptimalityTolerance',1e-7, ...
    'MaxIterations',2049240,'Display','off');
names=fieldnames(expected);
for i=1:numel(names)
    if ~isequal(actual.(names{i}),expected.(names{i}))
        error('lpDiagnostic:OptionDrift','Unexpected actual option %s',names{i});
    end
end
if ~isnumeric(actual.MaxTime) || ~isscalar(actual.MaxTime) || ...
        ~isreal(actual.MaxTime) || ~isfinite(actual.MaxTime) || actual.MaxTime<0
    error('lpDiagnostic:MaxTime','Native MaxTime must be finite and nonnegative');
end
end

function write_json_atomic(path,value)
temporary=[path '.tmp'];
fid=fopen(temporary,'w','n','UTF-8');
if fid<0, error('lpDiagnostic:OutputOpen','Cannot open %s',temporary); end
closer=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(value));
clear closer;
atomic_move(temporary,path);
end

function atomic_move(source_path,destination_path)
source_file=javaObject('java.io.File',source_path);
destination_file=javaObject('java.io.File',destination_path);
move_options=javaArray('java.nio.file.CopyOption',2);
move_options(1)=javaMethod('valueOf','java.nio.file.StandardCopyOption','ATOMIC_MOVE');
move_options(2)=javaMethod('valueOf','java.nio.file.StandardCopyOption','REPLACE_EXISTING');
javaMethod('move','java.nio.file.Files',source_file.toPath(), ...
    destination_file.toPath(),move_options);
end
