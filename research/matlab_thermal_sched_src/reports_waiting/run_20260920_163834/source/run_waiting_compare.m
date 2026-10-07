function outdir = run_waiting_compare(case_ids)
% Run the agreed 15 feasible instances in the declared order, unchanged data.
% Scheduler decisions use sub=4. Final schedules and optimal completions use
% sub=200 (0.005 ms); this is still a sampled, not continuous-time, constraint.
% Baselines run BEFORE enumeration and have no optimum/schedule input.
if nargin<1, case_ids=[8 17 35 9 18 36 1 4 7 13 16 22 25 31 34]; end
src=fileparts(mfilename('fullpath'));
outdir=fullfile(src,'reports_waiting',['run_' datestr(now,'yyyymmdd_HHMMSS')]);
assert(~exist(outdir,'dir'),'Output already exists.'); mkdir(outdir);
diary(fullfile(outdir,'console.txt')); cleanup=onCleanup(@() diary('off')); %#ok<NASGU>
fprintf('OUTPUT: %s\nMATLAB: %s\n',outdir,version);
fprintf('Priority=[1 2 3 4], mapping=parallel, sample decision=0.25 ms, final=0.005 ms.\n');
fprintf('Order: %s\n',mat2str(case_ids));
% Save exact executable sources alongside results for later reproduction.
mkdir(fullfile(outdir,'source'));
files=dir(fullfile(src,'*.m'));
for k=1:numel(files), copyfile(fullfile(src,files(k).name),fullfile(outdir,'source',files(k).name)); end
test_waiting_baseline();
rows=struct([]); details=cell(numel(case_ids),1);
for z=1:numel(case_ids)
    id=case_ids(z); cfg=case_config(id); th=thermal_build(cfg);
    fprintf('Case %02d START: releases=(%g,%g), deadlines=(%g,%g), T0=%g\n',...
        id,cfg.rA_ms,cfg.rB_ms,cfg.D_A_ms,cfg.D_B_ms,cfg.T0);
    tic_id=tic;
    [pg,Eg,complete_g,~]=greedy_scheduler(cfg,th,'parallel',[1 2 3 4],'energyfirst');
    seconds_g=toc(tic_id);
    wait=waiting_scheduler(cfg,th);
    immediate=waiting_scheduler(cfg,th,struct('max_wait',0));
    vg=assess(pg,complete_g,cfg,th); vw=assess(wait.pi,wait.complete,cfg,th);
    v0=assess(immediate.pi,immediate.complete,cfg,th);
    if complete_g, assert(abs(vg.E_mJ-Eg)<1e-8); end
    if wait.complete, assert(abs(vw.E_mJ-wait.E_mJ)<1e-8); end
    if immediate.complete, assert(abs(v0.E_mJ-immediate.E_mJ)<1e-8); end

    tic_id=tic;
    S=enumerate_schedules(cfg); res=eval_schedules(S,cfg,th);
    [Eopt,Opt,peaks_opt,Ecoarse]=refined_optimum(S,res,cfg,th);
    % Match the fixed mapping domain as well as the unrestricted reference.
    if any(Opt(:,1)==1 & Opt(:,2)==2)
        Eparallel=Eopt;
    else
        mask=S(:,1)==1 & S(:,2)==2;
        rp=struct('E',res.E(mask),'tr_ok',res.tr_ok(mask));
        Eparallel=refined_optimum(S(mask,:),rp,cfg,th);
    end
    seconds_opt=toc(tic_id);
    [cw,gapw]=classify(vw,Eopt); [cg,gapg]=classify(vg,Eopt); [c0,gap0]=classify(v0,Eopt);
    tg=NaN; tw=NaN; t0=NaN;
    if complete_g, tg=first_optimal_divergence(pg,Opt,cfg,true); end
    if wait.complete, tw=first_optimal_divergence(wait.pi,Opt,cfg,true); end
    if immediate.complete, t0=first_optimal_divergence(immediate.pi,Opt,cfg,true); end
    if strcmp(cw,'match'), assert(isnan(tw)); end
    if strcmp(cg,'match'), assert(isnan(tg)); end
    if strcmp(c0,'match'), assert(isnan(t0)); end
    assert(isfinite(Eopt),'An originally feasible instance lost all finer-grid solutions.');
    row=struct('case_id',id,'rA',cfg.rA_ms,'rB',cfg.rB_ms,'DA',cfg.D_A_ms,'DB',cfg.D_B_ms,...
        'T0',cfg.T0,'n_base',size(S,1),'n_opt_fine',size(Opt,1),...
        'Eopt_coarse',Ecoarse,'Eopt',Eopt,'Eopt_parallel',Eparallel,...
        'E_original',valid_energy(vg),'E_matched0',valid_energy(v0),'E_wait',valid_energy(vw),...
        'gap_original',gapg,'gap_matched0',gap0,'gap_wait',gapw,...
        'class_original',cg,'class_matched0',c0,'class_wait',cw,...
        'peak_original',vg.peak,'peak_matched0',v0.peak,'peak_wait',vw.peak,...
        'peak_wait_coarse',vw.peak_coarse,'tstar_original',tg,'tstar_matched0',t0,'tstar_wait',tw,...
        'seconds_original',seconds_g,'seconds_matched0',immediate.seconds,...
        'seconds_wait',wait.seconds,'seconds_opt',seconds_opt,...
        'candidates_wait',wait.candidate_evaluations,'candidates_matched0',immediate.candidate_evaluations);
    rows=[rows;row]; %#ok<AGROW>
    details{z}=struct('cfg',cfg,'original_pi',pg,'original_complete',complete_g,...
        'original_validation',vg,'waiting',wait,'waiting_validation',vw,...
        'matched0',immediate,'matched0_validation',v0,'Opt',Opt,'opt_peaks',peaks_opt);
    writetable(wait.trace,fullfile(outdir,sprintf('case%02d_wait_trace.csv',id)));
    writetable(immediate.trace,fullfile(outdir,sprintf('case%02d_matched0_trace.csv',id)));
    write_case(fullfile(outdir,sprintf('case%02d_report.txt',id)),row,details{z});
    writetable(struct2table(rows),fullfile(outdir,'summary.csv'));
    save(fullfile(outdir,'results.mat'),'rows','details','case_ids');
    fprintf('Case %02d DONE: opt=%.3f original=%s/%.3f matched0=%s/%.3f wait=%s/%.3f peak=%.6f t*=%.0f\n',...
        id,Eopt,cg,valid_energy(vg),c0,valid_energy(v0),cw,valid_energy(vw),vw.peak,tw);
