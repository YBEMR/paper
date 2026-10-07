function folder=run_pressure78(mode,receipt)
if nargin<1,mode='precheck';end
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));
design=fullfile(root,'research','pressure78_design');source=fullfile(root,'research','stage53_design');
folder=fullfile(here,'pressure78_reports',[mode '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);mkdir(folder);
diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
files=dir(fullfile(here,'*.m'));paths=cellfun(@(n)fullfile(here,n),{files.name},'UniformOutput',false);
paths=[paths {fullfile(source,'inputs_v1.json'),fullfile(source,'rules_v1.json'), ...
 fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json'),fullfile(design,'freeze_manifest.json')}];
hash=c44_audit(paths);mkdir(fullfile(folder,'source'));
for k=1:numel(paths),[~,n,e]=fileparts(paths{k});copyfile(paths{k},fullfile(folder,'source',sprintf('%03d_%s%s',k,n,e)));end
[trials,rules,base]=p78_load(design);
options=optimoptions('intlinprog','Display','off','AbsoluteGapTolerance',0,'RelativeGapTolerance',0,'ConstraintTolerance',1e-9,'IntegerTolerance',1e-6);
environment=struct('matlab',version,'prefdir',prefdir,'optimization_license',license('test','Optimization_Toolbox'), ...
 'solver',which('intlinprog'),'options',evalc('disp(options)'),'started',char(datetime('now')), ...
 'budget_s',60,'calls',numel(rules.calls),'order','discovery then repeat1 no_good/thermal_row then repeat2 thermal_row/no_good');
save(fullfile(folder,'inputs_environment.mat'),'trials','rules','environment','hash','options');
writejson(fullfile(folder,'source_hashes.json'),hash);writejson(fullfile(folder,'environment.json'),environment);
try
 fprintf('START %s %s\n',mode,folder);assert(environment.optimization_license==1);
 if strcmp(mode,'precheck')
  [checks,fixtures,certificate]=p78_tests(trials,rules,base,folder);pass=all(checks.passed);
  writetable(checks,fullfile(folder,'prechecks.csv'));
  save(fullfile(folder,'fixture_results.mat'),'fixtures','certificate','-v7.3');
  writejson(fullfile(folder,'discovery_certificate.json'),certificate);
  save(fullfile(folder,'receipt.mat'),'pass','checks','hash');
  fprintf('PRECHECK %d/%d\n',sum(checks.passed),height(checks));disp(checks(~checks.passed,:));assert(pass,'p78:precheck','Precheck failed');
 elseif strcmp(mode,'frozen')
  assert(nargin>1 && isfile(receipt));prior=load(receipt);
  assert(prior.pass && isequal(prior.hash,hash),'p78:receipt','Matching passed precheck required');
  copyfile(receipt,fullfile(folder,'receipt.mat'));records=cell(0,1);
  for k=1:numel(rules.calls)
   call=rules.calls(k);i=call.trial_index;
   fprintf('BEGIN %02d/%d %s rep%d %s\n',k,numel(rules.calls),trials(i).id,call.repeat,call.method);
   wall=tic;[fresh,~,~]=p78_load(design);setup=toc(wall);fresh(i).case.budget_s=60-setup;
   if strcmp(call.method,'no_good'),r=b68_method(fresh(i));
   else,r=f77_method(fresh(i));assert(~r.test_hooks_used);end
   outer=toc(wall);r=f77_budget_audit(r,setup,outer,60);
   dd=b64_data(fresh(i).case);r.common_L0_J=(dd.base+sum(dd.minE))*dd.energy_unit;
   r.comparison_method=call.method;
   rec=struct('trial_index',i,'repeat',call.repeat,'method',call.method,'call_index',k,'result',r);
   records{end+1,1}=rec; %#ok<AGROW>
   serial=tic;save(fullfile(folder,sprintf('call_%02d.mat',k)),'rec','-v7.3');
   save(fullfile(folder,'results.mat'),'records','trials','rules','environment','hash','-v7.3');
   fprintf('RESULT %s %s U=%.9g L0=%.9g rounds=%d thermal=%d cuts=%d elapsed=%.4f serialize=%.4f\n', ...
    call.method,r.status,r.upper_J,r.common_L0_J,r.stats.rounds,r.stats.thermal_calls,r.stats.cuts,r.elapsed_s,toc(serial));
   assert(~strcmp(r.raw_method_status,'error'),'p78:implementation','%s',r.message);
  end
  post=tic;p78_export(folder);writejson(fullfile(folder,'postprocess_timing.json'),struct('elapsed_s',toc(post),'counted_in_method_budget',false));
 else,error('p78:mode','Unknown mode');end
 assert(isequal(hash,c44_audit(paths)),'p78:hash','Source/input/rules changed during execution');
 writejson(fullfile(folder,'audit.json'),struct('complete',true,'source_input_rule_unchanged',true));fprintf('OUTPUT %s\nCOMPLETE\n',folder);
catch err
 message=getReport(err,'extended','hyperlinks','off');fprintf('%s\n',message);
 fid=fopen(fullfile(folder,'failure.txt'),'w','n','UTF-8');fprintf(fid,'%s',message);fclose(fid);rethrow(err);
end
end
function writejson(path,v)
fid=fopen(path,'w','n','UTF-8');g=onCleanup(@()fclose(fid));fprintf(fid,'%s',jsonencode(v,'PrettyPrint',true)); %#ok<NASGU>
end
