function solve_model(folder, guardSeconds)
% One R2023b worker for correctness checks or one budgeted method call. Every request is
% a new problem with no reused incumbent. An explicitly supplied, independently
% checked x0 belongs to this request only. Thermal/energy acceptance is
% performed by Python; optional live events permit in-budget incumbent checks.
workerClock = tic;
info = struct('version',version,'release',version('-release'), ...
    'intlinprog_path',which('intlinprog'),'license_test', ...
    license('test','Optimization_Toolbox'));
[ok,message] = license('checkout','Optimization_Toolbox');
info.license_checkout = logical(ok); info.license_message = message;
if ok && ~isempty(info.intlinprog_path), info.status = 'READY';
else, info.status = 'TOOLBOX_UNAVAILABLE'; end
writejson(fullfile(folder,'ready.json'),info);
if ~strcmp(info.status,'READY'), return; end
requestNumber = 1;
while toc(workerClock) < guardSeconds && ~isfile(fullfile(folder,'stop'))
    prefix = fullfile(folder,sprintf('request_%06d',requestNumber));
    if ~isfile([prefix '.request.json']), pause(.01); continue; end
    requestClock = tic; callbacks = {}; callbackFields = {}; callbackError = '';
    streamEvents = false; eventNumber = 0;
    result = struct('status','ERROR','x',[],'fval',[],'exitflag',[], ...
        'output',struct(),'callbacks',{{}},'callback_fields',{{}}, ...
        'intlinprog_entered',false,'phase_seconds',struct(), ...
        'initial_point',struct('provided',false));
    try
        phaseClock=tic;
        [requestText,readInfo,readError] = read_request_text(prefix,folder,workerClock,guardSeconds);
        result.request_publication_read=readInfo;
        if ~isempty(readError), throw(readError); end
        % Atomic publication can still be temporarily locked on Windows.
        % Only file-open failures are retried; complete malformed JSON is an
        % immediate protocol error, not a transient publication to accept.
        req = jsondecode(requestText);
        streamEvents = isfield(req,'stream_events') && req.stream_events;
        p = load([prefix '.mat']);
        initialPoint=[];
        if isfield(p,'x0')
            initialPoint=p.x0(:);
            result.initial_point=struct('provided',true, ...
                'length',numel(initialPoint),'initial_objective',p.c(:)'*initialPoint, ...
                'thermal_safe_claim',false,'solver_acceptance','not_independently_observed');
            if isfield(p,'x0_validation')
                result.initial_point.python_admission=p.x0_validation;
            end
        end
        result.phase_seconds.request_and_mat_load=toc(phaseClock);
        phaseClock=tic;
        % A relative timer cannot represent Python's monotonic epoch or all
        % publication latency. Python's original absolute deadline governs
        % acceptance; MATLAB MaxTime/callbacks provide best-effort stopping.
        remaining = req.remaining_s;
        % This optional cap applies only to one native solve. The request's
        % original remaining time and Python's evidence deadline are unchanged.
        hasSolverTimeCap=isfield(req,'solver_max_time_s');
        solverTimeCap=inf;
        if hasSolverTimeCap
            solverTimeCap=req.solver_max_time_s;
            declaredSolverTimeCap=req.solver_max_time_s_declared;
            if ~isnumeric(solverTimeCap) || ~isscalar(solverTimeCap) ...
                    || ~isreal(solverTimeCap) || isnan(solverTimeCap) || isinf(solverTimeCap) ...
                    || solverTimeCap<=0 ...
                    || ~isnumeric(declaredSolverTimeCap) || ~isscalar(declaredSolverTimeCap) ...
                    || ~isreal(declaredSolverTimeCap) || isnan(declaredSolverTimeCap) ...
                    || isinf(declaredSolverTimeCap) ...
                    || declaredSolverTimeCap<=0 || solverTimeCap>declaredSolverTimeCap
                error('chapter3:solverTimeCap','Invalid native-only MaxTime cap');
            end
            result.solver_max_time_s_declared=declaredSolverTimeCap;
            result.solver_max_time_s_allocated=solverTimeCap;
            result.solver_max_time_s_scope='native_MaxTime_only_not_response_or_evidence_deadline';
        end
        hasCutIterationLimit=isfield(req,'cut_max_iterations');
        if hasCutIterationLimit ~= isfield(p,'cut_max_iterations')
            error('chapter3:cutIterationLimit','Cut limit request/MAT declaration mismatch');
        end
        if hasCutIterationLimit
            cutIterationLimit=req.cut_max_iterations;
            if ~isnumeric(cutIterationLimit) || ~isscalar(cutIterationLimit) ...
                    || ~isreal(cutIterationLimit) || isnan(cutIterationLimit) ...
                    || isinf(cutIterationLimit) || cutIterationLimit~=fix(cutIterationLimit) ...
                    || cutIterationLimit<1 || cutIterationLimit>50 ...
                    || ~isnumeric(p.cut_max_iterations) || ~isscalar(p.cut_max_iterations) ...
                    || ~isreal(p.cut_max_iterations) || p.cut_max_iterations~=cutIterationLimit
                error('chapter3:cutIterationLimit','CutMaxIterations must be an integer from 1 to 50');
            end
            result.cut_max_iterations_declared=cutIterationLimit;
        end
        opts = optimoptions('intlinprog','Display','off', ...
            'AbsoluteGapTolerance',0,'RelativeGapTolerance',0, ...
            'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6, ...
            'IntegerPreprocess','none', ...
            'LPPreprocess','none', ...
            'OutputFcn',@callback);
        if hasCutIterationLimit
            opts.CutMaxIterations=cutIterationLimit;
            result.cut_max_iterations_actual_effective=opts.CutMaxIterations;
        end
        % Engineering compatibility setting, fixed before formal runs:
        % numeric_diagnostic04 solved the unchanged small physical model with
        % IntegerPreprocess='none', where 'basic' reported infeasible despite
        % independent feasible lifts.  This preserves the mathematical model;
        % it does not establish a general MATLAB preprocessing defect.
        % K.106's fixed-logic feasibility pair also requires LPPreprocess='none'
        % for this R2023b numerical representation. The original matrices,
        % variable domain and tolerances are unchanged. Full free-schedule
        % optimization speed is not established by that compatibility check.
        opts.MaxTime = max(0,min([remaining-toc(requestClock), ...
            guardSeconds-toc(workerClock),solverTimeCap]));
        result.options_text = evalc('disp(opts)');
        % LPPreprocess is documented for R2023b but hidden from properties().
        % Archive it explicitly; IntegerPreprocess='none' does not disable it.
        names = [properties(opts); {'LPPreprocess'}]; optionValues = struct();
        if hasCutIterationLimit, names=[names; {'CutMaxIterations'}]; end
        for k=1:numel(names)
            value=opts.(names{k});
            if isa(value,'function_handle'), value=func2str(value); end
            optionValues.(names{k})=value;
        end
        result.options = optionValues;
        % Options inspection and MAT loading belong to this same request.
        opts.MaxTime = max(0,min([remaining-toc(requestClock), ...
            guardSeconds-toc(workerClock),solverTimeCap]));
        result.options.MaxTime = opts.MaxTime;
        if hasSolverTimeCap
            result.solver_max_time_s_used=opts.MaxTime;
            solverTimeAllocation=struct('declared',declaredSolverTimeCap, ...
                'allocated',solverTimeCap,'native_MaxTime_used',opts.MaxTime, ...
                'response_deadline_shortened',false);
        end
        result.options_text = evalc('disp(opts)');
        result.phase_seconds.options_preparation=toc(phaseClock);
        if opts.MaxTime<=0 || isfile([prefix '.cancel']) ...
                || isfile(fullfile(folder,'stop')) || toc(workerClock)>=guardSeconds
            result.status='BUDGET_EXHAUSTED_BEFORE_SOLVER';
        else
            result.intlinprog_entered=true;
            if streamEvents
                entered=struct('kind','solver_entered','request_wall_seconds',toc(requestClock));
                if hasSolverTimeCap, entered.solver_time_allocation=solverTimeAllocation; end
                if hasCutIterationLimit
                    entered.cut_max_iterations_declared=cutIterationLimit;
                    entered.cut_max_iterations_actual_effective=opts.CutMaxIterations;
                end
                publish(entered);
            end
            phaseClock=tic;
            lastwarn('');
            [x,fval,exitflag,output] = intlinprog(p.c(:),p.intcon(:)', ...
                p.A,p.b(:),p.Aeq,p.beq(:),p.lb(:),p.ub(:),initialPoint,opts);
            [warningMessage,warningIdentifier]=lastwarn;
            result.solver_warning_message=warningMessage;
            result.solver_warning_identifier=warningIdentifier;
            result.phase_seconds.intlinprog_call=toc(phaseClock);
            result.x=x(:)'; result.fval=fval; result.exitflag=exitflag;
            result.output=output; result.status='SOLVED';
            if ~isempty(callbackError)
                result.status='CALLBACK_ERROR'; result.callback_error=callbackError;
            end
            % MAT retains NaN/Inf and all native solver fields independently
            % of JSON's null representation.  This is raw solver evidence.
            phaseClock=tic;
            if hasSolverTimeCap
                save([prefix '.native.mat'],'x','fval','exitflag','output','opts','callbacks', ...
                    'initialPoint','solverTimeAllocation');
            else
                save([prefix '.native.mat'],'x','fval','exitflag','output','opts','callbacks','initialPoint');
            end
            result.phase_seconds.native_result_archive=toc(phaseClock);
        end
    catch err
        if any(strcmp(err.identifier,{'chapter3:requestReadCancelled', ...
                'chapter3:requestReadStopped','chapter3:requestReadGuardExpired'}))
            result.status='BUDGET_EXHAUSTED_BEFORE_SOLVER';
        end
        result.error_identifier=err.identifier;
        result.error_message=getReport(err,'extended','hyperlinks','off');
    end
    result.callbacks=callbacks; result.callback_fields=callbackFields;
    result.matlab_request_wall_seconds=toc(requestClock);
    result.worker_elapsed_seconds=toc(workerClock);
    result.solver_information_is_independently_certified=false;
    result.callback_candidates_independently_thermal_checked=false;
    result.deadline_authority='Python absolute monotonic deadline';
    writejson([prefix '.response.json'],result);
    requestNumber=requestNumber+1;
