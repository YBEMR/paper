function a=audit_catalog(p)
% Enumerate per-task placements, not joint schedules. Necessary DAG bounds.
H=p.cfg.H_ms;n=p.n;es=p.release;lf=min(p.deadline,H);
for it=1:n
 for e=p.edges'
  es(e(2))=max(es(e(2)),es(e(1))+p.minDuration(e(1)));
  lf(e(1))=min(lf(e(1)),lf(e(2))-p.minDuration(e(2)));
 end
end
v=zeros(0,7); % stage, resource, frequency, duration, power, start, delta energy
for j=1:n
 for m=p.modes{j}'
  for s=es(j):lf(j)-m(3)
   v(end+1,:)=[j m(1) m(2) m(3) m(4) s (m(4)-p.idle(m(1)))*m(3)]; %#ok<AGROW>
  end
 end
end
a.v=v;nv=size(v,1);a.byStage=cell(1,n);
for j=1:n,a.byStage{j}=find(v(:,1)==j);end
a.energy=v(:,7);a.idleEnergy=sum(p.idle)*H;
ii=[];jj=[];vv=[];
for k=1:nv
 rows=(v(k,2)-1)*H+(v(k,6)+1:v(k,6)+v(k,4));
 ii=[ii rows];jj=[jj repmat(k,1,numel(rows))];vv=[vv ones(1,numel(rows))]; %#ok<AGROW>
end
a.occ=sparse(ii,jj,vv,3*H,nv);
a.eq=sparse(v(:,1),(1:nv)',ones(nv,1),n,nv);
a.dep=sparse(size(p.edges,1),nv);
for k=1:size(p.edges,1)
 u=a.byStage{p.edges(k,1)};w=a.byStage{p.edges(k,2)};
 a.dep(k,u)=v(u,6)+v(u,4);a.dep(k,w)=-v(w,6);
end
[a.R,a.base]=audit_thermal_rows(p,a,(.25:.25:H)');
end