end
fid=fopen(fullfile(outdir,'summary.txt'),'w'); cleanfile=onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'Fixed parameters; decisions from t=0; no reservations or optimum input.\n');
fprintf(fid,'Decision sub=4, common final/reference sub=200. Finite sampled-grid results only.\n');
fprintf(fid,'No-energy-gap entries for incomplete/unsafe schedules; NaN tstar means no divergence for complete matches.\n');
for name={'original','matched0','wait'}
    col={rows.(['class_' name{1}])};
    fprintf(fid,'%s: match=%d costlier=%d failed=%d\n',name{1},...
        sum(strcmp(col,'match')),sum(strcmp(col,'costlier')),sum(strcmp(col,'failed')));
end
fprintf('FINISHED: %s\n',outdir);
end

function c=case_config(id)
assert(id>=1 && id<=36 && id==round(id));
c=config_default();
c.P_A1=c.P_A1*1.6; c.P_B1=c.P_B1*1.6;
c.P_A2=c.P_A2*1.6; c.P_B2=c.P_B2*1.6; c.C=c.C*.25; c.H_ms=28;
releases=[0 0;0 5;5 0;0 10]; deadlines=[18 22;20 24;24 28]; temperatures=[45 60 70];
a=floor((id-1)/9)+1; b=floor(mod(id-1,9)/3)+1; t=mod(id-1,3)+1;
c.rA_ms=releases(a,1); c.rB_ms=releases(a,2);
c.D_A_ms=deadlines(b,1); c.D_B_ms=deadlines(b,2); c.T0=temperatures(t);
end

