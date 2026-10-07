function net = thv_build(h)
assert(all(h.capacity>0) && all(h.g_env>0) && h.g>=0);
C=diag(h.capacity); G=diag(h.g_env)+h.g*[1 -1;-1 1];
S=diag(sqrt(h.capacity)); invS=diag(1./sqrt(h.capacity));
[U,L]=eig(invS*G*invS); [lambda,order]=sort(diag(L)); U=U(:,order);
assert(all(lambda>0));
net=struct('C',C,'G',G,'A',-(C\G),'lambda',lambda, ...
    'V',invS*U,'Vi',U'*S,'tau',1./lambda);
end
