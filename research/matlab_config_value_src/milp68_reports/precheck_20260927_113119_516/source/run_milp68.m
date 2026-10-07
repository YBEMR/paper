function folder=run_milp68(mode,receipt)
if nargin<1,mode='precheck';end
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));design=fullfile(root,'research','stage53_design');
folder=fullfile(here,'milp68_reports',[mode '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);mkdir(folder);
diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
paths=dir(fullfile(here,'*.m'));paths=cellfun(@(n)fullfile(here,n),{paths.name},'UniformOutput',false);
paths=[paths {fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json')}];hash=c44_audit(paths);
mkdir(fullfile(folder,'source'));for i=1:numel(paths),[~,n,e]=fileparts(paths{i});copyfile(paths{i},fullfile(folder,'source',[n e]));end
[trials,rules]=s55_load(design);options=optimoptions('intlinprog','Display','off','AbsoluteGapTolerance',0,'RelativeGapTolerance',0,'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6);
environment=struct('matlab',version,'prefdir',prefdir,'optimization_license',license('test','Optimization_Toolbox'),'solver',which('intlinprog'),'options',evalc('disp(options)'), ...
 'started',char(datetime('now')),'budget_s',60,'order','no_repair then milp_engineering per case','solver_threads','R2023b defaults; no override');
save(fullfile(folder,'inputs_environment.mat'),'trials','rules','environment','hash');writejson(fullfile(folder,'environment.json'),environment);writejson(fullfile(folder,'source_hashes.json'),hash);
fprintf('START %s %s\n',mode,folder);
try
 assert(environment.optimization_license==1,'b68:license','Optimization Toolbox unavailable');
 if strcmp(mode,'precheck')
  checks=b68_tests(trials);writetable(checks,fullfile(folder,'prechecks.csv'));pass=all(checks.passed);
  save(fullfile(folder,'receipt.mat'),'pass','checks','hash');disp(checks(~checks.passed,:));fprintf('PRECHECK %d/%d\n',sum(checks.passed),height(checks));assert(pass,'b68:precheck','Precheck failed');
 elseif strcmp(mode,'frozen')
  assert(nargin>1 && isfile(receipt),'Passed receipt required');p=load(receipt);assert(p.pass && isequal(p.hash,hash),'b68:receipt','Hashes must match');copyfile(receipt,fullfile(folder,'receipt.mat'));
  results=cell(10,2);methods={'no_repair','milp_engineering'};
  for i=1:10
   for j=1:2
    fprintf('BEGIN %d %s %s\n',i,trials(i).id,methods{j});clock=tic;[fresh,~]=s55_load(design);overhead=toc(clock);fresh(i).case.budget_s=60-overhead;
    if j==1,r=b64_search(fresh(i),'no_repair');else,r=b68_method(fresh(i));end
    r.input_setup_s=overhead;r.elapsed_s=r.elapsed_s+overhead;r.first_safe_s=r.first_safe_s+overhead;r.bound_trace(:,1)=r.bound_trace(:,1)+overhead;
    if isfield(r,'solver_trace'),r.solver_trace(:,1)=r.solver_trace(:,1)+overhead;end
    dd=b64_data(fresh(i).case);r.common_L0_J=(dd.base+sum(dd.minE))/16000;
    results{i,j}=r;save(fullfile(folder,sprintf('case%02d_method%02d.mat',i,j)),'r','-v7.3');save(fullfile(folder,'results.mat'),'results','trials','methods','rules','environment','-v7.3');
    fprintf('RESULT %s %s U=%.9g L=%.9g t=%.3f\n',methods{j},r.status,r.upper_J,r.lower_J,r.elapsed_s);
    assert(~strcmp(r.status,'error'),'b68:implementation','Preserve failure and stop');
   end
  end
  b68_export(folder);
 else,error('Unknown mode');end
 assert(isequal(hash,c44_audit(paths)),'Source/input changed');writejson(fullfile(folder,'audit.json'),struct('complete',true,'source_input_unchanged',true));fprintf('OUTPUT %s\nCOMPLETE\n',folder);
catch err
 msg=getReport(err,'extended','hyperlinks','off');fprintf('%s\n',msg);fid=fopen(fullfile(folder,'failure.txt'),'w','n','UTF-8');fprintf(fid,'%s',msg);fclose(fid);rethrow(err);
end
end
function writejson(path,v)
fid=fopen(path,'w','n','UTF-8');g=onCleanup(@()fclose(fid));fprintf(fid,'%s',jsonencode(v,'PrettyPrint',true)); %#ok<NASGU>
end
