function [s,selected,E]=b68_decode(c,p,x)
assert(numel(x)==size(p.columns,1) && all(isfinite(x)),'b68:numeric','Candidate shape/nonfinite');
x=x(:);y=round(x);
assert(all(abs(x-y)<=1e-6) && all(y==0 | y==1),'b68:numeric','Not binary within declared tolerance');
assert(all(p.Aeq*y==p.beq) && all(p.A*y<=p.b),'b68:numeric','Rounded candidate violates exact integer matrix');
selected=find(y);choice=zeros(1,c.n);start=choice;
for j=selected',i=p.columns(j,1);choice(i)=p.columns(j,2);start(i)=p.columns(j,3);end
s=b64_schedule(p.d,choice,start);v=s55_validate(c,s);assert(v.feasible,'b68:numeric',v.reason);
E=p.d.base+p.f'*y;e=s55_energy(c,s);
assert(abs(e.sum_J-E*p.d.energy_unit)<1e-12 && e.error_J<1e-12,'b68:energy','Independent energy check failed');
end
