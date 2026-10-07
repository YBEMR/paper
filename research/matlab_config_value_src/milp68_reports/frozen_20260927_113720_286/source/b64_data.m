function d=b64_data(c)
% Exact lattice adapter, restricted to representable inputs; never rounds data.
d=c;d.time_unit=1/4000;d.energy_unit=1/16000;
d.g=exact(c.grid*4000);d.w=exact(c.window*4000);
d.a=exact(c.release*4000);d.dead=exact(c.deadline*4000);
d.base=exact((c.idle_cpu+c.idle_npu+c.external)*c.window*16000);
d.dt=cell(1,c.n);d.en=d.dt;d.minD=zeros(1,c.n);d.minE=d.minD;
d.adj=false(c.n);
for i=1:c.n
 d.dt{i}=exact(c.options{i}(:,3)*4000);d.en{i}=exact(prod(c.options{i}(:,3:4),2)*16000);
 d.minD(i)=min(d.dt{i});d.minE(i)=min(d.en{i});d.adj(c.pred{i},i)=true;
end
[d.order,ok]=b64_topo(d.adj);assert(ok,'b64:input','Input DAG must be acyclic');
end
function k=exact(x)
k=round(x);assert(all(abs(x(:)-k(:))<=32*eps(max(1,abs(x(:))))) && all(abs(k(:))<2^45), ...
 'b64:lattice','Input does not match exact declared lattice');
end
