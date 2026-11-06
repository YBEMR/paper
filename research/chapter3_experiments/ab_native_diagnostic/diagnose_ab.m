function diagnose_ab
% Isolated single-AB diagnostic. LP solutions are never solver SAFE receipts.
out = getenv('AB_DIAG_OUT');
phase = getenv('AB_DIAG_PHASE');
assert(strcmp(version('-release'),'2023b'), 'MATLAB R2023b required');
p = load(getenv('AB_DIAG_MAT'),'c','A','b','Aeq','beq','lb','ub','intcon','x0');
n = numel(p.c);
I = p.intcon(:);
assert(n == 8738 && size(p.A,1) + size(p.Aeq,1) == 40078);
assert(numel(unique(I)) == numel(I) && ~isempty(I) && all(I >= 1 & I <= n & I == fix(I)));
assert(all(isfinite(p.x0)) && all(p.x0(I) == round(p.x0(I))));
initial = residual(p,p.x0);
assert(max([initial.inequality initial.equality initial.lower initial.upper]) <= 1e-9);
write_json(out,'startup',struct('version',version,'release',version('-release'), ...
    'optimization_toolbox',ver('optim'),'initial',initial,'integer_count',numel(I)));
cap = 29.45299999997951;
events = {};
if strcmp(phase,'lp')
    opts = optimoptions('linprog','Algorithm','dual-simplex','Preprocess','none', ...
        'ConstraintTolerance',1e-9,'OptimalityTolerance',1e-7,'MaxTime',cap, ...
        'MaxIterations',max(30000,10*(size(p.A,1)+size(p.Aeq,1)+n)), 'Display','final');
    lb = p.lb; ub = p.ub;
    lb(I) = p.x0(I); ub(I) = p.x0(I);
    lp('fixed_integer_lp',lb,ub);
    lp('free_lp_relaxation',p.lb,p.ub);
elseif strcmp(phase,'milp')
    opts = integer_options(cap);
    solve_mip('x0_callback',p,p.x0,@observe,opts);
    solve_mip('x0_no_callback',p,p.x0,[],opts);
    solve_mip('no_x0_callback',p,[],@observe,opts);
elseif strcmp(phase,'repair')
    q = load(getenv('AB_DIAG_REPAIR_MAT'),'c','A','b','Aeq','beq','lb','ub','intcon','x0');
    assert(isequal(p.c,q.c) && isequal(p.lb,q.lb) && isequal(p.ub,q.ub) ...
        && isequal(p.intcon,q.intcon) && isequal(p.x0,q.x0));
    solve_mip('exact_equality_repair',q,p.x0,@observe,integer_options(cap));
else
    error('ABDiagnostic:Phase','Unknown phase');
end

    function lp(name,lb,ub)
        write_json(out,[name '_started'],struct('max_time_s',cap));
        lastwarn('');
        clock = tic;
        try
            [x,fval,flag,output] = linprog(p.c,p.A,p.b,p.Aeq,p.beq,lb,ub,opts);
        catch err
            write_error(out,name,err,toc(clock));
            rethrow(err);
        end
        elapsed = toc(clock);
        [warningMessage,warningIdentifier] = lastwarn;
        r = summarize(x,fval,flag,output,elapsed,warningMessage,warningIdentifier);
        r.options = evalc('disp(opts)');
        if ~isempty(x) && strcmp(name,'fixed_integer_lp')
            r.fixed_value_error = max(abs(x(I)-p.x0(I)));
        end
        save(fullfile(out,[name '.mat']),'x','fval','flag','output','opts','r');
        write_json(out,name,r);
    end

    function solve_mip(name,q,seed,fcn,settings)
        settings.OutputFcn = fcn;
        events = {};
        write_json(out,[name '_started'],struct('max_time_s',settings.MaxTime, ...
            'x0_length',numel(seed),'outputfcn',~isempty(fcn)));
        lastwarn('');
        clock = tic;
        try
            [x,fval,flag,output] = intlinprog(q.c(:),q.intcon(:)', ...
                q.A,q.b(:),q.Aeq,q.beq(:),q.lb(:),q.ub(:),seed,settings);
        catch err
            write_error(out,name,err,toc(clock));
            rethrow(err);
        end
        elapsed = toc(clock);
        [warningMessage,warningIdentifier] = lastwarn;
        r = summarize(x,fval,flag,output,elapsed,warningMessage,warningIdentifier);
        r.events = events;
        r.max_time_s = settings.MaxTime;
        r.options = evalc('disp(settings)');
        r.lp_preprocess = settings.LPPreprocess;
        save(fullfile(out,[name '.mat']),'x','fval','flag','output','settings','r');
        write_json(out,name,r);
    end

    function stop = observe(x,values,state)
        % Pure observation, with no I/O or cancellation in the solver callback.
        stop = false;
        event = struct('state',state,'values',values,'vector_length',numel(x));
        if ~isempty(x)
            event.residual = residual(p,x);
            event.x = x;
        end
        events{end+1} = event;
    end

    function r = summarize(x,fval,flag,output,elapsed,message,identifier)
        r = struct('elapsed_s',elapsed,'exitflag',flag,'fval',fval,'output',output, ...
            'x_length',numel(x),'warning_identifier',identifier,'warning_message',message);
        if numel(x) == n && all(isfinite(x))
            r.original_residual = residual(p,x);
            r.max_abs_x_minus_x0 = max(abs(x(:)-p.x0(:)));
            r.matches_x0 = isequal(x(:),p.x0(:));
        end
    end
end

function o = integer_options(seconds)
o = optimoptions('intlinprog','Display','iter','MaxFeasiblePoints',1, ...
    'AbsoluteGapTolerance',0,'RelativeGapTolerance',0,'ConstraintTolerance',1e-9, ...
    'IntegerTolerance',1e-6,'IntegerPreprocess','none','LPPreprocess','none', ...
    'RootLPAlgorithm','dual-simplex','MaxTime',seconds);
end

function r = residual(p,x)
x = x(:);
xi = x(p.intcon(:));
r = struct('inequality',max([0; p.A*x-p.b(:)]), ...
    'equality',max([0; abs(p.Aeq*x-p.beq(:))]), ...
    'lower',max([0; p.lb(:)-x]),'upper',max([0; x-p.ub(:)]), ...
    'integrality',max([0; abs(xi-round(xi))]),'objective',p.c(:)'*x);
end

function write_error(out,name,err,seconds)
write_json(out,name,struct('status','ERROR','identifier',err.identifier, ...
    'message',err.message,'elapsed_s',seconds));
end

function write_json(out,name,value)
path = fullfile(out,[name '.json']);
assert(~isfile(path));
fid = fopen(path,'w','n','UTF-8');
assert(fid > 0);
close_file = onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));
end
