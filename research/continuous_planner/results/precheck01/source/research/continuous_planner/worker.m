function worker(folder)
% Isolated intlinprog service. No evaluator, reference answer or candidate cache.
info = struct('version', version, 'release', version('-release'), ...
    'license', license('test','Optimization_Toolbox'), 'solver', which('intlinprog'));
writejson(fullfile(folder,'ready.json'),info);
index=1;
while ~isfile(fullfile(folder,'stop'))
    input=fullfile(folder,sprintf('request_%04d.json',index));
    if ~isfile(input), pause(0.01); continue; end
    try
        p=jsondecode(fileread(input));
        A=spconvertrows(p.A,p.rows,p.n); Ae=spconvertrows(p.Aeq,p.eqrows,p.n);
        opts=optimoptions('intlinprog','Display','off','MaxTime',p.seconds, ...
            'AbsoluteGapTolerance',0,'RelativeGapTolerance',0, ...
            'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6);
        started=tic;
        [x,f,flag,out]=intlinprog(p.f(:),p.integer(:),A,p.b(:),Ae,p.beq(:),p.lb(:),p.ub(:),opts);
        r=struct('x',x,'fval',f,'exitflag',flag,'output',out, ...
            'solve_s',toc(started),'options',struct(opts),'state','returned');
    catch err
        r=struct('state','error','identifier',err.identifier,'message',err.message);
    end
    writejson(fullfile(folder,sprintf('response_%04d.json',index)),r);
    index=index+1;
end
end
function A=spconvertrows(t,m,n)
if isempty(t), A=sparse(m,n); else, A=sparse(t(:,1),t(:,2),t(:,3),m,n); end
end
function writejson(path,x)
tmp=[path '.tmp']; fid=fopen(tmp,'w'); cleanup=onCleanup(@() fclose(fid));
fprintf(fid,'%s',jsonencode(x)); clear cleanup; movefile(tmp,path);
end
