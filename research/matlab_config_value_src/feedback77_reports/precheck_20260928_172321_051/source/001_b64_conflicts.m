function pairs=b64_conflicts(d,m)
pairs=zeros(0,2);
for i=1:d.n
 a=d.options{i}(m(i),:);
 for j=i+1:d.n
  b=d.options{j}(m(j),:);u=a(1);v=b(1);
  if u==v || (d.unit_kind(u)==1 && d.unit_kind(v)==1 && d.domain(u)==d.domain(v) && a(2)~=b(2))
   pairs(end+1,:)=[i j]; %#ok<AGROW>
  end
 end
end
end
