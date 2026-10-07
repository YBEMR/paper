function out=b64_thermal(c,s,h)
% Analytic extrema plus outward enclosures for the declared symmetric RC.
% Exact physical contract: C=1/400, g_env=1/20, coupling=1/40.
% Common/difference modes have EXACT rates 20 and 40 per second.
assert(all(h.capacity==.0025) && all(h.g_env==.05) && h.g==.025, ...
 'b64:thermal_domain','Certified enclosure is restricted to the frozen RC network');
v=s55_validate(c,s,true);assert(v.feasible,v.reason);
out=s55_thermal(c,s,h);known=isfinite(s.start);
ev=unique([0 c.window s.start(known) s.finish(known)]);
iv=@(x)[x x];cpu=sub(iv(h.initial(1)),iv(h.ambient));npu=sub(iv(h.initial(2)),iv(h.ambient));
M=mul(add(cpu,npu),iv(.5));D=mul(sub(cpu,npu),iv(.5));
pklo=h.initial;pkhi=h.initial;err=0;
for k=1:numel(ev)-1
 mid=(ev(k)+ev(k+1))/2;ix=find(known & s.start<=mid & mid<s.finish);
 pc=wide(c.idle_cpu);pn=wide(c.idle_npu);
 for i=ix
  if c.unit_kind(s.unit(i))==1,pc=add(pc,wide(s.increment(i)));else,pn=add(pn,wide(s.increment(i)));end
 end
 em=mul(iv(10),add(pc,pn));ed=mul(iv(5),sub(pc,pn));
 a=sub(M,em);b=sub(D,ed);
 % Binary input times enclosed before subtraction; covers decimal conversion.
 dt=sub(wide(ev(k+1)),wide(ev(k)));x=mul(iv(20),dt);z=exneg(x);z2=mul(z,z);
 for n=1:2
  sg=3-2*n;eq=add(em,mul(iv(sg),ed));bb=mul(iv(sg),b);
  q0=poly(eq,a,bb,iv(1));q1=poly(eq,a,bb,z);
  lo=max(q0(1),q1(1));hi=max(q0(2),q1(2));
  if bb(2)<0
   vertex=divide(neg(a),mul(iv(2),bb));vr=[max(vertex(1),z(1)) min(vertex(2),1)];
   if vr(1)<=vr(2),q=poly(eq,a,bb,vr);hi=max(hi,q(2));end
   % A fixed z strictly within [z_upper,1] is a physically reached time.
   t=min(1,max(z(2),mean(vertex)));q=poly(eq,a,bb,iv(t));lo=max(lo,q(1));
  elseif bb(1)<=0 && bb(2)>=0
   q=poly(eq,a,bb,[z(1) 1]);hi=max(hi,q(2));
  end
  pklo(n)=max(pklo(n),add(iv(h.ambient),iv(lo))*[1;0]);
  q=add(iv(h.ambient),iv(hi));pkhi(n)=max(pkhi(n),q(2));
 end
 M=add(em,mul(a,z));D=add(ed,mul(b,z2));
 err=max(err,max([M(2)-M(1),D(2)-D(1)]));
end
out.peak_lower=pklo;out.peak_upper=pkhi;out.enclosure_width=max(pkhi-pklo);
out.state_interval_width=err;out.enclosure_basis='symmetric_modes_quadratic_extrema_outward_IEEE754_Taylor24';
if any(pklo>h.limit+h.band),out.status='violation';
elseif all(pkhi<h.limit-h.band),out.status='safe';else,out.status='unresolved';end
% Nominal eig-based peak is diagnostic, never the pruning certificate.
end
function q=poly(e,a,b,z),q=add(e,add(mul(a,z),mul(b,mul(z,z))));end
function x=wide(v),x=pad([v v]);end
function c=add(a,b),c=pad([a(1)+b(1) a(2)+b(2)]);end
function c=neg(a),c=[-a(2) -a(1)];end
function c=sub(a,b),c=add(a,neg(b));end
function c=mul(a,b),v=[a(1)*b(1) a(1)*b(2) a(2)*b(1) a(2)*b(2)];c=pad([min(v) max(v)]);end
function c=divide(a,b)
assert(b(1)*b(2)>0);r=pad([1/b(2) 1/b(1)]);c=mul(a,r);
end
function c=pad(c)
% At least eight representable spacings outward; no overflow/subnormal use.
assert(all(isfinite(c)) && max(abs(c))<1e100);
e=8*eps(max(1,max(abs(c))));c=[c(1)-e c(2)+e];
end
function z=exneg(x)
% e^-x alternating Taylor, |remainder| <= x^25/25!, 0<=x<=0.5.
assert(x(1)>-1e-10 && x(2)<=.5);x(1)=max(0,x(1));
term=[1 1];z=term;
for k=1:24,term=divide(mul(term,neg(x)),[k k]);z=add(z,term);end
rem=[1 1];for k=1:25,rem=divide(mul(rem,[0 x(2)]),[k k]);end
z=add(z,[-rem(2) rem(2)]);z=[max(0,z(1)) min(1,z(2))];
end
