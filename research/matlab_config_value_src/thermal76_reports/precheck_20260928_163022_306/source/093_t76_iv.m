function z=t76_iv(op,a,b)
% Outward intervals; finite IEEE binary64 normal-range operations only.
% Inputs/outputs are N-by-2; scalar rows expand.  Eight ulps cover each
% rounded elementary operation plus rounding of the outward endpoint.
switch op
 case 'point',z=[a(:) a(:)];
 case 'wide',z=pad([a(:) a(:)]);
 case 'add',z=pad([a(:,1)+b(:,1) a(:,2)+b(:,2)]);
 case 'sub',z=t76_iv('add',a,[-b(:,2) -b(:,1)]);
 case 'mul'
  v=[a(:,1).*b(:,1) a(:,1).*b(:,2) a(:,2).*b(:,1) a(:,2).*b(:,2)];
  z=pad([min(v,[],2) max(v,[],2)]);
 case 'div'
  assert(all(b(:,1)>0));z=t76_iv('mul',a,pad([1./b(:,2) 1./b(:,1)]));
 case 'nonnegative',z=max(0,a); % justified only for physically nonnegative quantities
 case 'expneg'
  assert(all(a(:,1)>=0 & a(:,2)<=1),'t76:expdomain','Exponential domain is [0,1]');
  term=repmat([1 1],size(a,1),1);z=term;
  for k=1:32
   term=t76_iv('div',t76_iv('mul',term,[-a(:,2) -a(:,1)]),[k k]);
   z=t76_iv('add',z,term);
  end
  rem=repmat([1 1],size(a,1),1);
  for k=1:33,rem=t76_iv('div',t76_iv('mul',rem,[zeros(size(a,1),1) a(:,2)]),[k k]);end
  z=t76_iv('add',z,[-rem(:,2) rem(:,2)]);z=[max(0,z(:,1)) min(1,z(:,2))];
 case 'sum'
  z=[0 0];for k=1:size(a,1),z=t76_iv('add',z,a(k,:));end
 otherwise,error('t76:interval','Unknown operation');
end
assert(all(isfinite(z),'all') && all(z(:,1)<=z(:,2)));
end
function z=pad(z)
assert(all(isfinite(z),'all') && all(abs(z)<1e100,'all'));
e=8*eps(max(1,max(abs(z),[],2)));z=[z(:,1)-e z(:,2)+e];
end
