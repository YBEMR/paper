function ac_native_repro
out=getenv('AC_REPRO_OUT');
p=load(getenv('AC_REPRO_MAT'),'c','A','b','Aeq','beq','lb','ub','intcon','x0');
assert(strcmp(version('-release'),'2023b'));
assert(numel(p.c)==14014 && size(p.A,1)==80272 && size(p.Aeq,1)==4994);
events={};wall=tic;
opts=optimoptions('intlinprog','Display','iter','AbsoluteGapTolerance',0, ...
 'RelativeGapTolerance',0,'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6, ...
 'IntegerPreprocess','none','LPPreprocess','none','RootLPAlgorithm','dual-simplex', ...
 'MaxTime',300,'OutputFcn',@observe);
assert(isinf(opts.MaxFeasiblePoints));
names=[properties(opts);{'LPPreprocess'}];values=struct();
for k=1:numel(names)
 v=opts.(names{k});if isa(v,'function_handle'),v=func2str(v);end
 values.(names{k})=v;
end
write_json('startup',struct('version',version,'release',version('-release'), ...
 'optimization_toolbox',ver('optim'),'intlinprog_which',which('intlinprog'), ...
 'options',values,'MaxFeasiblePoints_is_Inf',isinf(opts.MaxFeasiblePoints), ...
 'scope','single direct same-array reproduction, not a formal optimization experiment'));
if isfile(fullfile(out,'stop')),return;end
write_json('call_started',struct('MaxTime',300,'x0_argument',9,'options_argument',10));
lastwarn('');clock=tic;
try
 [x,fval,exitflag,output]=intlinprog(p.c(:),p.intcon(:)',p.A,p.b(:),p.Aeq,p.beq(:),p.lb(:),p.ub(:),p.x0(:),opts);
catch err
 write_json('error',struct('identifier',err.identifier,'message',err.message,'elapsed_s',toc(clock)));
 rethrow(err);
end
elapsed=toc(clock);[wm,wi]=lastwarn;
r=struct('elapsed_s',elapsed,'exitflag',exitflag,'fval',fval,'output',output, ...
 'x_length',numel(x),'MaxTime',300,'options',values,'MaxFeasiblePoints_is_Inf',isinf(opts.MaxFeasiblePoints), ...
 'events',{events},'warning_identifier',wi,'warning_message',wm, ...
 'matches_x0',isequal(x(:),p.x0(:)),'independently_proven_optimal',false);
if ~isempty(x)
 r.input_matrix_residual=struct('inequality',max([0;p.A*x-p.b(:)]), ...
  'equality',max([0;abs(p.Aeq*x-p.beq(:))]),'lower',max([0;p.lb(:)-x]), ...
  'upper',max([0;x-p.ub(:)]),'integer',max([0;abs(x(p.intcon(:))-round(x(p.intcon(:))))]));
end
initialPoint=p.x0;
save(fullfile(out,'native_result.mat'),'x','fval','exitflag','output','opts','r','events','initialPoint');
write_json('native_result',r);
 function stop=observe(v,info,state)
  stop=isfile(fullfile(out,'stop')) || toc(wall)>=400;
  events{end+1}=struct('state',state,'values',info,'x',v,'actual_stop',logical(stop),'wall_s',toc(wall));
 end
 function write_json(name,value)
  target=fullfile(out,[name '.json']);assert(~isfile(target));
  fid=fopen(target,'w','n','UTF-8');assert(fid>0);c=onCleanup(@()fclose(fid));
  fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));
 end
end
