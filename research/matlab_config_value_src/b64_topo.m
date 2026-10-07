function [order,ok]=b64_topo(adj)
n=size(adj,1);left=true(1,n);order=zeros(1,n);ok=true;
for k=1:n
 ready=find(left & ~any(adj(left,:),1),1);
 if isempty(ready),ok=false;order=order(1:k-1);return;end
 order(k)=ready;left(ready)=false;
end
end
