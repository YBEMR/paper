function run_lp_probe(folder, originalFolder, absoluteUnixDeadline)
% One isolated numerical diagnostic. Original model/x0 are never changed.
started = tic; eventNumber = 0; callbacks = {};
result = struct('status','NOT_STARTED','solver_calls',0, ...
    'formal_experiment',false,'thermal_evaluation_performed',false, ...
    'safe_upper_bound_claim',false,'independent_optimality_claim',false);
try
    info=struct('version',version,'release',version('-release'), ...
        'intlinprog_path',which('intlinprog'), ...
        'license_test',license('test','Optimization_Toolbox'));
    [ok,message]=license('checkout','Optimization_Toolbox');
    info.license_checkout=logical(ok); info.license_message=message;
    writejson(fullfile(folder,'environment.json'),info);
    if ~ok || ~strcmp(info.release,'2023b')
        error('audit:Prerequisite','R2023b license prerequisite failed');
    end
    p=load(fullfile(originalFolder,'request_000001.mat'));
    native=load(fullfile(originalFolder,'request_000001.native.mat'),'opts');
    originalOptions=native.opts;
    result.original_LPPreprocess=originalOptions.LPPreprocess;
    if ~strcmp(originalOptions.LPPreprocess,'basic')
        error('audit:Prerequisite','Original LPPreprocess is not basic; no solve');
    end
    required={'c','intcon','A','b','Aeq','beq','lb','ub','x0'};
    for k=1:numel(required)
        if ~isfield(p,required{k}), error('audit:Prerequisite','Missing field'); end
    end
    result.initial_point_residual=residual(p,p.x0(:));
    if result.initial_point_residual.max_row>1e-9 || ...
            result.initial_point_residual.max_bound>1e-9 || ...
            result.initial_point_residual.max_integer>1e-6
        error('audit:Prerequisite','Original x0 numerical check failed; no solve');
    end
    originalOptionsPublic=optionvalues(originalOptions);
    writejson(fullfile(folder,'original_options.json'),originalOptionsPublic);
    opts=originalOptions;
    opts.LPPreprocess='none';
    opts.Display='iter';
    opts.OutputFcn=@observer;
    remaining=absoluteUnixDeadline-nowunix()-5;
    opts.MaxTime=min(258.57254819995904,remaining);
    if opts.MaxTime<=0, error('audit:Deadline','No solver budget'); end
    requestedOptions=optionvalues(opts);
    writejson(fullfile(folder,'requested_options.json'),requestedOptions);
    result.status='ENTERING_SOLVER'; result.solver_calls=1;
    result.elapsed_before_solver_seconds=toc(started);
    result.solver_max_time_seconds=opts.MaxTime;
    writejson(fullfile(folder,'solver_entered.json'),result);
    solveClock=tic; lastwarn('');
    [x,fval,exitflag,output]=intlinprog(p.c(:),p.intcon(:)', ...
        p.A,p.b(:),p.Aeq,p.beq(:),p.lb(:),p.ub(:),p.x0(:),opts);
    result.solver_seconds=toc(solveClock);
    [warningMessage,warningIdentifier]=lastwarn;
    result.status='RETURNED'; result.exitflag=exitflag;
    result.fval=fval; result.output=output;
    result.warning_message=warningMessage;
    result.warning_identifier=warningIdentifier;
    result.returned_x_length=numel(x);
    if ~isempty(x), result.returned_x_residual=residual(p,x(:)); end
    result.returned_before_outer_deadline=nowunix()<=absoluteUnixDeadline;
    result.elapsed_before_archive_seconds=toc(started);
    save(fullfile(folder,'diagnostic.native.mat'),'x','fval','exitflag', ...
        'output','originalOptionsPublic','requestedOptions','callbacks','-v7');
catch err
    result.status='ERROR'; result.error_identifier=err.identifier;
    result.error_message=getReport(err,'extended','hyperlinks','off');
end
result.matlab_elapsed_seconds=toc(started);
result.archived_before_outer_deadline=nowunix()<=absoluteUnixDeadline;
writejson(fullfile(folder,'result.json'),result);

    function stop=observer(x,values,state)
        eventNumber=eventNumber+1;
        entry=struct('event',eventNumber,'state',state,'values',values, ...
            'x_length',numel(x),'matlab_elapsed_seconds',toc(started), ...
            'unix_time',nowunix());
        callbacks{end+1}=entry; %#ok<AGROW>
        writejson(fullfile(folder,sprintf('callback_%04d.json',eventNumber)),entry);
        stop=nowunix()>=absoluteUnixDeadline-5;
    end
end

function value=optionvalues(opts)
names=properties(opts); names=union(names,{'LPPreprocess'}); value=struct();
for k=1:numel(names)
    item=opts.(names{k});
    if isa(item,'function_handle'), item=func2str(item); end
    value.(names{k})=item;
end
end

function value=residual(p,x)
v=p.A*x-p.b(:); e=p.Aeq*x-p.beq(:);
value=struct('max_inequality',max([0;v]), ...
    'max_equality',max([0;abs(e)]), ...
    'max_row',max([0;v;abs(e)]), ...
    'max_bound',max([0;p.lb(:)-x;x-p.ub(:)]), ...
    'max_integer',max([0;abs(x(p.intcon)-round(x(p.intcon)))]), ...
    'objective',p.c(:)'*x,'length',numel(x));
end

function value=nowunix()
value=posixtime(datetime('now','TimeZone','UTC'));
end

function writejson(path,value)
fid=fopen([path '.tmp'],'w','n','UTF-8');
if fid<0,error('audit:Archive','Cannot open diagnostic output');end
cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(value)); clear cleanup;
movefile([path '.tmp'],path,'f');
end
