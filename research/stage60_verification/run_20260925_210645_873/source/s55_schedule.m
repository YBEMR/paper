function s=s55_schedule(c,row)
n=c.n; s=struct('choice',nan(1,n),'unit',nan(1,n),'mode',nan(1,n), ...
    'start',nan(1,n),'finish',nan(1,n),'duration',nan(1,n),'increment',nan(1,n));
if nargin<2 || isempty(row), return; end
row=double(row); assert(numel(row)==2*n);
for i=1:n
    if ~isfinite(row(i)), continue; end
    m=c.options{i}(row(i),:); s.choice(i)=row(i); s.unit(i)=m(1); s.mode(i)=m(2);
    s.start(i)=row(n+i)*c.grid; s.duration(i)=m(3); s.finish(i)=s.start(i)+m(3); s.increment(i)=m(4);
end
end
