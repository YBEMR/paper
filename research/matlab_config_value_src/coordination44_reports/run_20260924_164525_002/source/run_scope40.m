function folder=run_scope40()
here=fileparts(mfilename('fullpath'));
folder=fullfile(here,'scope40_reports',['run_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
mkdir(folder); diary(fullfile(folder,'console.txt')); cleanup=onCleanup(@()diary('off')); %#ok<NASGU>
fprintf('START %s MATLAB %s\n',char(datetime('now')),version);
trials=s40_cases(); legacy=thv_cases();
historical=fullfile(here,'thermal_reports','run_20260923_204922_828');
frozen=load(fullfile(historical,'inputs.mat'),'trials'); assert(isequaln(legacy,frozen.trials));
environment=struct('matlab',version,'started',char(datetime('now')), ...
    'rules','SCOPE40_README.md v1','reference_budget_s',60,'policy_version_budget_s',60, ...
    'scope','60 synthetic conditions; 15 legacy regression cases separately', ...
    'information','All policy runs precede reference classification; no reference timings supplied');
save(fullfile(folder,'inputs.mat'),'trials','legacy','environment');
writejson('inputs.json',struct('trials',trials,'legacy',legacy,'environment',environment));
mkdir(fullfile(folder,'source')); files=dir(fullfile(here,'*.m'));
for k=1:numel(files), copyfile(fullfile(here,files(k).name),fullfile(folder,'source')); end
copyfile(fullfile(here,'SCOPE40_README.md'),fullfile(folder,'source'));
writejson('freeze_manifest.json',s40_manifest(folder));
checks=s40_tests(trials); writetable(checks,fullfile(folder,'preflight_checks.csv'));
fprintf('PREFLIGHT %d/%d\n',sum(checks.passed),height(checks));
runs=cell(numel(trials),2); regress_runs=cell(numel(legacy),2);
references=cell(1,numel(trials)); regress_refs=cell(1,numel(legacy));
for section=1:2
    if section==1, items=trials; else, items=legacy; end
    for k=1:numel(items)
        for v=1:2
            timer=tic; configs=[]; outputs={}; status='complete'; message='';
            try
                configs=s40_config(items(k).case,items(k).thermal,timer);
                if isempty(configs), status='no_noheat_configuration'; end
                versions={'P0','P1'};
                for j=1:numel(configs)
                    outputs{j}=h37_policy(items(k).case,items(k).thermal,configs(j),versions{v},timer);
                    if strcmp(outputs{j}.status,'timeout'), status='timeout'; break; end
                end
            catch err
                status='error'; message=getReport(err,'extended','hyperlinks','off');
                if contains(err.identifier,'timeout'), status='timeout'; end
                fprintf('%s\n',message);
            end
            rr=struct('configs',configs,'outputs',{outputs},'status',status,'message',message,'elapsed_s',toc(timer));
            if section==1, runs{k,v}=rr; else, regress_runs{k,v}=rr; end
        end
        fprintf('POLICY scope=%d %d/%d %s\n',section,k,numel(items),items(k).id);
    end
end
save(fullfile(folder,'results.mat'),'trials','legacy','environment','runs','regress_runs','references','regress_refs');
fprintf('ALL POLICIES FINISHED; reference classification starts\n');
for section=1:2
    if section==1, items=trials; else, items=legacy; end
    for k=1:numel(items)
        rr=s40_classify(items(k));
        if section==1, references{k}=rr; else, regress_refs{k}=rr; end
        fprintf('REFERENCE scope=%d %d/%d %s class=%s %.4fs eval=%d\n',section,k,numel(items),items(k).id,rr.decision.class,rr.elapsed_s,sum([rr.modes.evaluated]));
        save(fullfile(folder,'results.mat'),'trials','legacy','environment','runs','regress_runs','references','regress_refs');
    end
end
s40_export(folder,trials,references,runs,'main');
s40_export(folder,legacy,regress_refs,regress_runs,'regression');
post=s40_postchecks(trials,references,runs,legacy,regress_refs,regress_runs,here);
writetable(post,fullfile(folder,'post_checks.csv'));
save(fullfile(folder,'results.mat'),'trials','legacy','environment','runs','regress_runs','references','regress_refs','checks','post');
fprintf('POSTCHECKS %d/%d\n',sum(post.passed),height(post)); assert(all(post.passed),'Post checks failed');
s40_plots(folder); writejson('manifest.json',s40_manifest(folder));
fprintf('COMPLETE %s\nOUTPUT %s\n',char(datetime('now')),folder);
    function writejson(name,value)
        fid=fopen(fullfile(folder,name),'w'); assert(fid>=0); guard=onCleanup(@()fclose(fid)); %#ok<NASGU>
        fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');
    end
end
