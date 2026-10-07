function audit_tests()
c=audit_cases();p=c{1};a=audit_catalog(p);
w=waiting_scheduler(p.cfg,p.th,struct('map_mode','auto'));sel=pi_to_sel(w.pi,a);
z=audit_validate(p,a,sel);v=validate_schedule(w.pi,p.cfg,p.th,200);
assert(z.ok==v.ok && abs(z.energy-v.E_mJ)<1e-8 && abs(z.peak-v.peak)<1e-7);
T=a.base+sum(a.R(:,sel),2);coarse=audit_validate(p,a,sel,4);
assert(abs(max([p.cfg.T0;T])-coarse.peak)<1e-7,'Convolution vs direct propagation');
assert(max(a.occ(:,sel)*ones(p.n,1))==1);
assert(all(a.dep(:,sel)*ones(p.n,1)<=0));
for j=1:5
 bad=sel;bad(1)=0;z=audit_validate(p,a,bad);assert(~z.ok && isnan(z.energy));
end
% Cross-check a generic rolling baseline against the unchanged implementation.
tick=tic;h=audit_heuristic(p,a,false,tick,5);z=audit_validate(p,a,h.selected);
assert(z.ok && abs(z.energy-w.E_mJ)<1e-8);
% Initial temperature, dependency and resource failures must not be accepted.
hot=p;hot.cfg.T0=81;z=audit_validate(hot,a,sel);assert(~z.ok);
bad=sel;ks=a.byStage{4};k=ks(a.v(ks,6)==a.v(sel(3),6));
if ~isempty(k),bad(4)=k(1);z=audit_validate(p,a,bad);assert(~z.ok);end
% Old independent enumerator provides reference energy for case08 (all cores).
S=enumerate_schedules(p.cfg);rr=eval_schedules(S,p.cfg,p.th);
e=min(rr.E(rr.tr_ok))*1000;assert(abs(e-258.5)<1e-7);
tick=tic;m=audit_milp(p,a,false,tick,5);z=audit_validate(p,a,m.selected);
assert(z.ok && abs(z.energy-e)<1e-7 && m.lower<=e+1e-6);
fprintf('PASS: catalog/direct RC, legacy evaluator, rolling baseline, invalid schedules, independent enumeration/MILP.\n');
end
function sel=pi_to_sel(pi,a)
sel=zeros(1,4);cores=[pi(1:2) 3 3];freq=[pi(3:4) 1 1];s=pi(5:8);
for j=1:4
 k=find(a.v(:,1)==j & a.v(:,2)==cores(j) & a.v(:,3)==freq(j) & a.v(:,6)==s(j));
 assert(numel(k)==1);sel(j)=k;
end
end
