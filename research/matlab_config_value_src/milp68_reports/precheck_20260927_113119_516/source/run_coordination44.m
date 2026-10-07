function folder=run_coordination44()
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(here));
folder=fullfile(here,'coordination44_reports',['run_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
mkdir(folder); diary(fullfile(folder,'console.txt')); guard=onCleanup(@()diary('off')); %#ok<NASGU>
try
    fprintf('START %s MATLAB %s\n',char(datetime('now')),version);
    design=fullfile(root,'research','coordination43_design'); manifest=jsondecode(fileread(fullfile(design,'freeze_manifest.json')));
    for v=manifest.files'
        actual=c44_audit({fullfile(root,v.path)}); assert(strcmp(actual.sha256,v.sha256),'Frozen design hash changed');
    end
    allfiles=dir(fullfile(here,'*.m')); oldpaths={}; mkdir(fullfile(folder,'source'));
    for i=1:numel(allfiles)
        p=fullfile(here,allfiles(i).name); copyfile(p,fullfile(folder,'source'));
        if ~startsWith(allfiles(i).name,'c44_') && ~strcmp(allfiles(i).name,'run_coordination44.m'), oldpaths{end+1}=p; end %#ok<AGROW>
    end
    oldhash=c44_audit(oldpaths); copyfile(fullfile(design,'inputs_v1.json'),fullfile(folder,'inputs.json'));
    copyfile(fullfile(root,'research','43_多CPU单元配置协调最小验证定义.md'),fullfile(folder,'rules43.md'));
    copyfile(fullfile(here,'COORDINATION44_README.md'),fullfile(folder,'source'));
    writejson('old_source_hashes.json',oldhash);
    trials=c44_cases(fullfile(design,'inputs_v1.json'));
    environment=struct('matlab',version,'started',char(datetime('now')),'status','frozen_before_tests', ...
        'reference_budget_s',60,'policy_budget_s',60,'source_input','coordination43-v1','units','seconds/watts/joules/degC');
    save(fullfile(folder,'inputs.mat'),'trials','environment');
    frozen=dir(fullfile(folder,'source','*')); pp={fullfile(folder,'inputs.json'),fullfile(folder,'rules43.md')};
    for i=1:numel(frozen), if ~frozen(i).isdir, pp{end+1}=fullfile(folder,'source',frozen(i).name); end, end %#ok<AGROW>
    writejson('freeze_manifest.json',c44_audit(pp));
    checks=c44_tests(trials); writetable(checks,fullfile(folder,'preflight_checks.csv'));
    fprintf('PREFLIGHT %d/%d\n',sum(checks.passed),height(checks)); assert(all(checks.passed),'Preflight checks failed');
    runs=cell(numel(trials),2); refs=cell(numel(trials),1);
    for k=1:numel(trials)
        for j=1:2
            versions={'C0','C1'}; runs{k,j}=c44_policy(trials(k),versions{j});
            fprintf('POLICY %s %s %s %.4fs\n',trials(k).id,versions{j},runs{k,j}.status,runs{k,j}.elapsed_s);
            save(fullfile(folder,'results.mat'),'trials','environment','checks','runs','refs');
        end
    end
    fprintf('ALL POLICIES FINISHED; THERMAL REFERENCE STARTS\n');
    for k=1:numel(trials)
        refs{k}=c44_reference(trials(k),runs{k,2});
        fprintf('REFERENCE %s %s [%g,%g] mJ %.4fs\n',trials(k).id,refs{k}.status,refs{k}.lower_J*1000,refs{k}.upper_J*1000,refs{k}.elapsed_s);
        save(fullfile(folder,'results.mat'),'trials','environment','checks','runs','refs');
    end
    summary=c44_export(folder,trials,runs,refs); post=c44_postchecks(trials,runs,refs);
    writetable(post,fullfile(folder,'post_checks.csv')); fprintf('POSTCHECKS %d/%d\n',sum(post.passed),height(post));
    save(fullfile(folder,'results.mat'),'trials','environment','checks','runs','refs','post','summary');
    assert(all(post.passed),'Post checks failed');
    after=c44_audit(oldpaths); assert(isequal(oldhash,after),'Historical source modified');
    copyhash=c44_audit(pp); initial=jsondecode(fileread(fullfile(folder,'freeze_manifest.json')));
    assert(isequal(string({copyhash.sha256}),string({initial.sha256})),'Snapshot changed');
    writejson('audit.json',struct('old_sources_unchanged',true,'source_snapshot_unchanged',true,'old_source_count',numel(oldpaths)));
    c44_plots(folder,trials,runs);
    fprintf('COMPLETE\nOUTPUT %s\n',folder);
catch err
    text=getReport(err,'extended','hyperlinks','off'); fprintf('%s\n',text);
    fid=fopen(fullfile(folder,'failure.txt'),'w'); fprintf(fid,'%s',text); fclose(fid);
    rethrow(err);
end
    function writejson(name,value)
        fid=fopen(fullfile(folder,name),'w','n','UTF-8'); assert(fid>=0); g=onCleanup(@()fclose(fid)); %#ok<NASGU>
        fprintf(fid,'%s',jsonencode(value,'PrettyPrint',true));
    end
end
