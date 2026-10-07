function ids=t76_option_ids(c,columns,rows)
ids=zeros(size(rows,1),c.n);d=b64_data(c);
for j=1:size(rows,1)
 for i=1:c.n
  k=find(columns(:,1)==i & columns(:,2)==double(rows(j,i)) & columns(:,3)==double(rows(j,c.n+i))*d.g);
  assert(numel(k)==1,'t76:option','Each selected option must have exactly one column');ids(j,i)=k;
 end
end
end
