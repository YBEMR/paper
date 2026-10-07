function folder=run_thermal76(mode,receipt)
% Independent OFFLINE row-coverage diagnostic, never an MILP solver run.
if nargin<1,mode='precheck';end
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));design=fullfile(root,'research','stage53_design');
plan=fullfile(root,'research','thermal76_design');
folder=fullfile(here,'thermal76_reports',[mode '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);mkdir(folder);
diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
list=dir(fullfile(here,'*.m'));paths=cellfun(@(n)fullfile(here,n),{list.name},'UniformOutput',false);
paths=[paths {fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json'),fullfile(plan,'rules_v1.json')}];hash=c44_audit(paths);
mkdir(fullfile(folder,'source'));for i=1:numel(paths),[~,n,e]=fileparts(paths{i});copyfile(paths{i},fullfile(folder,'source',sprintf('%03d_%s%s',i,n,e)));end
environment=struct('matlab',version,'prefdir',prefdir,'started',char(datetime('now')),'budget_s',60, ...
 'scope','offline all-arrangement cut coverage; no MILP optimization');
writejson(fullfile(folder,'source_hashes.json'),hash);writejson(fullfile(folder,'environment.json'),environment);
try
 fprintf('START %s %s\n',mode,folder);
 if strcmp(mode,'precheck')
  [trials,~]=s55_load(design);checks=t76_tests(trials);pass=all(checks.passed);
  writetable(checks,fullfile(folder,'prechecks.csv'));save(fullfile(folder,'receipt.mat'),'pass','checks','hash');
  disp(checks);assert(pass,'t76:precheck','Precheck failed');
 elseif strcmp(mode,'frozen')
  assert(nargin>1 && isfile(receipt));prior=load(receipt);assert(prior.pass && isequal(prior.hash,hash),'t76:receipt','Passed matching receipt required');
  copyfile(receipt,fullfile(folder,'receipt.mat'));rules=jsondecode(fileread(fullfile(plan,'rules_v1.json')));
  results=cell(2,1);ids={'P_high_D6_cold','P_high_D6_hot'};
  for k=1:2
   fprintf('BEGIN %s\n',ids{k});r=t76_diagnose(design,ids{k});results{k}=r;
   save(fullfile(folder,[ids{k} '.mat']),'r','-v7.3');save(fullfile(folder,'results.mat'),'results','rules','environment','hash','-v7.3');
   fprintf('RESULT %s %s rows=%d cuts=%d elapsed=%.3f\n',r.id,r.status,r.checked_rows,r.checked_cuts,r.elapsed_s);
   if strcmp(r.status,'error'),error('t76:implementation','%s',r.error);end
  end
  t76_export(folder,results);
 else,error('Unknown mode');end
 assert(isequal(hash,c44_audit(paths)),'t76:hash','Sources/input changed during execution');
 writejson(fullfile(folder,'audit.json'),struct('complete',true,'source_input_unchanged',true));fprintf('OUTPUT %s\nCOMPLETE\n',folder);
catch err
 msg=getReport(err,'extended','hyperlinks','off');fprintf('%s\n',msg);fid=fopen(fullfile(folder,'failure.txt'),'w','n','UTF-8');fprintf(fid,'%s',msg);fclose(fid);rethrow(err);
end
end
function writejson(path,v)
fid=fopen(path,'w','n','UTF-8');g=onCleanup(@()fclose(fid));fprintf(fid,'%s',jsonencode(v,'PrettyPrint',true)); %#ok<NASGU>
end
