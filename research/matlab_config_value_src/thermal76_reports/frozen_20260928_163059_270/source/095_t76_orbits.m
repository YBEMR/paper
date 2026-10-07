function [orbit,keys]=t76_orbits(c,rows)
% Only one global C1/C2 label permutation, never arbitrary remapping.
rows=double(rows);swapped=rows;
for j=1:size(rows,1)
 for i=1:c.n
  o=c.options{i}(rows(j,i),:);
  if o(1)<=2
   k=find(c.options{i}(:,1)==3-o(1) & c.options{i}(:,2)==o(2));assert(numel(k)==1);
   assert(isequal(c.options{i}(k,3:4),o(3:4)));swapped(j,i)=k;
  end
 end
end
keys=rows;
for j=1:size(rows,1)
 k=find(rows(j,:)~=swapped(j,:),1);if ~isempty(k) && swapped(j,k)<rows(j,k),keys(j,:)=swapped(j,:);end
end
[~,~,orbit]=unique(keys,'rows');
end
