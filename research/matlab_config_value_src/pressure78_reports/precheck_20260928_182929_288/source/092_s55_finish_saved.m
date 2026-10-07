function folder=s55_finish_saved(runfolder,receipt)
% POSTPROCESS ONLY: no calls to any scheduling/method/enumeration function.
% Preserve original checkpoint, failure log, source snapshot and budgets.
p=load(receipt,'pass','sourcehash','oldhash');assert(p.pass,'Precheck must pass');
assert(isequal(p.sourcehash,c44_audit({p.sourcehash.path})),'Current postprocess precheck hashes changed');
old=jsondecode(fileread(fullfile(runfolder,'old_source_hashes.json')));
assert(isequal(old(:),reshape(c44_audit({old.path}),[],1)),'Historical source changed');
original=jsondecode(fileread(fullfile(runfolder,'source_hashes.json')));
changed={};
for i=1:numel(original)
    a=c44_audit({original(i).path});
    if ~strcmpi(a.sha256,original(i).sha256)
        [~,name,ext]=fileparts(original(i).path);changed{end+1}=[name ext]; %#ok<AGROW>
    end
end
assert(all(ismember(changed,{'s55_export.m','s55_tests.m'})),'A computational method/input changed; post-only recovery refused');
folder=fullfile(runfolder,['postprocess_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);mkdir(folder);
diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
try
    checkpoint=fullfile(runfolder,'results.mat');before=c44_audit({checkpoint});
    d=load(checkpoint);assert(all(~cellfun(@isempty,d.runs(:))) && all(~cellfun(@isempty,d.refs(:))),'Incomplete saved method results');
    copyfile(receipt,fullfile(folder,'postprocess_precheck_receipt.mat'));
    for f={'s55_export.m','s55_tests.m','s55_finish_saved.m'}
        copyfile(fullfile(fileparts(mfilename('fullpath')),f{1}),fullfile(folder,f{1}));
    end
    [summary,post]=s55_export(folder,d.trials,d.runs,d.refs);
    writetable(summary,fullfile(folder,'summary.csv'));writetable(post,fullfile(folder,'postchecks.csv'));
    save(fullfile(folder,'postprocess.mat'),'summary','post','-v7.3');
    assert(all(post.passed),'Postchecks failed');assert(isequal(before,c44_audit({checkpoint})),'Saved numerical results changed');
    audit=struct('mode','postprocess_only','method_calls_repeated',0,'saved_results_unchanged',true, ...
        'original_run',runfolder,'original_checkpoint_hash',before,'historical_sources_unchanged',true, ...
        'changed_new_sources',{changed},'postchecks_passed',sum(post.passed),'postchecks_total',height(post));
    fid=fopen(fullfile(folder,'audit.json'),'w','n','UTF-8');fprintf(fid,'%s',jsonencode(audit,'PrettyPrint',true));fclose(fid);
    fprintf('POSTCHECK %d/%d\nOUTPUT %s\nCOMPLETE POSTPROCESS ONLY\n',sum(post.passed),height(post),folder);
catch err
    msg=getReport(err,'extended','hyperlinks','off');fid=fopen(fullfile(folder,'failure.txt'),'w','n','UTF-8');fprintf(fid,'%s',msg);fclose(fid);rethrow(err);
end
end
