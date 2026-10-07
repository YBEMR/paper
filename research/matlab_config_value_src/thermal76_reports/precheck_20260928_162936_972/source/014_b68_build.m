function p=b68_build(c,check)
% Stage/mode/start columns; exact integer coefficients, no schedule library.
if nargin<2,check=@()[];end
d=b64_data(c);o=zeros(0,7);groups=cell(1,c.n);
for i=1:c.n
 check();first=size(o,1)+1;
 for m=1:size(c.options{i},1)
  lo=d.g*ceil(d.a(c.request(i))/d.g);hi=min(d.dead(c.request(i)),d.w)-d.dt{i}(m);
  for t=lo:d.g:hi
   o(end+1,:)=[i m t t+d.dt{i}(m) c.options{i}(m,1:2) d.en{i}(m)]; %#ok<AGROW>
  end
 end
 groups{i}=first:size(o,1);
end
n=size(o,1);eq=sparse(o(:,1),(1:n)',ones(n,1),c.n,n);
rr=[];cc=[];vv=[];b=[];row=0;
for j=1:c.n
 for i=c.pred{j}
  row=row+1;a=groups{i};z=groups{j};
  rr=[rr repmat(row,1,numel(a)+numel(z))];cc=[cc a z];vv=[vv o(a,4)' -o(z,3)'];b(row,1)=0; %#ok<AGROW>
 end
end
for a=1:n
 check();z=find(o(:,1)>o(a,1) & o(:,3)<o(a,4) & o(:,4)>o(a,3));
 for j=z'
  conflict=o(a,5)==o(j,5);
  if c.unit_kind(o(a,5))==1 && c.unit_kind(o(j,5))==1
   conflict=conflict || (c.domain(o(a,5))==c.domain(o(j,5)) && o(a,6)~=o(j,6));
  end
  if conflict
   row=row+1;rr=[rr row row];cc=[cc a j];vv=[vv 1 1];b(row,1)=1; %#ok<AGROW>
  end
 end
end
p=struct('columns',o,'groups',{groups},'A',sparse(rr,cc,vv,row,n),'b',b, ...
 'Aeq',eq,'beq',ones(c.n,1),'f',o(:,7),'d',d,'L0',d.base+sum(d.minE), ...
 'empty_stage',any(cellfun(@isempty,groups)));
check();
end