end

    function stop = callback(x,values,state)
        stop = false;
        try
            callbackFields=union(callbackFields,fieldnames(values));
            entry=struct('state',state,'request_wall_seconds',toc(requestClock), ...
                'values',values,'x',x(:)');
            if streamEvents
                entry.kind='callback';
                publish(entry);
                % The immutable event file retains x; avoid duplicate large
                % vectors in the final response. Historical path is unchanged.
                entry.x=[]; entry.event_number=eventNumber;
            end
            callbacks{end+1}=entry; %#ok<AGROW>
            stop = toc(requestClock)>=remaining || toc(workerClock)>=guardSeconds ...
                || isfile([prefix '.cancel']) || isfile(fullfile(folder,'stop'));
        catch err
            callbackError=getReport(err,'extended','hyperlinks','off');
            stop=true;
        end
    end

    function publish(entry)
        eventNumber=eventNumber+1;
        entry.event_number=eventNumber;
        writejson(sprintf('%s.event_%06d.json',prefix,eventNumber),entry);
    end
end

function [text,info,readError] = read_request_text(prefix,folder,workerClock,guardSeconds)
% A short transport retry window, not another solve or a replenished budget.
% requestClock was started by the caller before the first read, so all time
% here is still deducted from req.remaining_s and the original worker guard.
readClock=tic; text=''; readError=[];
info=struct('attempts',0,'read_failures',0,'elapsed_s',0, ...
    'retry_window_s',2,'retry_pause_s',.01,'outcome','WAITING', ...
    'last_error_identifier','','last_error_message','');
while true
    if stop_reading(), return; end
    info.attempts=info.attempts+1;
    try
        text=fileread([prefix '.request.json']);
    catch err
        info.read_failures=info.read_failures+1;
        info.last_error_identifier=err.identifier;
        info.last_error_message=err.message;
        info.elapsed_s=toc(readClock);
        if ~strcmp(err.identifier,'MATLAB:fileread:cannotOpenFile')
            info.outcome='READ_ERROR'; readError=err; return;
        end
        if stop_reading(), return; end
        pause(min([info.retry_pause_s,info.retry_window_s-info.elapsed_s, ...
            max(0,guardSeconds-toc(workerClock))]));
        continue;
    end
    % A read that completed after cancellation, close, guard or the fixed
    % retry window must not start a solve merely because the lock cleared.
    if stop_reading(), text=''; return; end
    info.outcome='READ';
    return;
end

    function stopped = stop_reading()
        info.elapsed_s=toc(readClock);
        if toc(workerClock)>=guardSeconds
            info.outcome='WORKER_GUARD_EXHAUSTED';
            readError=MException('chapter3:requestReadGuardExpired','Worker guard expired before request read');
        elseif isfile(fullfile(folder,'stop'))
            info.outcome='STOPPED';
            readError=MException('chapter3:requestReadStopped','Worker close requested before request read');
        elseif isfile([prefix '.cancel'])
            info.outcome='CANCELLED';
            readError=MException('chapter3:requestReadCancelled','Request cancelled before request read');
        elseif info.elapsed_s>=info.retry_window_s
            info.outcome='RETRY_LIMIT';
            readError=MException('chapter3:requestReadTimeout', ...
                'Request remained unreadable for %.3g s; last error [%s]: %s', ...
                info.retry_window_s,info.last_error_identifier,info.last_error_message);
        end
        stopped=~isempty(readError);
    end
end

function writejson(path,value)
temporary=[path '.tmp'];
fid=fopen(temporary,'w','n','UTF-8');
if fid<0,error('chapter3:bridgeOutput','Cannot open output %s',temporary);end
cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(value));
clear cleanup % close before exposing the final name
% Same-directory atomic rename uses MATLAB's bundled JVM, not a new solver
% or external dependency.  A receiver still retries transient Windows locks
% under its original deadline and never accepts a partially readable message.
sourceFile=javaObject('java.io.File',temporary); source=sourceFile.toPath();
destinationFile=javaObject('java.io.File',path); destination=destinationFile.toPath();
options=javaArray('java.nio.file.CopyOption',2);
options(1)=javaMethod('valueOf','java.nio.file.StandardCopyOption','ATOMIC_MOVE');
options(2)=javaMethod('valueOf','java.nio.file.StandardCopyOption','REPLACE_EXISTING');
javaMethod('move','java.nio.file.Files',source,destination,options);
end
