function [R,b]=audit_thermal_rows(p,a,times)
% Linear superposition from zero additional power; time-major/node-minor rows.
times=times(:);v=a.v;nt=numel(times);nv=size(v,1);R=zeros(3*nt,nv);b=zeros(3*nt,1);
x0=repmat(p.cfg.T0-p.cfg.T_amb,3,1);ss=p.th.Ginv*p.idle';
for i=1:nt
 E=expm(p.th.A*times(i)*.001);b(3*i-2:3*i)=p.cfg.T_amb+ss+E*(x0-ss);
end
% Cache impulse response at multiples of the finest evaluation grid.
K=round(p.cfg.H_ms*200);step=expm(p.th.A*.000005);Es=zeros(3,3,K+1);Es(:,:,1)=eye(3);
for k=1:K,Es(:,:,k+1)=step*Es(:,:,k);end
for k=1:nv
 r=v(k,2);s=v(k,6);d=v(k,4);dp=v(k,5)-p.idle(r);g=p.th.Ginv(:,r)*dp;
 active=find(times>s);
 for i=active'
  u=times(i)-s;E1=Es(:,:,round(u*200)+1);
  if u<=d,R(3*i-2:3*i,k)=(eye(3)-E1)*g;
  else,E0=Es(:,:,round((u-d)*200)+1);R(3*i-2:3*i,k)=(E0-E1)*g;end
 end
end
R=sparse(R);
end
