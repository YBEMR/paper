function solve_model(folder, guardSeconds)
% One R2023b worker for small-domain correctness prechecks.  Every request is
% a new problem with no x0 or reused incumbent.  Thermal/energy acceptance is
% performed by Python after this solver-reported result has been returned.
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
    result = struct('status','ERROR','x',[],'fval',[],'exitflag',[], ...
        'output',struct(),'callbacks',{{}},'callback_fields',{{}});
    try
        req = jsondecode(fileread([prefix '.request.json']));
        p = load([prefix '.mat']);
        remaining = min(req.remaining_s, guardSeconds-toc(workerClock));
        opts = optimoptions('intlinprog','Display','off', ...
            'AbsoluteGapTolerance',0,'RelativeGapTolerance',0, ...
            'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6, ...
            'IntegerPreprocess','none', ...
            'OutputFcn',@callback);
        opts.MaxTime = max(0,remaining-toc(requestClock));
        result.options_text = evalc('disp(opts)');
        % All documented public option values, including defaults, are kept.
        names = properties(opts); optionValues = struct();
        for k=1:numel(names)
            value=opts.(names{k});
            if isa(value,'function_handle'), value=func2str(value); end
            optionValues.(names{k})=value;
        end
        result.options = optionValues;
        if opts.MaxTime<=0 || isfile([prefix '.cancel'])
            result.status='BUDGET_EXHAUSTED_BEFORE_SOLVER';
        else
            [x,fval,exitflag,output] = intlinprog(p.c(:),p.intcon(:)', ...
                p.A,p.b(:),p.Aeq,p.beq(:),p.lb(:),p.ub(:),[],opts);
            result.x=x(:)'; result.fval=fval; result.exitflag=exitflag;
            result.output=output; result.status='SOLVED';
            if ~isempty(callbackError)
                result.status='CALLBACK_ERROR'; result.callback_error=callbackError;
            end
            % MAT retains NaN/Inf and all native solver fields independently
            % of JSON's null representation.  This is raw solver evidence.
            save([prefix '.native.mat'],'x','fval','exitflag','output','opts','callbacks');
        end
    catch err
        result.error_identifier=err.identifier;
        result.error_message=getReport(err,'extended','hyperlinks','off');
    end
    result.callbacks=callbacks; result.callback_fields=callbackFields;
    result.matlab_request_wall_seconds=toc(requestClock);
    result.worker_elapsed_seconds=toc(workerClock);
    result.solver_information_is_independently_certified=false;
    writejson([prefix '.response.json'],result);
    requestNumber=requestNumber+1;
end

    function stop = callback(x,values,state)
        stop = false;
        try
            callbackFields=union(callbackFields,fieldnames(values));
            entry=struct('state',state,'request_wall_seconds',toc(requestClock), ...
                'values',values,'x',x(:)');
            callbacks{end+1}=entry; %#ok<AGROW>
            stop = toc(requestClock)>=remaining || toc(workerClock)>=guardSeconds ...
                || isfile([prefix '.cancel']) || isfile(fullfile(folder,'stop'));
        catch err
            callbackError=getReport(err,'extended','hyperlinks','off');
            stop=true;
        end
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
