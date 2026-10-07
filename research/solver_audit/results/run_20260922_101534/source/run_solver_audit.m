function outdir=run_solver_audit(testOnly)
if nargin<1,testOnly=false;end
src=fileparts(mfilename('fullpath'));old=fullfile(src,'..','matlab_thermal_sched_src');addpath(old);
outdir=fullfile(src,'results',['run_' datestr(now,'yyyymmdd_HHMMSS')]);mkdir(outdir);
diary(fullfile(outdir,'console.txt'));clean=onCleanup(@()diary('off')); %#ok<NASGU>
fprintf('MATLAB %s\nOutput %s\n',version,outdir);disp(ver('optim'));
mkdir(fullfile(outdir,'source'));copyfile(fullfile(src,'*.m'),fullfile(outdir,'source'));
copyfile(fullfile(src,'PLAN.md'),outdir);
audit_tests();if testOnly,return;end
cases=audit_cases();save(fullfile(outdir,'inputs.mat'),'cases');
rows=struct([]);details=cell(numel(cases),4);budget=5;allclock=tic;
legacy=readtable(fullfile(old,'reports_waiting','run_20260920_163834','summary.csv'));
for i=1:numel(cases)
 p=cases{i};fprintf('START %d/%d %s n=%d H=%d\n',i,numel(cases),p.id,p.n,p.cfg.H_ms);
 for im=1:4
  names={'wait','portfolio','milp_cold','milp_warm5'};name=names{im};tick=tic;
  a=audit_catalog(p);buildSeconds=toc(tick);
  if im<=2
   o=audit_heuristic(p,a,im==2,tick,budget);lb=p.energyLB;nodes=NaN;flag=0;calls=0;cuts=0;
  else
   o=audit_milp(p,a,im==4,tick,budget);lb=o.lower;nodes=o.nodes;flag=o.exitflag;calls=o.calls;cuts=o.cuts;
  end
  seconds=toc(tick);verify=tic;z=audit_validate(p,a,o.selected);verifySeconds=toc(verify);
  E=NaN;gap=NaN;status='not_found';
  if z.ok
   E=z.energy;assert(lb<=E+1e-5,'Invalid lower bound.');gap=max(0,(E-lb)/max(1,abs(E)));
   status='feasible';if gap<1e-7,status='certified_optimal';end
   if p.legacy>0
    oldrow=legacy.case_id==p.legacy;assert(abs(E-legacy.Eopt(oldrow))<1e-7,'Legacy energy regression.');
   end
  elseif flag==-2,status='proven_infeasible';
  elseif seconds>=budget,status='timeout_no_solution';end
  row=struct('case_id',p.id,'legacy',p.legacy,'stages',p.n,'shape',p.shape,'T0',p.cfg.T0,...
   'limit',p.cfg.T_lim,'method',name,'status',status,'energy_mJ',E,'lower_mJ',lb,...
   'gap',gap,'peak',z.peak,'seconds',seconds,'build_seconds',buildSeconds,...
   'verify_seconds',verifySeconds,'nodes',nodes,'exitflag',flag,'calls',calls,'cuts',cuts,...
   'variables',size(a.v,1),'thermal_rows',size(a.R,1));
  rows=[rows;row];details{i,im}=struct('out',o,'validation',z,'placements',a.v(o.selected(o.selected>0),:)); %#ok<AGROW>
  fprintf('  %s: %s E=%.3f LB=%.3f gap=%.4g time=%.3f build=%.3f\n',name,status,E,lb,gap,seconds,buildSeconds);
  writetable(struct2table(rows),fullfile(outdir,'summary.csv'));
  save(fullfile(outdir,'results.mat'),'rows','details','budget');
  assert(toc(allclock)<1800,'Audit hard timeout (30min).');
 end
end
fprintf('FINISHED %d rows in %.3fs.\n',numel(rows),toc(allclock));
end
