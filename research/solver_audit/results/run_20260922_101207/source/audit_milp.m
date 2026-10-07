function out=audit_milp(p,a,warm,clock0,budget)
nv=size(a.v,1);out=struct('selected',zeros(1,p.n),'energy',Inf,'lower',p.energyLB,...
 'nodes',0,'exitflag',0,'calls',0,'cuts',0,'message','','warmSeconds',0);
x0=[];
if warm
 t=tic;h=audit_heuristic(p,a,true,clock0,budget);out.warmSeconds=toc(t);
 if isfinite(h.energy)
  out.selected=h.selected;out.energy=h.energy;x0=zeros(nv,1);x0(h.selected)=1;
 end
 if out.energy<=out.lower+1e-7,out.exitflag=1;out.message='Analytic lower bound matched by warm start.';return;end
end
A=[a.occ;a.dep;a.R];b=[ones(size(a.occ,1),1);zeros(size(a.dep,1),1);p.cfg.T_lim-a.base];
rel=0;if warm,rel=.05;end
seen=[];
while toc(clock0)<budget
 opt=optimoptions('intlinprog','Display','off','MaxTime',max(.01,budget-toc(clock0)),...
  'RelativeGapTolerance',rel,'AbsoluteGapTolerance',1e-8,'ConstraintTolerance',1e-8);
 [x,f,flag,info]=intlinprog(a.energy,1:nv,A,b,a.eq,ones(p.n,1),zeros(nv,1),ones(nv,1),x0,opt);
 out.calls=out.calls+1;out.exitflag=flag;out.message=info.message;
 if isfield(info,'numnodes'),out.nodes=out.nodes+info.numnodes;end
 if ~isempty(f) && isfinite(f) && isfield(info,'absolutegap') && isfinite(info.absolutegap)
  out.lower=max(out.lower,a.idleEnergy+f-info.absolutegap);
 end
 if flag==-2,out.lower=Inf;break;end
 if isempty(x),break;end
 selected=zeros(1,p.n);
 for j=1:p.n
  ks=a.byStage{j};[value,ii]=max(x(ks));if value>.5,selected(j)=ks(ii);end
 end
 val=audit_validate(p,a,selected);
 if val.ok
  if val.energy<out.energy,out.energy=val.energy;out.selected=selected;end
  break;
 elseif ~strcmp(val.reason,'thermal')
  error('MILP incumbent failed independent legality: %s',val.reason);
 end
 % Add all violating fine-grid timestamps (all nodes), never change objective.
 times=setdiff(unique(val.badTimes),seen);seen=union(seen,times);
 if isempty(times),error('Thermal cut loop made no progress.');end
 [R,base]=audit_thermal_rows(p,a,times);A=[A;R];b=[b;p.cfg.T_lim-base]; %#ok<AGROW>
 out.cuts=out.cuts+3*numel(times);
end
end
