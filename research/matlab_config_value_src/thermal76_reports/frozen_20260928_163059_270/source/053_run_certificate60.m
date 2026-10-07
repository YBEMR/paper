function folder=run_certificate60()
% Independent certificate checking; no enumeration or scheduling policy.
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));
design=fullfile(root,'research','stage53_design');base=fullfile(root,'research','stage60_verification');
folder=fullfile(base,['run_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);mkdir(folder);
diary(fullfile(folder,'console.txt'));guard=onCleanup(@()diary('off')); %#ok<NASGU>
checks=struct('name',{},'passed',{}); results=struct([]); schedules=struct([]);
try
 raw=jsondecode(fileread(fullfile(design,'inputs_v1.json')));
 protocol=jsondecode(fileread(fullfile(base,'protocol_v1.json')));
 [trials,rules]=s55_load(design);
 deps={'run_certificate60.m','s55_load.m','s55_schedule.m','s55_validate.m','s55_energy.m','s55_thermal.m','s55_budget.m','thv_build.m','thv_step.m','c44_audit.m'};
 paths=cellfun(@(x)fullfile(here,x),deps,'UniformOutput',false);
 paths=[paths {fullfile(design,'inputs_v1.json'),fullfile(design,'rules_v1.json'),fullfile(base,'protocol_v1.json')}];
 hashes=c44_audit(paths);writejson(fullfile(folder,'source_hashes.json'),hashes);
 mkdir(fullfile(folder,'source'));for z=1:numel(paths),[~,n,e]=fileparts(paths{z});copyfile(paths{z},fullfile(folder,'source',[n e]));end
 environment=struct('matlab',version,'prefdir',prefdir,'operation','certificate validation; no search','started',char(datetime('now')));
 writejson(fullfile(folder,'environment.json'),environment);
 historical=fullfile(here,'stage55_reports','frozen_20260925_173727_619');
 check('four frozen cases',numel(protocol.cases)==4);
 for k=1:4
  id=protocol.cases{k};tr=trials(strcmp({trials.id},id));cR=tr.case;h=tr.thermal;cI=inverse(cR,raw);
  check([id ' cold only'],all(h.initial==30));
  for i=1:8
   a=raw.cpu_response.parameters(mod(i-1,4)+1);opts=cR.options{i};
   for j=1:size(opts,1)
    if opts(j,1)==3,continue;end
    x=raw.cpu_frequencies(opts(j,2)).ratio_to_reference;
    check(sprintf('%s table %d %d',id,i,j),abs(opts(j,3)-a.reference_duration_s*((1-a.alpha)+a.alpha/x))<1e-12 && abs(opts(j,4)-(a.u_W+a.v_W*x*x))<1e-12);
   end
  end
  oldid=regexprep(id,'D10','D6');oldpath=fullfile(historical,[oldid '_joint_noheat.json']);old=jsondecode(fileread(oldpath));
  oldsha=c44_audit({oldpath});writejson(fullfile(folder,[id '_historical_source.json']),oldsha);
  sI=fromspec(cI,old.schedule.unit,old.schedule.mode,old.schedule.start);
  if contains(id,'D10')
   if contains(id,'P_low'),w=protocol.wide_low;else,w=protocol.wide_high;end
   sR=fromspec(cR,w.unit,w.mode,w.start_ms/1000);
  else,sR=fromspec(cR,old.schedule.unit,old.schedule.mode,old.schedule.start);end
  replay=fromspec(cR,sI.unit,sI.mode,sI.start);
  candidate={sI,sR,replay};models={cI,cR,cR};names={'I_planned','R_planned','I_replayed_R'};
  for j=1:3
   timer=tic;s=candidate{j};c=models{j};
   v=independent_check(c,s);check([id ' ' names{j} ' independent legality'],v);
   oldv=s55_validate(c,s);check([id ' ' names{j} ' old legality'],oldv.feasible);
   energy=energy_direct(c,s);olde=s55_energy(c,s);
   check([id ' ' names{j} ' energy double integral'],abs(energy-olde.integral_J)<1e-10);
   z=symmetric_thermal(c,s,h);oldz=s55_thermal(c,s,h);
   check([id ' ' names{j} ' continuous peak agreement'],max(abs(z.peak-oldz.peak))<1e-8);
   check([id ' ' names{j} ' ode crosscheck'],z.ode_error<1e-6);
   check([id ' ' names{j} ' safe'],all(z.peak<h.limit-h.band));
   check([id ' ' names{j} ' cold sufficient bound'],all(z.peak<=44.682809+1e-6));
   lb=independent_lb(c);
   if j==2 && contains(id,'D6')
    check([id ' D6 no-low certificate'],tight_certificate(cR,raw));
    lb=independent_lb(cI);proof='D6 analytic frequency exclusion plus attainable bound';
   else,proof='additive mode lower bound';end
   if j~=3,check([id ' ' names{j} ' bound attained'],abs(energy-lb)<1e-10);else,lb=NaN;proof='replay; no independent optimality claim';end
   elapsed=toc(timer);check([id ' ' names{j} ' verification budget'],elapsed<60);
   rr=struct('case_id',id,'evaluation',names{j},'energy_mJ',energy*1000,'lower_mJ',lb*1000, ...
    'completion_A_ms',s.finish(4)*1000,'completion_B_ms',s.finish(8)*1000,'peak_CPU_C',z.peak(1),'peak_NPU_C',z.peak(2), ...
    'terminal_CPU_C',z.terminal(1),'terminal_NPU_C',z.terminal(2),'ode_error_C',z.ode_error,'elapsed_s',elapsed,'safe',true,'proof',proof,'complete_optimal_set',false);
   if isempty(results),results=rr;else,results(end+1)=rr;end %#ok<AGROW>
   ss=struct('case_id',id,'evaluation',names{j},'schedule',s,'trace',z);
   if isempty(schedules),schedules=ss;else,schedules(end+1)=ss;end %#ok<AGROW>
  end
  expected=protocol.expected_energy_mJ.(id);
  check([id ' frozen expected check'],max(abs([energy_direct(cR,replay) energy_direct(cR,sR)]*1000-expected(:)'))<1e-8);
  check([id ' fixed-start replay'],isequal(sI.unit,replay.unit)&&isequal(sI.mode,replay.mode)&&isequal(sI.start,replay.start));
 end
 % Fixtures are checker tests, not additional research cases.
 c=cR;s=sR;
 bad=s;bad.start(8)=bad.start(8)+0.0002;bad.finish(8)=bad.finish(8)+0.0002;
 check('fixture off-grid rejected',~independent_check(c,bad));
 bad=s;bad.unit(2)=3;check('fixture unsupported response mismatch',~independent_check(c,bad));
 bad=s;bad.start(3)=0;bad.finish(3)=bad.duration(3);check('fixture precedence rejected',~independent_check(c,bad));
 bad=s;bad.unit(5)=1;bad.choice(5)=find(c.options{5}(:,1)==1 & c.options{5}(:,2)==bad.mode(5));check('fixture CPU overlap rejected',~independent_check(c,bad));
 % Same frequency legal concurrency is already covered by the wide witnesses.
 bad=fromspec(c,[1 1 1 1 2 2 2 2],[2 1 2 1 2 2 2 1],[0 1 4 6 0 1 4 6]/1000);
 check('fixture domain conflict rejected',~independent_check(c,bad));
 cp=c;cp.deadline(:)=0.004;check('fixture impossible deadline rejected',~independent_check(cp,s));
 bad=s;bad.start(8)=NaN;check('fixture incomplete rejected',~independent_check(c,bad));
 cAlpha=c;for i=1:8,hh=c.options{i}(find(c.options{i}(:,1)==1 & c.options{i}(:,2)==2,1),3);for j=1:size(c.options{i},1),if c.options{i}(j,1)<3,x=raw.cpu_frequencies(c.options{i}(j,2)).ratio_to_reference;cAlpha.options{i}(j,3)=hh/x;end,end,end
 check('fixture alpha1 identity',isequal(cAlpha.options,cI.options));
 check('fixture equal S1 high/N energy',abs(c.options{2}(2,3)*c.options{2}(2,4)-c.options{2}(5,3)*c.options{2}(5,4))<1e-12);
 % Shortening a nonselected low mode can change prediction without changing a fixed choice.
 unchanged=fromspec(cI,sI.unit,sI.mode,sI.start);check('fixture same H choice replay energy',abs(energy_direct(cI,unchanged)-energy_direct(cR,replay))<1e-12 && any(cI.options{4}(:,3)~=cR.options{4}(:,3)));
 % No solver is used: a partial certificate is deliberately never upgraded.
 check('fixture witness alone is not optimum',~certificate_status(true,false,false));
 check('fixture unresolved not proof',~certificate_status(true,true,true));
 check('fixture interrupted bound not proof',~certificate_status(false,true,false));
 check('source unchanged',isequal(hashes,c44_audit(paths)));
 writetable(struct2table(results),fullfile(folder,'summary.csv'));
 writetable(struct2table(checks),fullfile(folder,'checks.csv'));
 writejson(fullfile(folder,'results.json'),results);writejson(fullfile(folder,'schedules.json'),schedules);
 save(fullfile(folder,'verification.mat'),'results','schedules','checks','environment','protocol','rules');
 fprintf('CHECKS %d/%d\nOUTPUT %s\n',sum([checks.passed]),numel(checks),folder);
 assert(all([checks.passed]),'c60:checks','Check failure; see preserved outputs');
catch err
 writejson(fullfile(folder,'checks_failed.json'),checks);fid=fopen(fullfile(folder,'failure.txt'),'w');fprintf(fid,'%s',getReport(err,'extended'));fclose(fid);rethrow(err);
end
 function check(name,passed),checks(end+1)=struct('name',name,'passed',logical(passed));if ~passed,fprintf('FAIL %s\n',name);end,end
end

function c=inverse(c,raw)
for i=1:c.n
 a=raw.cpu_response.parameters(mod(i-1,4)+1);
 for j=1:size(c.options{i},1)
  if c.options{i}(j,1)<3,x=raw.cpu_frequencies(c.options{i}(j,2)).ratio_to_reference;c.options{i}(j,3)=a.reference_duration_s/x;end
 end
end
end
function s=fromspec(c,unit,mode,start)
unit=unit(:)';mode=mode(:)';start=start(:)';choice=zeros(1,8);
for i=1:8,choice(i)=find(c.options{i}(:,1)==unit(i)&c.options{i}(:,2)==mode(i));end
s=s55_schedule(c,[choice start/c.grid]);
end
function yes=independent_check(c,s)
yes=false;epsT=1e-9;
if any(~isfinite([s.start s.finish s.duration s.unit s.mode])) || numel(s.start)~=8,return;end
for i=1:8
 rows=c.options{i};hit=find(rows(:,1)==s.unit(i)&rows(:,2)==s.mode(i));
 if numel(hit)~=1 || abs(rows(hit,3)-s.duration(i))>epsT || abs(rows(hit,4)-s.increment(i))>1e-12,return;end
 if abs(s.finish(i)-s.start(i)-s.duration(i))>epsT || s.start(i)<c.release(c.request(i))-epsT || s.finish(i)>min(c.window,c.deadline(c.request(i)))+epsT,return;end
 if abs(s.start(i)/c.grid-round(s.start(i)/c.grid))>epsT/c.grid,return;end
 if mod(i-1,4)>0 && s.start(i)<s.finish(i-1)-epsT,return;end
end
ev=unique([0 c.window s.start s.finish]);
for k=1:numel(ev)-1
 t=(ev(k)+ev(k+1))/2;active=find(s.start<=t & s.finish>t);u=s.unit(active);
 if numel(unique(u))~=numel(u),return;end
 cpu=active(u<3);if numel(unique(s.mode(cpu)))>1,return;end
end
yes=true;
end
function e=energy_direct(c,s)
e=(c.idle_cpu+c.idle_npu+c.external)*c.window+dot(s.finish-s.start,s.increment);
end
function lb=independent_lb(c)
lb=(c.idle_cpu+c.idle_npu+c.external)*c.window;
for i=1:8,o=c.options{i};lb=lb+min(o(:,3).*o(:,4));end
end
function valid=tight_certificate(c,raw)
% Restricted analytic proof, NOT a general lower-bound routine.
% S2-L/S1-CPU-L exceed the isolated chain deadline. S0-L must start at
% zero and use N next, which blocks all ways for the other chain to finish.
% S3-L must start at 4 ms; the other chain needs CPU-H over 3--5 ms.
get=@(i,u,m)c.options{i}(find(c.options{i}(:,1)==u&c.options{i}(:,2)==m,1),3);
h0=get(1,1,2);l0=get(1,1,1);h1=get(2,1,2);l1=get(2,1,1);n1=get(2,3,3);
h2=get(3,1,2);l2=get(3,1,1);h3=get(4,1,2);l3=get(4,1,1);D=c.deadline(1);g=c.grid;
eq=@(a,b)abs(a-b)<1e-10;
valid=c.n==8 && all(c.release==0) && all(c.deadline==D) && eq(D,0.006) && eq(g,0.001) && isequal(c.domain,[1 1 0]);
valid=valid && h0+n1+l2+h3>D && h0+l1+h2+h3>D;
valid=valid && eq(l0+n1+h2+h3,D) && l0+h0+n1+h2+h3>D && l0+2*n1+h2+h3>D;
earliest=h0+n1+h2;latest=floor((D-l3+1e-12)/g)*g;
otherStart=h0+min(h1,2*n1);otherEnd=otherStart+h2;
valid=valid && eq(earliest,latest) && eq(otherEnd+h3,D) && otherStart<earliest+l3 && otherEnd>earliest;
valid=valid && isequal([raw.cpu_response.parameters.alpha],[1 .5 1 .25]);
end
function z=symmetric_thermal(c,s,h)
% Independent common/differential modal formula, not eig/thv_step.
assert(abs(diff(h.capacity))<1e-15 && abs(diff(h.g_env))<1e-15);
C=h.capacity(1);g0=h.g_env(1);g=h.g;lam=[g0/C (g0+2*g)/C];
G=[g0+g -g;-g g0+g];theta=h.initial(:)-h.ambient;
ev=unique([0 c.window s.start s.finish]);peak=theta;times=[0;0];odeError=0;states=theta';
for k=1:numel(ev)-1
 dt=ev(k+1)-ev(k);mid=(ev(k+1)+ev(k))/2;on=s.start<=mid & mid<s.finish;
 p=[c.idle_cpu+sum(s.increment(on&s.unit<3));c.idle_npu+sum(s.increment(on&s.unit==3))];
 aeq=sum(p)/(2*g0);beq=(p(1)-p(2))/(2*(g0+2*g));
 a=sum(theta)/2-aeq;b=(theta(1)-theta(2))/2-beq;
 value=@(t)[aeq+beq+a*exp(-lam(1)*t)+b*exp(-lam(2)*t);aeq-beq+a*exp(-lam(1)*t)-b*exp(-lam(2)*t)];
 candidates=[0 dt];
 for node=1:2
  bb=b*(3-2*node);if a*bb<0,r=log(-lam(2)*bb/(lam(1)*a))/(lam(2)-lam(1));if r>0&&r<dt,candidates(end+1)=r;end,end %#ok<AGROW>
 end
 sol=ode45(@(~,y)(p-G*y)/C,[0 dt],theta,odeset('RelTol',1e-11,'AbsTol',1e-12));
 t=unique([linspace(0,dt,33) candidates]);direct=value(t);numeric=deval(sol,t);odeError=max(odeError,max(abs(direct(:)-numeric(:))));
 pv=value(candidates);[pk,idx]=max(pv,[],2);hit=pk>peak;peak(hit)=pk(hit);ct=candidates(idx);times(hit)=ev(k)+ct(hit);
 theta=value(dt);states(end+1,:)=theta'; %#ok<AGROW>
end
z=struct('peak',peak'+h.ambient,'peak_time',times','terminal',theta'+h.ambient,'ode_error',odeError,'event_time',ev,'event_temperature',states+h.ambient);
end
function yes=certificate_status(complete,attained,unresolved),yes=complete&&attained&&~unresolved;end
function writejson(p,x),fid=fopen(p,'w','n','UTF-8');assert(fid>=0);g=onCleanup(@()fclose(fid));fprintf(fid,'%s',jsonencode(x,'PrettyPrint',true));end
