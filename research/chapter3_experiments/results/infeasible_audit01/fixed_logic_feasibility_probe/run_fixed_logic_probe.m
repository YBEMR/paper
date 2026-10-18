function run_fixed_logic_probe(folder, originalFolder, absoluteUnixDeadline)
% One feasibility lift: fixed original logic, original physical continuous domain.
started=tic; eventNumber=0; callbacks={};
result=struct('status','NOT_STARTED','solver_calls',0,'formal_experiment',false, ...
    'thermal_evaluation_performed',false,'energy_optimization_performed',false, ...
    'independent_feasibility_certificate',false);
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
    opts=native.opts;
    if ~strcmp(opts.LPPreprocess,'basic') || ~strcmp(opts.IntegerPreprocess,'none')
        error('audit:Prerequisite','Unexpected original preprocessing options');
    end
    declared=jsondecode(fileread(fullfile(folder,'predeclaration.json')));
    logic=[(1:39740)';(47440:71736)'];
    physical=setdiff((1:numel(p.c))',logic);
    values=p.x0(logic);
    checks=struct('logic_count',numel(logic),'physical_count',numel(physical), ...
        'model_summary_logical_binary_variables',declared.model_summary_logical_binary_variables, ...
        'logic_count_matches_model_summary',numel(logic)==declared.model_summary_logical_binary_variables, ...
        'original_intcon_subset_of_logic',all(ismember(p.intcon(:),logic)), ...
        'logic_x0_exactly_binary',all(values==0 | values==1), ...
        'original_bounds_allow_logic_x0',all(p.lb(logic)<=values & values<=p.ub(logic)), ...
        'expected_total_variables',numel(p.c)==77347, ...
        'expected_physical_count',numel(physical)==13310);
    writejson(fullfile(folder,'prerequisite_checks.json'),checks);
    if ~(checks.logic_count_matches_model_summary && checks.original_intcon_subset_of_logic ...
            && checks.logic_x0_exactly_binary && checks.original_bounds_allow_logic_x0 ...
            && checks.expected_total_variables && checks.expected_physical_count)
        error('audit:Prerequisite','Logic partition checks failed; no solve');
    end
    lb=p.lb(:); ub=p.ub(:); lb(logic)=values; ub(logic)=values;
    c=zeros(size(p.c(:)));
    result.input_changes=struct('zero_based_logic_ranges',[0 39740;47439 71736], ...
        'logic_variables_fixed',numel(logic),'physical_variables_free',numel(physical), ...
        'changed_lower_bounds',nnz(lb~=p.lb(:)), ...
        'changed_upper_bounds',nnz(ub~=p.ub(:)), ...
        'physical_bounds_unchanged',isequal(lb(physical),p.lb(physical)) && isequal(ub(physical),p.ub(physical)), ...
        'objective_all_zero',all(c==0),'intcon_unchanged',true, ...
        'A_b_Aeq_beq_unchanged',true,'x0_unchanged',true);
    save(fullfile(folder,'logic_fixing.mat'),'logic','values','physical','-v7');
    result.initial_point_residual=residual(p,p.x0(:));
    originalOptionsPublic=optionvalues(opts);
    writejson(fullfile(folder,'original_options.json'),originalOptionsPublic);
    opts.Display='iter'; opts.OutputFcn=@observer;
    opts.MaxTime=min(60,absoluteUnixDeadline-nowunix()-5);
    if opts.MaxTime<=0, error('audit:Deadline','No solver budget'); end
    requestedOptions=optionvalues(opts);
    writejson(fullfile(folder,'requested_options.json'),requestedOptions);
    result.status='ENTERING_SOLVER';result.solver_calls=1;
    result.elapsed_before_solver_seconds=toc(started);
    result.solver_max_time_seconds=opts.MaxTime;
    writejson(fullfile(folder,'solver_entered.json'),result);
    solveClock=tic;lastwarn('');
    [x,fval,exitflag,output]=intlinprog(c,p.intcon(:)',p.A,p.b(:), ...
        p.Aeq,p.beq(:),lb,ub,p.x0(:),opts);
    result.solver_seconds=toc(solveClock);
    [warningMessage,warningIdentifier]=lastwarn;
    result.status='RETURNED';result.exitflag=exitflag;result.zero_objective_value=fval;
    result.output=output;result.warning_message=warningMessage;
    result.warning_identifier=warningIdentifier;result.returned_x_length=numel(x);
    if ~isempty(x)
        result.returned_x_residual_against_original=residual(p,x(:));
        result.logic_values_exactly_same=isequal(x(logic),values);
        result.logic_values_max_deviation=max(abs(x(logic)-values));
        result.returned_fixed_bound_residual=max([0;lb-x(:);x(:)-ub]);
    end
    result.returned_before_outer_deadline=nowunix()<=absoluteUnixDeadline;
    result.elapsed_before_archive_seconds=toc(started);
    save(fullfile(folder,'diagnostic.native.mat'),'x','fval','exitflag', ...
        'output','originalOptionsPublic','requestedOptions','callbacks','-v7');
catch err
    result.status='ERROR';result.error_identifier=err.identifier;
    result.error_message=getReport(err,'extended','hyperlinks','off');
end
result.matlab_elapsed_seconds=toc(started);
result.archived_before_outer_deadline=nowunix()<=absoluteUnixDeadline;
writejson(fullfile(folder,'result.json'),result);
    function stop=observer(x,values,state)
        eventNumber=eventNumber+1;
        entry=struct('event',eventNumber,'state',state,'values',values, ...
            'x_length',numel(x),'matlab_elapsed_seconds',toc(started),'unix_time',nowunix());
        callbacks{end+1}=entry; %#ok<AGROW>
        writejson(fullfile(folder,sprintf('callback_%04d.json',eventNumber)),entry);
        stop=nowunix()>=absoluteUnixDeadline-5;
    end
end

function value=optionvalues(opts)
names=properties(opts);names=union(names,{'LPPreprocess'});value=struct();
for k=1:numel(names)
    item=opts.(names{k});if isa(item,'function_handle'),item=func2str(item);end
    value.(names{k})=item;
end
end
function value=residual(p,x)
v=p.A*x-p.b(:);e=p.Aeq*x-p.beq(:);
value=struct('max_inequality',max([0;v]),'max_equality',max([0;abs(e)]), ...
    'max_row',max([0;v;abs(e)]),'max_bound',max([0;p.lb(:)-x;x-p.ub(:)]), ...
    'max_integer',max([0;abs(x(p.intcon)-round(x(p.intcon)))]),'length',numel(x));
end
function value=nowunix()
value=posixtime(datetime('now','TimeZone','UTC'));
end
function writejson(path,value)
fid=fopen([path '.tmp'],'w','n','UTF-8');
if fid<0,error('audit:Archive','Cannot open diagnostic output');end
cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(value));clear cleanup;
movefile([path '.tmp'],path,'f');
end
