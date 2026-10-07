function folder = run_config_value()
% Independent, nonthermal first-round verification. No Optimization Toolbox.
here=fileparts(mfilename('fullpath'));
folder=fullfile(here,'reports',['run_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
assert(~isfolder(folder),'Run folder already exists'); mkdir(folder);
diary(fullfile(folder,'console.txt')); cleanup=onCleanup(@()diary('off')); %#ok<NASGU>
fprintf('START %s\nMATLAB %s\n',char(datetime('now')),version);
cases=cv_cases();
environment=struct('matlab',version,'computer',computer,'started',char(datetime('now')), ...
    'thermal','not_evaluated','source','abstract inputs authorized in implementation plan', ...
    'units','s,W,J','mode_encoding','1=L,2=H', ...
    'N1_power_completion','Use R2_above power inputs; only B NPU duration changes', ...
    'test_fixture','replay unit fixture: R2_above_tight, modes LL, change alpha to [1 1]');
save(fullfile(folder,'inputs.mat'),'cases','environment');
fid=fopen(fullfile(folder,'inputs.json'),'w'); assert(fid>=0);
fwrite(fid,jsonencode(struct('environment',environment,'cases',cases),'PrettyPrint',true),'char'); fclose(fid);
mkdir(fullfile(folder,'source')); files=dir(fullfile(here,'*.m'));
for j=1:numel(files), copyfile(fullfile(here,files(j).name),fullfile(folder,'source')); end
if isfile(fullfile(here,'README.md')), copyfile(fullfile(here,'README.md'),fullfile(folder,'source')); end
fprintf('Inputs and source frozen before numerical evaluation: %s\n',folder);
results=cell(1,numel(cases));
for k=1:numel(cases)
    c=cases(k); clock=tic;
    try
        o=cv_compare(c,clock);
        if toc(clock)>c.budget_s, error('cv:timeout','Case budget exceeded'); end
    catch err
        o=struct('status','error','identifier',err.identifier,'message',err.message,'stack',err.stack);
        fprintf('%s\n',getReport(err,'extended','hyperlinks','off'));
    end
    o.elapsed_s=toc(clock); results{k}=o;
    fprintf('%s %s %.6f s\n',c.id,o.status,o.elapsed_s);
    save(fullfile(folder,'results.mat'),'cases','environment','results');
end
if ~all(cellfun(@(x)strcmp(x.status,'complete'),results))
    error('cv:caseFailed','Case failed; saved results include errors; do not infer infeasibility');
end
cv_export(folder,cases,results);
checks=cv_tests(cases,results);
summary_check=readtable(fullfile(folder,'summary.csv'),'TextType','string');
empty_row=summary_check.case_id=="TEST_impossible";
checks(end+1,:)={'export_empty_replay_is_not_feasible', ...
    all(isnan(summary_check.simple_replays_all_feasible(empty_row))), ...
    'No replay is reported as NaN, not vacuously feasible'};
writetable(checks,fullfile(folder,'checks.csv'));
save(fullfile(folder,'results.mat'),'cases','environment','results','checks');
fprintf('CHECKS %d/%d passed\n',sum(checks.passed),height(checks));
disp(readtable(fullfile(folder,'summary.csv'),'TextType','string'));
disp(readtable(fullfile(folder,'queue.csv'),'TextType','string'));
assert(all(checks.passed),'cv:checkFailed','Checks failed; see checks.csv');
fprintf('COMPLETE %s\nOUTPUT %s\n',char(datetime('now')),folder);
end
