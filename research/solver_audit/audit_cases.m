function cases=audit_cases()
% Declared set: 15 legacy + 12 structural + 6 thermal ablations.
ids=[8 17 35 9 18 36 1 4 7 13 16 22 25 31 34]; cases={};
for id=ids
 c=base(); releases=[0 0;0 5;5 0;0 10]; deadlines=[18 22;20 24;24 28]; ts=[45 60 70];
 a=floor((id-1)/9)+1;b=floor(mod(id-1,9)/3)+1;k=mod(id-1,3)+1;
 c.H_ms=28;c.rA_ms=releases(a,1);c.rB_ms=releases(a,2);
 c.D_A_ms=deadlines(b,1);c.D_B_ms=deadlines(b,2);c.T0=ts(k);
 p=make(c,2,'independent'); p.id=sprintf('old%02d',id);p.legacy=id;
 p.release=[c.rA_ms c.rB_ms c.rA_ms c.rB_ms];
 p.deadline=[c.D_A_ms c.D_B_ms c.D_A_ms c.D_B_ms];
 cases{end+1}=p; %#ok<AGROW>
end
for n=[3 4]
 for shape={'independent','barrier','serial'}
  for T=[45 60]
   c=base();c.H_ms=14*n;c.T0=T;
   p=make(c,n,shape{1}); p.id=sprintf('new%d_%s_T%d',n,shape{1},T);
   cases{end+1}=p; %#ok<AGROW>
  end
 end
end
original=cases;
for k=16:numel(original)
 if original{k}.cfg.T0~=60,continue;end
 p=original{k};p.cfg.T_lim=200;p.id=[p.id '_noheat'];cases{end+1}=p; %#ok<AGROW>
end
end
function c=base()
c=config_default();c.P_A1=c.P_A1*1.6;c.P_B1=c.P_B1*1.6;
c.P_A2=c.P_A2*1.6;c.P_B2=c.P_B2*1.6;c.C=c.C*.25;
end
function p=make(c,n,shape)
p=struct('id','','legacy',0,'cfg',c,'n',2*n,'requests',n,'shape',shape);
p.release=zeros(1,2*n);p.deadline=zeros(1,2*n);p.modes=cell(1,2*n);p.edges=zeros(0,2);
for j=1:n
 if mod(j,2),d=c.d_A1_ms;pw=c.P_A1;dn=c.d_A2_ms;pn=c.P_A2;D=c.H_ms-4;
 else,d=c.d_B1_ms;pw=c.P_B1;dn=c.d_B2_ms;pn=c.P_B2;D=c.H_ms;end
 % mode columns = resource, frequency, duration(ms), power(W)
 p.modes{j}=[1 1 d(1) pw(1);1 2 d(2) pw(2);2 1 d(1) pw(1);2 2 d(2) pw(2)];
 p.modes{n+j}=[3 1 dn pn];p.deadline([j n+j])=D;
 p.edges(end+1,:)=[j n+j]; %#ok<AGROW>
end
if strcmp(shape,'barrier')
 [a,b]=ndgrid(1:n,n+1:2*n);p.edges=unique([p.edges;a(:) b(:)],'rows');
elseif strcmp(shape,'serial')
 p.edges=[p.edges; (n+1:2*n-1)' (2:n)'];
end
p.th=thermal_build(c);p.idle=[c.P_idle_C c.P_idle_C c.P_idle_N];
p.minDuration=cellfun(@(m)min(m(:,3)),p.modes);
p.energyLB=sum(p.idle)*c.H_ms;
for j=1:p.n
 m=p.modes{j};p.energyLB=p.energyLB+min((m(:,4)-p.idle(m(:,1))').*m(:,3));
end
end
