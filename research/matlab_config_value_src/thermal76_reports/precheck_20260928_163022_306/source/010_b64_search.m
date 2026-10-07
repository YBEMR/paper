function out=b64_search(tr,variant,inject)
% Bounded three-layer search. No reference inputs or candidate library.
clock=tic;if nargin<3,inject=struct();end
c=tr.case;h=tr.thermal;budget=c.budget_s;
ordered=ismember(variant,{'full','no_repair'});repair=ismember(variant,{'full','simple_order'});
assert(ismember(variant,{'full','no_repair','simple_order','bare'}));
d=b64_data(c);root=b64_root(d);rootLower=root.lb;
stats=struct('popped',0,'generated',0,'noheat_pruned',0,'thermal_pruned',0,'energy_pruned',0, ...
 'config_closed',0,'thermal_calls',0,'cache_hits',0,'repair_trials',0,'repair_safe',0,'leaves',0, ...
 'probe_safe',0,'unresolved_leaves',0,'max_queue',0);
cost=struct('generation',0,'scoring',0,'queue',0,'thermal',0,'repair',0,'validation',0);
heap={};keys=zeros(0,4);hn=0;active=root;buffer={};Z={};seq=0;U=Inf;best=[];first=NaN;
cache=containers.Map('KeyType','char','ValueType','any');safeConfigs=containers.Map('KeyType','char','ValueType','logical');
events=zeros(0,6);trace=zeros(0,4);repairs={};status='running';message='';coverage=true;
try
 check('input');[root,ok]=score(root);if ok,push(root);else,stats.noheat_pruned=1;end;active=[];
 while hn>0
  check('loop');L=bound();trace(end+1,:)=[toc(clock),L,U,hn]; %#ok<AGROW>
  if isfinite(U) && L>=U,status='optimal';break;end
  active=pop();stats.popped=stats.popped+1;N=active;
  check('popped');
  if N.lb>=U,close('energy');continue;end
  mk=sprintf('%d,',N.m);
  if all(N.m>0) && isKey(safeConfigs,mk),close('config');continue;end
  if N.phase==3 && any(isfinite(N.s))
   z=thermal(N.m,N.s);check('committed_heat');
   if strcmp(z.status,'violation'),close('thermal');continue;end
  end
  if N.phase==3 && ~N.probed
   [ok,t]=b64_propagate(d,N);assert(ok);z=thermal(N.m,t);
   if strcmp(z.status,'safe'),accept(N.m,t,'probe');active=[];continue;end
   if strcmp(z.status,'violation') && repair
    timer=tic;[rr,targets,weights]=b64_repair(d,N,t,z,h);cost.repair=cost.repair+toc(timer);check('repair_construct');
    found=false;
    for j=1:numel(rr)
     stats.repair_trials=stats.repair_trials+1;
     if isempty(rr{j}),st='deadline';else,q=thermal(N.m,rr{j});st=q.status;end
     repairs{end+1}=struct('node',N.id,'target',targets(j),'contribution',weights(targets(j)), ...
       'status',st,'start_units',rr{j}); %#ok<AGROW>
     check('repair_evaluated');
     if strcmp(st,'safe'),accept(N.m,rr{j},'repair');found=true;break;end
    end
    if found,active=[];continue;end
   end
   N.probed=true;active=N;
  end
  if N.phase==3 && all(isfinite(N.s))
   stats.leaves=stats.leaves+1;z=thermal(N.m,N.s);check('leaf');
   if strcmp(z.status,'safe'),accept(N.m,N.s,'leaf');
   elseif strcmp(z.status,'unresolved'),Z{end+1}=N;stats.unresolved_leaves=stats.unresolved_leaves+1;
   else,stats.thermal_pruned=stats.thermal_pruned+1;end
   active=[];continue;
  end
  timer=tic;children=b64_expand(d,N);cost.generation=cost.generation+toc(timer);check('expand');
  buffer={};
  for j=1:numel(children)
   [C,ok]=score(children{j});stats.generated=stats.generated+1;check('child');
   if ~ok,stats.noheat_pruned=stats.noheat_pruned+1;record(C,1);
   elseif C.lb>=U,stats.energy_pruned=stats.energy_pruned+1;record(C,2);
   else,buffer{end+1}=C;end %#ok<AGROW>
  end
  % Parent stays active until all children are validated and inserted.
  % Interrupted commit may retain duplicates, never loses parent coverage.
  check('commit');for j=1:numel(buffer),push(buffer{j});end
  active=[];buffer={};check('committed');
 end
 if strcmp(status,'running')
  if isfinite(U) && bound()>=U,status='optimal';
  elseif isempty(Z) && hn==0 && isempty(active),status='grid_infeasible';
  else,status='numeric_unresolved';end
 end
catch err
 if strcmp(err.identifier,'b64:timeout'),status='timeout';
 elseif strcmp(err.identifier,'b64:resource') || contains(lower(err.message),'out of memory'),status='resource_unresolved';coverage=false;
 else,status='error';coverage=false;end
 message=getReport(err,'extended','hyperlinks','off');
