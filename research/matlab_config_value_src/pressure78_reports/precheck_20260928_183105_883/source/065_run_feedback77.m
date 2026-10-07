function folder=run_feedback77(mode,receipt)
if nargin<1,mode='precheck';end
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));design=fullfile(root,'research','stage53_design');
protocol=fullfile(root,'research','feedback77_design','rules_v1.json');
folder=fullfile(here,'feedback77_reports',[mode '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);mkdir(folder);
diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
files=dir(fullfile(here,'*.m'));paths=cellfun(@(n)fullfile(here,n),{files.name},'UniformOutput',false);
paths=[paths {fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json'),protocol}];hash=c44_audit(paths);
mkdir(fullfile(folder,'source'));
for k=1:numel(paths),[~,n,e]=fileparts(paths{k});copyfile(paths{k},fullfile(folder,'source',sprintf('%03d_%s%s',k,n,e)));end
[trials,rules]=s55_load(design);protocol_rules=jsondecode(fileread(protocol));
options=optimoptions('intlinprog','Display','off','AbsoluteGapTolerance',0,'RelativeGapTolerance',0,'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6);
environment=struct('matlab',version,'prefdir',prefdir,'optimization_license',license('test','Optimization_Toolbox'), ...
 'solver',which('intlinprog'),'options',evalc('disp(options)'),'started',char(datetime('now')), ...
 'budget_s',60,'order','53 case order; original b68 no_good then f77 thermal_row','threads','R2023b defaults');
save(fullfile(folder,'inputs_environment.mat'),'trials','rules','protocol_rules','environment','hash','options');
writejson(fullfile(folder,'source_hashes.json'),hash);writejson(fullfile(folder,'environment.json'),environment);
try
 fprintf('START %s %s\n',mode,folder);assert(environment.optimization_license==1,'f77:license','Optimization Toolbox unavailable');
 if strcmp(mode,'precheck')
  [checks,fixtures]=f77_tests(trials,folder);pass=all(checks.passed);
  writetable(checks,fullfile(folder,'prechecks.csv'));save(fullfile(folder,'fixture_results.mat'),'fixtures','-v7.3');
  save(fullfile(folder,'receipt.mat'),'pass','checks','hash');disp(checks(~checks.passed,:));
  fprintf('PRECHECK %d/%d\n',sum(checks.passed),height(checks));assert(pass,'f77:precheck','Precheck failed');
 elseif strcmp(mode,'frozen')
  assert(nargin>1 && isfile(receipt));prior=load(receipt);
  assert(prior.pass && isequal(prior.hash,hash),'f77:receipt','Matching passed precheck required');copyfile(receipt,fullfile(folder,'receipt.mat'));
  results=cell(10,2);methods={'no_good','thermal_row'};
  for i=1:10
   for j=1:2
    fprintf('BEGIN %02d %s %s\n',i,trials(i).id,methods{j});
    wall=tic;[fresh,~]=s55_load(design);setup=toc(wall);fresh(i).case.budget_s=60-setup;
    if j==1,r=b68_method(fresh(i));else,r=f77_method(fresh(i));assert(~r.test_hooks_used);end
    outer=toc(wall);r=f77_budget_audit(r,setup,outer,60);
    dd=b64_data(fresh(i).case);r.common_L0_J=(dd.base+sum(dd.minE))*dd.energy_unit;
    r.comparison_method=methods{j};results{i,j}=r;
    serializeTimer=tic;save(fullfile(folder,sprintf('case%02d_method%02d.mat',i,j)),'r','-v7.3');
    save(fullfile(folder,'results.mat'),'results','trials','methods','rules','protocol_rules','environment','hash','-v7.3');
    fprintf('RESULT %s %s U=%.9g L0=%.9g calls=%d cuts=%d t=%.4f serialize=%.4f\n', ...
     methods{j},r.status,r.upper_J,r.common_L0_J,r.stats.thermal_calls,r.stats.cuts,r.elapsed_s,toc(serializeTimer));
    assert(~strcmp(r.raw_method_status,'error'),'f77:implementation','%s',r.message);
   end
  end
  postTimer=tic;f77_export(folder);writejson(fullfile(folder,'postprocess_timing.json'),struct('elapsed_s',toc(postTimer),'counted_in_method_budget',false));
 else,error('Unknown mode');end
 assert(isequal(hash,c44_audit(paths)),'f77:hash','Sources/input/rules changed during execution');
 writejson(fullfile(folder,'audit.json'),struct('complete',true,'source_input_rule_unchanged',true));fprintf('OUTPUT %s\nCOMPLETE\n',folder);
catch err
 message=getReport(err,'extended','hyperlinks','off');fprintf('%s\n',message);
 fid=fopen(fullfile(folder,'failure.txt'),'w','n','UTF-8');fprintf(fid,'%s',message);fclose(fid);rethrow(err);
end
end
function writejson(path,v)
fid=fopen(path,'w','n','UTF-8');g=onCleanup(@()fclose(fid));fprintf(fid,'%s',jsonencode(v,'PrettyPrint',true)); %#ok<NASGU>
end
