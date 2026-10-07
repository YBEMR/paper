function folder=run_stage55(mode,receipt)
% Explicit modes. Frozen mode requires a matching successful precheck receipt.
if nargin<1,mode='precheck';end
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));design=fullfile(root,'research','stage53_design');
folder=fullfile(here,'stage55_reports',[mode '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
mkdir(folder);diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
try
    [trials,rules]=s55_load(design); fprintf('START %s MATLAB %s MODE %s\n',char(datetime('now')),version,mode);
    allm=dir(fullfile(here,'*.m'));old={};source={};
    for i=1:numel(allm)
        p=fullfile(here,allm(i).name);
        if startsWith(allm(i).name,'s55_') || strcmp(allm(i).name,'run_stage55.m')
            source{end+1}=p; %#ok<AGROW>
        else,old{end+1}=p;end %#ok<AGROW>
    end
    deps={'thv_build.m','thv_step.m','thv_trace.m','c44_audit.m'};
    for i=1:numel(deps),source{end+1}=fullfile(here,deps{i});end
    source=[source {fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json')}];
    sourcehash=c44_audit(source);oldhash=c44_audit(old);
    writejson(fullfile(folder,'source_hashes.json'),sourcehash);writejson(fullfile(folder,'old_source_hashes.json'),oldhash);
    mkdir(fullfile(folder,'source'));
    for i=1:numel(source),[~,n,e]=fileparts(source{i});copyfile(source{i},fullfile(folder,'source',[n e]));end
    environment=struct('matlab',version,'prefdir',prefdir,'started',char(datetime('now')), ...
        'mode',mode,'budget_s',60,'case_count',numel(trials),'root',root);
    save(fullfile(folder,'inputs.mat'),'trials','rules','environment');
    writejson(fullfile(folder,'environment.json'),environment);
    if strcmp(mode,'precheck')
        checks=s55_tests(trials);writetable(checks,fullfile(folder,'prechecks.csv'));
        fprintf('PRECHECK %d/%d\n',sum(checks.passed),height(checks));
        pass=all(checks.passed);save(fullfile(folder,'receipt.mat'),'pass','checks','sourcehash','oldhash','environment');
        assert(pass,'s55:precheck','Prechecks failed; frozen run prohibited');
    elseif strcmp(mode,'frozen')
        assert(nargin>=2 && isfile(receipt),'s55:receipt','Explicit precheck receipt required');
        prior=load(receipt,'pass','sourcehash','oldhash','checks');
        assert(prior.pass && isequal(prior.sourcehash,sourcehash) && isequal(prior.oldhash,oldhash),'s55:receipt','Precheck hashes do not match');
        copyfile(receipt,fullfile(folder,'precheck_receipt.mat'));checks=prior.checks;
        runs=cell(numel(trials),2);refs=cell(numel(trials),1);
        for i=1:numel(trials)
            for j=1:2
                names={'joint_noheat','full_suffix'};
                fprintf('BEGIN %s %s\n',trials(i).id,names{j});
                runs{i,j}=s55_method(trials(i),names{j});
                emit(runs{i,j});writejson(fullfile(folder,[trials(i).id '_' names{j} '.json']),runs{i,j});
                save(fullfile(folder,'results.mat'),'trials','rules','environment','checks','runs','refs','-v7.3');
                assert(~strcmp(runs{i,j}.status,'error'),'s55:implementation','Method implementation error; preserve run and fix');
            end
        end
        fprintf('ALL BASELINES SAVED; THERMAL REFERENCES BEGIN\n');
        for i=1:numel(trials)
            fprintf('BEGIN %s thermal_reference\n',trials(i).id);
            refs{i}=s55_method(trials(i),'thermal_reference');emit(refs{i});
            writejson(fullfile(folder,[trials(i).id '_thermal_reference.json']),refs{i});
            save(fullfile(folder,'results.mat'),'trials','rules','environment','checks','runs','refs','-v7.3');
            assert(~strcmp(refs{i}.status,'error'),'s55:implementation','Reference implementation error; preserve run and fix');
        end
        [summary,post]=s55_export(folder,trials,runs,refs);
        writetable(summary,fullfile(folder,'summary.csv'));writetable(post,fullfile(folder,'postchecks.csv'));
        save(fullfile(folder,'results.mat'),'trials','rules','environment','checks','runs','refs','summary','post','-v7.3');
        fprintf('POSTCHECK %d/%d\n',sum(post.passed),height(post));assert(all(post.passed),'s55:postcheck','Independent result checks failed');
    else,error('s55:mode','Use precheck or frozen');end
    assert(isequal(sourcehash,c44_audit(source)),'s55:hash','Frozen source/input changed');
    assert(isequal(oldhash,c44_audit(old)),'s55:hash','Historical source changed');
    writejson(fullfile(folder,'audit.json'),struct('source_and_input_unchanged',true,'historical_source_unchanged',true, ...
        'historical_source_count',numel(old),'mode',mode,'complete',true));
    fprintf('OUTPUT %s\nCOMPLETE\n',folder);
catch err
    msg=getReport(err,'extended','hyperlinks','off');fprintf('%s\n',msg);
    fid=fopen(fullfile(folder,'failure.txt'),'w','n','UTF-8');fprintf(fid,'%s',msg);fclose(fid);rethrow(err);
end
end
function emit(r)
fprintf('RESULT %s %s status=%s candidates=%d visited=%d thermal=%d elapsed=%.3fs bounds=[%.9g %.9g]J\n', ...
    r.input_id,r.method,r.status,r.library_count,r.visited,r.thermal_calls,r.elapsed_s,r.lower_J,r.upper_J);
end
function writejson(p,v)
fid=fopen(p,'w','n','UTF-8');assert(fid>=0);g=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',jsonencode(v,'PrettyPrint',true));
end
