function cases = cv_cases()
% Frozen abstract inputs, not measurements. Internal units: s, W, J.
b = struct('id','','family','','dref',[.005 .005],'alpha',[.2 1], ...
    'u',[2 0],'v',[2 2],'q',.5,'n',[.002 .002],'w',[1 1], ...
    'release',[0 0],'deadline',[.040 .040],'window',.060, ...
    'idle_cpu',.2,'idle_npu',.3,'external',.5,'time_tol',1e-9, ...
    'energy_abs_tol',1e-10,'energy_rel_tol',1e-8,'budget_s',60, ...
    'provenance','abstract_condition_constructed','thermal','not_evaluated');
cases = repmat(b,0,1);
for a = [.2 .6 1]
    c=b; c.id=sprintf('R1_alpha_%02d',round(10*a));
    c.family='R1'; c.alpha(1)=a; cases(end+1)=c;
end
c=b; c.id='R1_pure_square'; c.family='R1'; c.u(1)=0; cases(end+1)=c;
r=b; r.dref=[.004 .006]; r.alpha=[.5 .5]; r.u=[0 0];
r.v=[1 4/3]; r.deadline=[.008 .015];
labels={'below','equal','above'}; scales=[1/3 2/3 4/3];
for j=1:3
    c=r; c.family='R2'; c.v(2)=scales(j);
    c.id=['R2_' labels{j} '_tight']; cases(end+1)=c;
    c.id=['R2_' labels{j} '_loose']; c.deadline(2)=.017; cases(end+1)=c;
end
for n=[.002 .005 .008]
    c=r; c.family='N1'; c.id=sprintf('N1_service_%02dms',round(1000*n));
    c.n(2)=n; c.deadline=[.030 .030]; cases(end+1)=c;
end
c=r; c.id='TEST_impossible'; c.family='TEST'; c.deadline=[.001 .001];
cases(end+1)=c;
end
