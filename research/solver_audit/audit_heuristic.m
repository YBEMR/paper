function out=audit_heuristic(p,a,portfolio,clock0,budget)
% Fixed priority portfolio, optional single-stage feasible descent.
n=p.n;v=a.v;out=struct('selected',zeros(1,n),'energy',Inf,'attempts',0,'timeout',false);
[~,edf]=sort(p.deadline);[~,short]=sort(p.minDuration);[~,long]=sort(p.minDuration,'descend');
priorities=unique([(1:n);n:-1:1;edf;short;long],'rows','stable');
if ~portfolio,priorities=1:n;end
waits=Inf;if portfolio,waits=[Inf 0];end
for wait=waits
 for ip=1:size(priorities,1)
  sel=construct(priorities(ip,:),wait);out.attempts=out.attempts+1;
  if all(sel)
   val=audit_validate(p,a,sel);
   if val.ok && val.energy<out.energy,out.selected=sel;out.energy=val.energy;end
  end
  if out.energy<=p.energyLB+1e-7,return;end
  if toc(clock0)>=budget,out.timeout=true;return;end
 end
end
if ~portfolio || ~isfinite(out.energy),return;end
% Search all placements of one stage, holding the others fixed; no worsening.
changed=true;
while changed && toc(clock0)<budget
 changed=false;
 for j=1:n
  old=out.selected(j);others=out.selected;others(j)=[];
  used=sum(a.occ(:,others),2);T=a.base+sum(a.R(:,others),2);
  for k=a.byStage{j}'
   if v(k,7)>=v(old,7)-1e-8,continue;end
   if any(used+a.occ(:,k)>1) || any(T+a.R(:,k)>p.cfg.T_lim+1e-8),continue;end
   trial=out.selected;trial(j)=k;val=audit_validate(p,a,trial);
   if val.ok && val.energy<out.energy-1e-8
    out.selected=trial;out.energy=val.energy;changed=true;break;
   end
   if toc(clock0)>=budget,out.timeout=true;return;end
  end
  if out.energy<=p.energyLB+1e-7,return;end
 end
end
out.timeout=toc(clock0)>=budget;
    function sel=construct(priority,maxwait)
        sel=zeros(1,n);finish=inf(1,n);used=zeros(3*p.cfg.H_ms,1);T=a.base;
        for t=0:p.cfg.H_ms-1
            while true
                committed=false;
                for j=priority
                    if sel(j),continue;end
                    pred=p.edges(p.edges(:,2)==j,1);
                    if any(finish(pred)>t) || t<p.release(j),continue;end
                    ks=a.byStage{j};ks=ks(v(ks,6)>=t & v(ks,6)<=t+maxwait);
                    if isempty(ks),continue;end
                    ks=ks(~any(a.occ(:,ks)+used>1,1));
                    if isempty(ks),continue;end
                    peaks=full(max(a.R(:,ks)+T,[],1));good=peaks<=p.cfg.T_lim+1e-8;
                    ks=ks(good);peaks=peaks(good);
                    if isempty(ks),continue;end
                    key=[v(ks,7) v(ks,6) peaks' v(ks,2) v(ks,3)];
                    [~,order]=sortrows(key,1:5);k=ks(order(1));
                    if v(k,6)~=t,continue;end
                    sel(j)=k;finish(j)=t+v(k,4);used=used+a.occ(:,k);T=T+a.R(:,k);
                    committed=true;break;
                end
                if ~committed,break;end
                if toc(clock0)>=budget,return;end
            end
            if all(sel) || toc(clock0)>=budget,return;end
        end
    end
end
