function z=audit_validate(p,a,selected,sub)
% Independent power construction and RC replay, no thermal catalog used.
if nargin<4,sub=200;end
z=struct('ok',false,'energy',NaN,'peak',NaN,'reason','incomplete','badTimes',[]);
if numel(selected)~=p.n || any(selected<1),return;end
v=a.v(selected,:);H=p.cfg.H_ms;
if ~isequal(sort(v(:,1))',(1:p.n)),z.reason='stage';return;end
[~,idx]=sort(v(:,1));v=v(idx,:);s=v(:,6);f=s+v(:,4);
if any(s<p.release' | f>p.deadline' | f>H | s~=round(s)),z.reason='time';return;end
for e=p.edges'
 if f(e(1))>s(e(2)),z.reason='dependency';return;end
end
Q=repmat(p.idle,H,1);occ=false(H,3);
for j=1:p.n
 r=v(j,2);ii=s(j)+1:f(j);
 if any(occ(ii,r)),z.reason='resource';return;end
 occ(ii,r)=true;Q(ii,r)=v(j,5);
end
z.energy=sum(Q(:));x=repmat(p.cfg.T0-p.cfg.T_amb,3,1);z.peak=p.cfg.T0;
step=expm(p.th.A*.001/sub);bad=[];
for t=1:H
 ss=p.th.Ginv*Q(t,:)';
 for k=1:sub
  x=ss+step*(x-ss);T=max(x+p.cfg.T_amb);z.peak=max(z.peak,T);
  if T>p.cfg.T_lim+1e-7,bad(end+1)=(t-1)+k/sub;end %#ok<AGROW>
 end
end
z.badTimes=bad;z.ok=z.peak<=p.cfg.T_lim+1e-7;z.reason='ok';if ~z.ok,z.reason='thermal';end
end