end
elapsed=toc(clock);L=bound();if ~coverage,L=rootLower;end
trace(end+1,:)=[elapsed,L,U,hn];
out=struct('input_id',c.id,'method',variant,'status',status,'message',message, ...
 'schedule',best,'lower_J',L*d.energy_unit,'upper_J',U*d.energy_unit, ...
 'optimal_value_proved',strcmp(status,'optimal'),'grid_infeasible_proved',strcmp(status,'grid_infeasible'), ...
 'optimal_set_complete',false,'coverage_valid',coverage,'elapsed_s',elapsed,'first_safe_s',first, ...
 'stats',stats,'cost_s',cost,'bound_trace',trace,'events',events,'repair_log',{repairs}, ...
 'queue',{heap(1:hn)},'active',active,'unresolved',{Z},'buffer',{buffer}, ...
 'proof_scope','frozen_start_grid_exact_energy_and_outward_thermal_enclosure');
    function check(phase)
     if isfield(inject,'phase') && strcmp(inject.phase,phase)
      id='b64:timeout';if isfield(inject,'identifier'),id=inject.identifier;end
      error(id,'Injected interruption at %s',phase);
     end
     if toc(clock)>budget,error('b64:timeout','Budget exhausted at %s',phase);end
    end
    function [C,ok]=score(C)
     timer=tic;C.lb=d.base;for k=1:d.n
      if C.m(k)>0,C.lb=C.lb+d.en{k}(C.m(k));else,C.lb=C.lb+d.minE(k);end
     end
     [ok,~,fin]=b64_propagate(d,C);C.score=Inf;if ok,C.score=sum(fin(d.terminal));end
     C.fixed=sum(C.m>0)+C.pos-1+sum(isfinite(C.s));seq=seq+1;C.id=seq;
     cost.scoring=cost.scoring+toc(timer);
    end
    function push(C)
     timer=tic;hn=hn+1;heap{hn}=C;
     if ordered,key=[C.lb C.score -C.fixed C.id];else,key=[C.lb 0 0 C.id];end
     keys(hn,:)=key;j=hn;
     while j>1
      p=floor(j/2);if ~less(keys(j,:),keys(p,:)),break;end
      tmp=heap{p};heap{p}=heap{j};heap{j}=tmp;tmp=keys(p,:);keys(p,:)=keys(j,:);keys(j,:)=tmp;j=p;
     end
     stats.max_queue=max(stats.max_queue,hn);cost.queue=cost.queue+toc(timer);
    end
    function N=pop()
     timer=tic;N=heap{1};heap{1}=heap{hn};keys(1,:)=keys(hn,:);heap(hn)=[];keys(hn,:)=[];hn=hn-1;j=1;
     while 2*j<=hn
      p=2*j;if p<hn && less(keys(p+1,:),keys(p,:)),p=p+1;end
      if ~less(keys(p,:),keys(j,:)),break;end
      tmp=heap{p};heap{p}=heap{j};heap{j}=tmp;tmp=keys(p,:);keys(p,:)=keys(j,:);keys(j,:)=tmp;j=p;
     end
     cost.queue=cost.queue+toc(timer);
    end
    function L=bound()
     L=U;if hn>0,L=min(L,keys(1,1));end
     if ~isempty(active),L=min(L,active.lb);end
     for k=1:numel(Z),L=min(L,Z{k}.lb);end
    end
    function z=thermal(m,t)
     check('thermal_before');timer=tic;ck=sprintf('%d,',[m t]);
     if isKey(cache,ck),z=cache(ck);stats.cache_hits=stats.cache_hits+1;
     else
      s=b64_schedule(d,m,t);z=b64_thermal(c,s,h);stats.thermal_calls=stats.thermal_calls+1;
      check('thermal_after');cache(ck)=z;
     end
     cost.thermal=cost.thermal+toc(timer);check('thermal_return');
    end
    function accept(m,t,kind)
     timer=tic;s=b64_schedule(d,m,t);v=s55_validate(c,s);assert(v.feasible,v.reason);
     e=s55_energy(c,s);assert(e.error_J<=max(c.energy_abs_tol,c.energy_rel_tol*abs(e.sum_J)));
     z=b64_thermal(c,s,h);assert(strcmp(z.status,'safe'));
     cost.validation=cost.validation+toc(timer);check('accept');
     val=d.base;for k=1:d.n,val=val+d.en{k}(m(k));end
     safeConfigs(sprintf('%d,',m))=true;
     if val<U,U=val;best=s;if isnan(first),first=toc(clock);end;end
     if strcmp(kind,'repair'),stats.repair_safe=stats.repair_safe+1;
     elseif strcmp(kind,'probe'),stats.probe_safe=stats.probe_safe+1;end
     events(end+1,:)=[toc(clock) active.id 5 val hn seq];
    end
    function record(N,code),events(end+1,:)=[toc(clock) N.id code N.lb hn seq];end
    function close(kind)
     switch kind
      case 'energy',stats.energy_pruned=stats.energy_pruned+1;code=2;
      case 'config',stats.config_closed=stats.config_closed+1;code=3;
      case 'thermal',stats.thermal_pruned=stats.thermal_pruned+1;code=4;
     end
     record(active,code);active=[];
    end
end
function yes=less(a,b),k=find(a~=b,1);yes=~isempty(k) && a(k)<b(k);end
