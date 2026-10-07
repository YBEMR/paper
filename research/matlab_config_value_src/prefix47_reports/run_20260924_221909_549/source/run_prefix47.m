function folder=run_prefix47()
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(here));
folder=fullfile(here,'prefix47_reports',['run_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
mkdir(folder); diary(fullfile(folder,'console.txt')); g=onCleanup(@()diary('off')); %#ok<NASGU>
try
    design=fullfile(root,'research','prefix46_design'); manifest=jsondecode(fileread(fullfile(design,'freeze_manifest.json')));
    fprintf('START %s MATLAB %s\n',char(datetime('now')),version);
    for x=manifest.files'
        v=c44_audit({fullfile(root,x.path)}); assert(strcmp(v.sha256,x.sha256),'Frozen 46 design changed');
    end
    mkdir(fullfile(folder,'source')); fs=dir(fullfile(here,'*.m')); old={}; snapshots={};
    for k=1:numel(fs)
        p=fullfile(here,fs(k).name); copyfile(p,fullfile(folder,'source'));
        snapshots{end+1}=fullfile(folder,'source',fs(k).name); %#ok<AGROW>
        if ~startsWith(fs(k).name,'p47_') && ~strcmp(fs(k).name,'run_prefix47.m'), old{end+1}=p; end %#ok<AGROW>
    end
    oldhash=c44_audit(old); writejson(fullfile(folder,'old_source_hashes.json'),oldhash);
    for x=manifest.files'
        [~,name,ext]=fileparts(x.path); dest=fullfile(folder,[name ext]);
        copyfile(fullfile(root,x.path),dest); snapshots{end+1}=dest; %#ok<AGROW>
    end
    copyfile(fullfile(design,'freeze_manifest.json'),fullfile(folder,'design_freeze_manifest.json'));
    trials=p47_cases(fullfile(design,'inputs_v1.json'));
    environment=struct('matlab',version,'started',char(datetime('now')),'prefdir',prefdir, ...
        'budget_per_case_method_s',60,'grid_s',.001,'stage','frozen_before_tests');
    save(fullfile(folder,'inputs.mat'),'trials','environment');
    snapshots{end+1}=fullfile(folder,'inputs.mat');
    hashes=c44_audit(snapshots); writejson(fullfile(folder,'run_freeze_manifest.json'),hashes);
    checks=p47_tests(trials); writetable(checks,fullfile(folder,'preflight_checks.csv'));
    fprintf('PREFLIGHT %d/%d\n',sum(checks.passed),height(checks)); assert(all(checks.passed),'Preflight failed');
    runs=cell(numel(trials),2); refs=cell(numel(trials),1);
    for k=1:numel(trials)
        runs{k,1}=c44_policy(trials(k),'C1');
        save(fullfile(folder,'results.mat'),'trials','environment','checks','runs','refs');
        runs{k,2}=p47_witness(trials(k));
        for j=1:2
            fprintf('POLICY %s %s %s %.6f s\n',trials(k).id,runs{k,j}.version,runs{k,j}.status,runs{k,j}.elapsed_s);
            writejson(fullfile(folder,[trials(k).id '_' runs{k,j}.version '.json']),runs{k,j});
        end
        save(fullfile(folder,'results.mat'),'trials','environment','checks','runs','refs');
    end
    fprintf('ALL POLICIES SAVED; REFERENCE BEGINS\n');
    for k=1:numel(trials)
        refs{k}=p47_reference(trials(k),runs{k,1});
        fprintf('REFERENCE %s %s safe=%d violation=%d [%.8g %.8g] mJ loss=%g ms\n',trials(k).id,refs{k}.status, ...
            sum(refs{k}.thermal_state==1),sum(refs{k}.thermal_state==2),refs{k}.lower_J*1000,refs{k}.upper_J*1000,refs{k}.first_loss_time*1000);
        writejson(fullfile(folder,[trials(k).id '_reference.json']),refs{k});
        save(fullfile(folder,'results.mat'),'trials','environment','checks','runs','refs');
    end
    [summary,post]=exportcheck(folder,trials,runs,refs);
    writetable(summary,fullfile(folder,'summary.csv')); writetable(post,fullfile(folder,'post_checks.csv'));
    fprintf('POSTCHECKS %d/%d\n',sum(post.passed),height(post));
    save(fullfile(folder,'results.mat'),'trials','environment','checks','runs','refs','summary','post');
    assert(isequal(oldhash,c44_audit(old)),'Historical source changed');
    assert(isequal(hashes,c44_audit(snapshots)),'Frozen snapshot changed');
    for x=manifest.files'
        v=c44_audit({fullfile(root,x.path)}); assert(strcmp(v.sha256,x.sha256),'46 frozen file changed');
    end
    writejson(fullfile(folder,'audit.json'),struct('historical_source_count',numel(old),'historical_sources_unchanged',true, ...
        'run_snapshot_unchanged',true,'design_unchanged',true,'all_checks_passed',all(post.passed)));
    plots(folder,trials,runs);
    if all(post.passed), fprintf('COMPLETE\n'); else, fprintf('COMPLETE WITH CHECK DISCREPANCIES; DO NOT MODIFY INPUTS\n'); end
    fprintf('OUTPUT %s\n',folder);
catch err
    s=getReport(err,'extended','hyperlinks','off'); fprintf('%s\n',s);
    fid=fopen(fullfile(folder,'failure.txt'),'w'); fprintf(fid,'%s',s); fclose(fid); rethrow(err);
end
end

function [summary,checks]=exportcheck(folder,trials,runs,refs)
records=struct([]); scheduleRows=struct([]); names={}; values=[]; notes={};
for k=1:numel(trials)
    c=trials(k).case; h=trials(k).thermal; ref=refs{k};
    refT=array2table([ref.rows ref.energy ref.thermal_state ref.peaks], ...
        'VariableNames',{'modeA','modeB','unitA','unitB','startA_s','startB_s','startAN_s','startBN_s','energy_J','thermal_state','peakCPU_C','peakNPU_C'});
    writetable(refT,fullfile(folder,[trials(k).id '_reference_rows.csv']));
    add([trials(k).id '_ref_18_complete'],strcmp(ref.status,'complete') && size(ref.rows,1)==18,'Full finite-domain coverage');
    add([trials(k).id '_ref_HH_90mJ'],ref.energy_exact && isequal(ref.optimal_modes,4) && abs(ref.upper_J-.09)<c.energy_abs_tol,'Common-domain exact lower/upper');
    for j=1:2
        r=runs{k,j}; s=r.schedule; tag=[trials(k).id '_' r.version];
        v=c44_validate(c,s,true); z=c44_thermal(c,s,h);
        add([tag '_partial_legal'],v.feasible,v.reason);
        add([tag '_no_error_or_timeout'],~ismember(r.status,{'error','timeout'}),r.message);
        complete=strcmp(r.status,'complete') && all(isfinite(s.start)); valid=false; E=nan; gap=nan;
        if complete
            v=c44_validate(c,s); e=cv_energy(c,s); E=1000*e.integral; valid=v.feasible && strcmp(z.status,'safe');
            add([tag '_energy_dual'],e.difference<=max(c.energy_abs_tol,c.energy_rel_tol*abs(e.integral)),'Integral versus base + increments');
            add([tag '_complete_safe'],valid,v.reason);
            if valid && ref.energy_exact, gap=1000*(e.integral-ref.upper_J); end
        end
        if j==1
            previous=c44_schedule(c);
            for ev=r.events
                known=isfinite(previous.start);
                add(sprintf('%s_prefix_%g_ms',tag,ev.time*1000),isequaln(previous.start(known),ev.prefix.start(known)) && ...
                    isequaln(previous.unit(known),ev.prefix.unit(known)) && isequaln(previous.modes(isfinite(previous.modes)),ev.prefix.modes(isfinite(previous.modes))), ...
                    'Committed work not rewritten');
                if ev.selected>0
                    zz=c44_thermal(c,ev.prefix,h);
                    add(sprintf('%s_admission_%g_ms',tag,ev.time*1000),strcmp(zz.status,'safe'),'Independent committed-trajectory reevaluation');
                end
                previous=ev.prefix;
            end
        end
        row=struct('case_id',trials(k).id,'method',r.version,'status',r.status,'valid_complete',valid, ...
            'completion_A_ms',s.finish(3)*1000,'completion_B_ms',s.finish(4)*1000, ...
            'energy_mJ',E,'gap_mJ',gap,'peak_CPU_C',z.peak(1),'peak_NPU_C',z.peak(2), ...
            'temperature_scope',ternary(complete,'full_schedule','committed_only_not_complete'), ...
            'thermal_calls',r.thermal_evaluations,'library_count',r.library_count,'elapsed_s',r.elapsed_s);
        records=[records;row]; %#ok<AGROW>
        for i=1:4
            sr=struct('case_id',trials(k).id,'method',r.version,'stage',i,'unit',s.unit(i), ...
                'start_ms',s.start(i)*1000,'finish_ms',s.finish(i)*1000,'duration_ms',s.duration(i)*1000,'increment_W',s.increment(i));
            scheduleRows=[scheduleRows;sr]; %#ok<AGROW>
        end
    end
    if k==1
        add('analytic_hot_C1_A_only',strcmp(runs{k,1}.status,'thermal_blocked') && isequal(isfinite(runs{k,1}.schedule.start),[true false false false]) && runs{k,1}.schedule.start(1)==0,'Expected analytical path; not used by policy');
        add('analytic_hot_prefix_excluded',ref.first_loss_time==0 && ~isempty(ref.prefixes) && ref.prefixes{1}.count==2 && ref.prefixes{1}.violation==2,'Actual CPU label fixed; both suffixes excluded');
        add('analytic_hot_witness_B_first',max(abs(runs{k,2}.schedule.start-[.001 0 .009 .004]))<c.time_tol,'Representative predicted in 46, independently generated');
        add('analytic_hot_reference_counts',sum(ref.thermal_state==1)==6 && sum(ref.thermal_state==2)==12,'Every row checked; not inferred from one witness');
    else
        add('analytic_cold_both_start',all(runs{k,1}.schedule.start(1:2)==0) && strcmp(runs{k,1}.status,'complete'),'Normal condition');
        add('analytic_cold_all_safe',all(ref.thermal_state==1),'No hot-state exclusion carried into cold input');
    end
end
summary=struct2table(records); writetable(struct2table(scheduleRows),fullfile(folder,'schedules.csv'));
checks=table(names',logical(values'),notes','VariableNames',{'name','passed','note'});
    function add(n,v,t), names{end+1}=n; values(end+1)=v; notes{end+1}=t; end
end

function plots(folder,trials,runs)
for k=1:numel(trials)
    fig=figure('Visible','off','Position',[40 40 1150 680]); tiledlayout(2,2); colors=lines(4);
    for j=1:2
        r=runs{k,j}; s=r.schedule; nexttile(j); hold on;
        labels={'A1','B1','A2','B2'};
        for i=1:4
            if ~isfinite(s.start(i)), continue; end
            rectangle('Position',[s.start(i)*1000,s.unit(i)-.3,s.duration(i)*1000,.6],'FaceColor',colors(i,:));
            text((s.start(i)+s.duration(i)/2)*1000,s.unit(i),labels{i},'HorizontalAlignment','center');
        end
        ylim([.4 3.6]); yticks(1:3); yticklabels({'CPU1','CPU2','NPU'}); xlim([0 15]); xlabel('Time (ms)'); grid on;
        title([trials(k).id ' / ' r.version ' / ' r.status],'Interpreter','none');
        nexttile(j+2); z=c44_thermal(trials(k).case,s,trials(k).thermal); [t,T]=thv_trace(z,trials(k).thermal,.0001);
        plot(t*1000,T,'LineWidth',1.2); hold on; yline(80,'--'); xlim([0 60]); grid on;
        title(ternary(strcmp(r.status,'complete'),'Full schedule and idle tail','Committed work only; request set incomplete'));
        xlabel('Time (ms)'); ylabel('Temperature (C)'); legend('CPU','NPU','Limit','Location','best');
    end
    exportgraphics(fig,fullfile(folder,[trials(k).id '.png']),'Resolution',130); close(fig);
end
end
function s=ternary(c,a,b), if c, s=a; else, s=b; end, end
function writejson(path,value)
fid=fopen(path,'w','n','UTF-8'); assert(fid>=0); g=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',jsonencode(value,'PrettyPrint',true));
end
