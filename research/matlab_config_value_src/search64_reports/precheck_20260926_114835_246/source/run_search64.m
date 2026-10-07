function folder=run_search64(mode,receipt)
% Precheck-gated frozen comparison, with independent 60s method budgets.
if nargin<1,mode='precheck';end
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));design=fullfile(root,'research','stage53_design');
folder=fullfile(here,'search64_reports',[mode '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);mkdir(folder);
diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
files=dir(fullfile(here,'*.m'));paths=cellfun(@(p)fullfile(here,p),{files.name},'UniformOutput',false);
paths=[paths {fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json')}];hash=c44_audit(paths);
mkdir(fullfile(folder,'source'));for i=1:numel(paths),[~,n,e]=fileparts(paths{i});copyfile(paths{i},fullfile(folder,'source',[n e]));end
writejson(fullfile(folder,'source_hashes.json'),hash);
[trials,rules]=s55_load(design);
environment=struct('matlab',version,'prefdir',prefdir,'started',char(datetime('now')), ...
 'budget_s',60,'time_lattice_s',.00025,'energy_lattice_J',.0000625,'temperature_enclosure','outward common/difference Taylor24');
save(fullfile(folder,'inputs.mat'),'trials','rules','environment');writejson(fullfile(folder,'environment.json'),environment);
fprintf('START %s %s\n',mode,folder);
try
 if strcmp(mode,'precheck')
  checks=b64_tests(trials);writetable(checks,fullfile(folder,'prechecks.csv'));pass=all(checks.passed);
  save(fullfile(folder,'receipt.mat'),'pass','checks','hash');disp(checks(~checks.passed,:));
  fprintf('PRECHECK %d/%d\n',sum(checks.passed),height(checks));assert(pass,'b64:precheck','Precheck failed');
 elseif strcmp(mode,'frozen')
  assert(nargin>1 && isfile(receipt),'Explicit precheck receipt required');p=load(receipt);
  assert(p.pass && isequal(p.hash,hash),'b64:receipt','Source/input hashes must match passed precheck');
  copyfile(receipt,fullfile(folder,'precheck_receipt.mat'));checks=p.checks;
  methods={'full','no_repair','simple_order','bare','joint_noheat','full_suffix','thermal_reference'};
  results=cell(10,7);save(fullfile(folder,'results.mat'),'results','trials','methods','rules','environment','checks','-v7.3');
  for pass=1:2
   for i=1:10
    if pass==1,js=1:6;else,js=7;end
    for j=js
     fprintf('BEGIN %d/10 %s %s\n',i,trials(i).id,methods{j});
     clock=tic;[fresh,~]=s55_load(design);overhead=toc(clock);fresh(i).case.budget_s=60-overhead;
     if j<=4,r=b64_search(fresh(i),methods{j});else,r=s55_method(fresh(i),methods{j});end
     r.input_setup_s=overhead;r.elapsed_s=r.elapsed_s+overhead;
     results{i,j}=r;
     save(fullfile(folder,sprintf('case%02d_method%02d.mat',i,j)),'r','-v7.3');
     save(fullfile(folder,'results.mat'),'results','trials','methods','rules','environment','checks','-v7.3');
     fprintf('RESULT %s %s %s E=[%.9g %.9g] J t=%.3fs\n',trials(i).id,methods{j},r.status,r.lower_J,r.upper_J,r.elapsed_s);
     assert(~strcmp(r.status,'error'),'b64:implementation','Implementation failure: preserve logs and stop');
    end
   end
  end
  b64_export(folder);
 else,error('Use precheck or frozen');end
 assert(isequal(hash,c44_audit(paths)),'Source/input changed during run');
 writejson(fullfile(folder,'audit.json'),struct('source_input_unchanged',true,'complete',true));
 fprintf('OUTPUT %s\nCOMPLETE\n',folder);
catch err
 msg=getReport(err,'extended','hyperlinks','off');fprintf('%s\n',msg);
 fid=fopen(fullfile(folder,'failure.txt'),'w','n','UTF-8');fprintf(fid,'%s',msg);fclose(fid);rethrow(err);
end
end
function writejson(p,v)
fid=fopen(p,'w','n','UTF-8');g=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',jsonencode(v,'PrettyPrint',true));
end
