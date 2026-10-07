function folder = run_thermal_value()
here=fileparts(mfilename('fullpath'));
folder=fullfile(here,'thermal_reports',['run_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
assert(~isfolder(folder)); mkdir(folder); diary(fullfile(folder,'console.txt'));
cleanup=onCleanup(@()diary('off')); %#ok<NASGU>
fprintf('START %s\nMATLAB %s\n',char(datetime('now')),version);
trials=thv_cases();
environment=struct('matlab',version,'started',char(datetime('now')),'units','s,W,J,C', ...
    'scope','grid start times, continuous segment extrema, abstract two-node RC', ...
    'ordering','All earliest, legal common shifts, then exhaustive stage start grids', ...
    'test_fixture','Cold CPU/hot NPU zero-input internal peak; see frozen thv_tests source');
save(fullfile(folder,'inputs.mat'),'trials','environment');
fid=fopen(fullfile(folder,'inputs.json'),'w'); assert(fid>=0);
fwrite(fid,jsonencode(struct('environment',environment,'trials',trials),'PrettyPrint',true),'char'); fclose(fid);
mkdir(fullfile(folder,'source')); files=dir(fullfile(here,'*.m'));
for j=1:numel(files), copyfile(fullfile(here,files(j).name),fullfile(folder,'source')); end
copyfile(fullfile(here,'THERMAL_README.md'),fullfile(folder,'source'));
fprintf('FROZEN %s\n',folder);
results=cell(1,numel(trials));
for k=1:numel(trials)
    try
        r=thv_search(trials(k));
    catch err
        r=struct('status','error','message',err.message,'stack',err.stack);
        fprintf('%s\n',getReport(err,'extended','hyperlinks','off'));
    end
    results{k}=r;
    if strcmp(r.status,'completed')
        fprintf('%s resolved=%d recovered=%d %.4f s evaluations=%d\n',trials(k).id, ...
            r.all_modes_resolved,r.recovered_lower_bound,r.elapsed_s,sum([r.modes.evaluated]));
    else, fprintf('%s ERROR\n',trials(k).id); end
    save(fullfile(folder,'results.mat'),'trials','environment','results');
end
assert(all(cellfun(@(x)strcmp(x.status,'completed'),results)),'Case error: inspect saved results');
thv_export(folder,trials,results);
checks=thv_tests(trials,results); writetable(checks,fullfile(folder,'checks.csv'));
save(fullfile(folder,'results.mat'),'trials','environment','results','checks');
fprintf('CHECKS %d/%d passed\n',sum(checks.passed),height(checks));
assert(all(checks.passed),'Thermal checks failed');
thv_plots(folder,trials,results);
disp(readtable(fullfile(folder,'summary.csv'),'TextType','string'));
fprintf('COMPLETE %s\nOUTPUT %s\n',char(datetime('now')),folder);
end
