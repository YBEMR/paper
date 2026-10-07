function folder=run_h37()
here=fileparts(mfilename('fullpath'));
folder=fullfile(here,'h37_reports',['run_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
assert(~isfolder(folder)); mkdir(folder); diary(fullfile(folder,'console.txt'));
cleanup=onCleanup(@()diary('off')); %#ok<NASGU>
fprintf('START %s\nMATLAB %s\n',char(datetime('now')),version);
trials=thv_cases();
historical=fullfile(here,'thermal_reports','run_20260923_204922_828');
frozen=load(fullfile(historical,'inputs.mat'),'trials');
assert(isequaln(trials,frozen.trials),'Inputs differ from run 36');
environment=struct('matlab',version,'date',char(datetime('now')), ...
    'rules','H37_README.md v1','historical_inputs',historical, ...
    'oracle_isolation','Only configuration adapter uses no-heat solver; history read after policy execution', ...
    'units','s,W,J,C','budget','60 s per trial per version including configuration and ties');
save(fullfile(folder,'inputs.mat'),'trials','environment');
writejson(fullfile(folder,'inputs.json'),struct('trials',trials,'environment',environment));
mkdir(fullfile(folder,'source')); files=dir(fullfile(here,'*.m'));
for k=1:numel(files), copyfile(fullfile(here,files(k).name),fullfile(folder,'source')); end
copyfile(fullfile(here,'H37_README.md'),fullfile(folder,'source'));
fprintf('FROZEN %s\n',folder);
runs=struct('trial',{},'version',{},'status',{},'message',{},'configs',{},'outputs',{},'elapsed_s',{});
for k=1:numel(trials)
    for v={'P0','P1'}
        clock=tic; configs=[]; outputs={}; status='completed'; message='';
        try
            configs=h37_config(trials(k).case,clock);
            if isempty(configs), status='no_noheat_configuration'; end
            for j=1:numel(configs)
                outputs{j}=h37_policy(trials(k).case,trials(k).thermal,configs(j),v{1},clock);
            end
        catch err
            status='error'; message=getReport(err,'extended','hyperlinks','off');
            if strcmp(err.identifier,'cv:timeout'), status='timeout'; end
            fprintf('%s\n',message);
        end
        runs(end+1)=struct('trial',k,'version',v{1},'status',status,'message',message, ...
            'configs',configs,'outputs',{outputs},'elapsed_s',toc(clock));
        fprintf('%s %s execution=%s configs=%d elapsed=%.6f\n',trials(k).id,v{1},status,numel(configs),toc(clock));
        save(fullfile(folder,'results.mat'),'trials','environment','runs');
    end
end
% Diagnostic configuration: existing HH, not selected by the main planner.
diagnostics=struct('trial',{},'version',{},'output',{});
for k=1:numel(trials)
    if startsWith(trials(k).case.id,'R1_') && strcmp(trials(k).role,'coupling_control')
        c=trials(k).case; [d,Q]=cv_response(c,'task');
        config=struct('modes',[2 2],'duration',[d(:,2)' c.n],'increment',[Q(:,2)' c.w]);
        for v={'P0','P1'}
            o=h37_policy(c,trials(k).thermal,config,v{1},tic);
            diagnostics(end+1)=struct('trial',k,'version',v{1},'output',o);
        end
    end
end
fprintf('ALL POLICY EXECUTIONS FINISHED; opening historical evaluation results now\n');
old=load(fullfile(historical,'results.mat'),'results');
save(fullfile(folder,'results.mat'),'trials','environment','runs','diagnostics');
h37_export(folder,trials,runs,diagnostics,old.results);
try
    checks=h37_tests(here,trials,runs,diagnostics,old.results);
catch err
    fprintf('CHECK EXECUTION ERROR\n%s\n',getReport(err,'extended','hyperlinks','off'));
    rethrow(err);
end
writetable(checks,fullfile(folder,'checks.csv'));
save(fullfile(folder,'results.mat'),'trials','environment','runs','diagnostics','checks');
fprintf('CHECKS %d/%d passed\n',sum(checks.passed),height(checks));
assert(all(checks.passed),'H37 implementation checks failed; keep this run for audit');
disp(readtable(fullfile(folder,'summary.csv'),'TextType','string'));
fprintf('COMPLETE %s\nOUTPUT %s\n',char(datetime('now')),folder);
end
function writejson(path,value)
fid=fopen(path,'w'); assert(fid>=0); cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');
end
