function r=t76_coefficients(c,h,columns,t,node)
% All option responses at ONE exact binary observation time. No schedule input.
assert(all(h.capacity==.0025) && all(h.g_env==.05) && h.g==.025,'t76:RC','Frozen symmetric RC only');
assert(t>=0 && t<=c.window && c.window<=.02 && ismember(node,[1 2]));
iv=@(x)t76_iv('point',x);wide=@(x)t76_iv('wide',x);
add=@(a,b)t76_iv('add',a,b);sub=@(a,b)t76_iv('sub',a,b);mul=@(a,b)t76_iv('mul',a,b);
ex=@(x)t76_iv('expneg',t76_iv('nonnegative',x));
% Baseline includes ambient and the continuously present CPU/NPU idle power.
mc=mul(iv(.5),sub(add(iv(h.initial(1)),iv(h.initial(2))),iv(2*h.ambient)));
dc=mul(iv(.5),sub(iv(h.initial(1)),iv(h.initial(2))));
me=mul(iv(10),add(wide(c.idle_cpu),wide(c.idle_npu)));
de=mul(iv(5),sub(wide(c.idle_cpu),wide(c.idle_npu)));
mt=add(me,mul(sub(mc,me),ex(mul(iv(20),iv(t)))));
dt=add(de,mul(sub(dc,de),ex(mul(iv(40),iv(t)))));
base=add(iv(h.ambient),add(mt,mul(iv(3-2*node),dt)));
% Starts/ends are exact rationals in quarter-ms units. Enclose conversion.
s=wide(columns(:,3)/4000);e=wide(columns(:,4)/4000);
effective=t76_iv('nonnegative',sub([min(t,e(:,1)) min(t,e(:,2))],s));
lag=t76_iv('nonnegative',sub(iv(t),e));
a=mul(iv(10),mul(sub(iv(1),ex(mul(iv(20),effective))),ex(mul(iv(20),lag))));
b=mul(iv(5),mul(sub(iv(1),ex(mul(iv(40),effective))),ex(mul(iv(40),lag))));
same=t76_iv('nonnegative',add(a,b));cross=t76_iv('nonnegative',sub(a,b));
kind=c.unit_kind(columns(:,5));kind=kind(:);pulse=cross;pulse(kind==node,:)=same(kind==node,:);
q=zeros(size(columns,1),1);for k=1:numel(q),q(k)=c.options{columns(k,1)}(columns(k,2),4);end
pulse=t76_iv('nonnegative',mul(wide(q),pulse));
rhs=sub(add(iv(h.limit(node)),wide(h.band)),base);
r=struct('node',node,'time_s',t,'baseline_interval',base,'pulse_interval',pulse, ...
 'coefficient_lower',pulse(:,1),'rhs_upper',rhs(2), ...
 'basis','exact frozen modal rates 20/40; Taylor32 remainder; outward IEEE intervals');
end
