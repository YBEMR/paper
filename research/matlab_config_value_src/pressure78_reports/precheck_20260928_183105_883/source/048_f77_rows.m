function out=f77_rows(rows,selected,check)
% Current thermal rows are NEVER included in b68_decode's integer matrix.
if nargin<3,check=@()[];end
n=numel(rows);status=repmat({'satisfied'},n,1);intervals=zeros(n,2);
for j=1:n
 check();row=rows{j};v=t76_point(row,selected);intervals(j,:)=v;
 if v(1)>row.rhs_upper,status{j}='violated';
 elseif v(2)>row.rhs_upper,status{j}='unresolved';end
end
check();out=struct('status',{status},'lhs_intervals',intervals, ...
 'violated',find(strcmp(status,'violated'))','unresolved',find(strcmp(status,'unresolved'))');
end