function v=assess(pi,complete,cfg,th)
if ~complete
    v=validate_schedule(nan(1,8),cfg,th,200); v.peak_coarse=NaN; return;
end
v=validate_schedule(pi,cfg,th,200);
coarse=validate_schedule(pi,cfg,th,4); v.peak_coarse=coarse.peak;
end

function [energy,Opt,peaks,coarse_energy]=refined_optimum(S,res,cfg,th)
% Fine samples contain all coarse samples: start at the coarse lower bound,
% refine every schedule at each energy level until some remain feasible.
% All surviving optimum histories are retained for divergence diagnostics.
energy=Inf; coarse_energy=Inf; Opt=zeros(0,8); peaks=[];
eligible=find(res.tr_ok);
if isempty(eligible), return; end
coarse_energy=min(res.E(eligible))*1e3;
while ~isempty(eligible)
    e=min(res.E(eligible)); band=eligible(abs(res.E(eligible)-e)<=1e-12);
    rr=eval_schedules(S(band,:),cfg,th,struct('sub',200));
    if any(rr.tr_ok)
        energy=e*1e3; Opt=double(S(band(rr.tr_ok),:)); peaks=rr.Tmax(rr.tr_ok); return;
    end
    eligible=eligible(res.E(eligible)>e+1e-12);
end
end

function e=valid_energy(v)
e=NaN; if v.ok, e=v.E_mJ; end
end

function [cls,gap]=classify(v,Eopt)
cls='failed'; gap=NaN;
if ~v.ok, return; end
gap=v.E_mJ-Eopt;
assert(gap>=-1e-7,'Baseline beat enumeration: inspect constraint/evaluation mismatch.');
if abs(gap)<1e-7, cls='match'; else, cls='costlier'; end
end

function write_case(path,row,d)
fid=fopen(path,'w'); cleanfile=onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'case %02d r=(%g,%g) D=(%g,%g) T0=%g H=28\n',row.case_id,row.rA,row.rB,row.DA,row.DB,row.T0);
fprintf(fid,'Optimum coarse=%.6f fine=%.6f fixed-parallel=%.6f; fine optimal histories=%d\n',...
    row.Eopt_coarse,row.Eopt,row.Eopt_parallel,row.n_opt_fine);
fprintf(fid,'pi=[mA mB fA fB sA1 sB1 sA2 sB2]; NaN means not started.\n');
fprintf(fid,'Original: %s complete=%d E=%.6f peak=%.9f tstar=%g reason=%s\n',...
    mat2str(d.original_pi),d.original_complete,row.E_original,row.peak_original,row.tstar_original,d.original_validation.reason);
fprintf(fid,'Matched0: %s complete=%d E=%.6f peak=%.9f tstar=%g reason=%s\n',...
    mat2str(d.matched0.pi),d.matched0.complete,row.E_matched0,row.peak_matched0,row.tstar_matched0,d.matched0_validation.reason);
fprintf(fid,'Waiting:  %s complete=%d E=%.6f peak=%.9f tstar=%g reason=%s\n',...
    mat2str(d.waiting.pi),d.waiting.complete,row.E_wait,row.peak_wait,row.tstar_wait,d.waiting_validation.reason);
fprintf(fid,'Waiting unstarted stage ids: %s\n',mat2str(find(~d.waiting.started)));
fprintf(fid,'One optimum: %s peak=%.9f\n',mat2str(d.Opt(1,:)),d.opt_peaks(1));
fprintf(fid,'Trace action: -1 no feasible candidate, 0 defer without reservation, 1 actual start.\n');
if d.waiting.complete
    fprintf(fid,'\nWaiting decision-before-start state table:\nt done | ready | running | free\n');
    for t=0:d.cfg.H_ms
        st=schedule_state_before(d.waiting.pi,d.cfg,t);
        fprintf(fid,'%d %s | %s | %s | %s\n',t,strjoin(st.done,','),strjoin(st.ready,','),strjoin(st.running,','),strjoin(st.free,','));
    end
end
end
