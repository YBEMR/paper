function run_solver_diagnostic(runDir)
% Adaptive follow-up only on unresolved/costlier primary cases, original data.
src=fileparts(mfilename('fullpath'));addpath(fullfile(src,'..','matlab_thermal_sched_src'));
load(fullfile(runDir,'inputs.mat'),'cases');t=readtable(fullfile(runDir,'summary.csv'));
outdir=fullfile(runDir,'diagnostic');mkdir(outdir);diary(fullfile(outdir,'console.txt'));cl=onCleanup(@()diary('off')); %#ok<NASGU>
copyfile(fullfile(src,'audit_config_portfolio.m'),outdir);copyfile(fullfile(src,'run_solver_diagnostic.m'),outdir);
rows=struct([]);details={};indices=[];
for i=1:numel(cases)
 p=cases{i};rr=t(strcmp(t.case_id,p.id) & strcmp(t.method,'portfolio'),:);
 if strcmp(rr.status{1},'certified_optimal'),continue;end
 fprintf('DIAGNOSTIC %s\n',p.id);tick=tic;a=audit_catalog(p);build=toc(tick);
 o=audit_config_portfolio(p,a,tick,5);seconds=toc(tick);z=audit_validate(p,a,o.selected);
 E=NaN;gap=NaN;status='not_found';
 if z.ok,E=z.energy;gap=(E-p.energyLB)/E;status='feasible';if gap<1e-7,status='certified_optimal';end
 elseif seconds>=5,status='timeout_no_solution';end
 rows=[rows;struct('case_id',p.id,'status',status,'energy_mJ',E,'lower_mJ',p.energyLB,...
  'gap',gap,'peak',z.peak,'seconds',seconds,'build_seconds',build,'combinations',o.combinations,'attempts',o.attempts)]; %#ok<AGROW>
 indices(end+1)=i;details{end+1}=struct('out',o,'validation',z,'placements',a.v(o.selected(o.selected>0),:)); %#ok<AGROW>
 fprintf('%s E=%.3f LB=%.3f gap=%.4g seconds=%.3f combinations=%d\n',status,E,p.energyLB,gap,seconds,o.combinations);
 writetable(struct2table(rows),fullfile(outdir,'summary.csv'));save(fullfile(outdir,'results.mat'),'rows','details','indices');
end
end
