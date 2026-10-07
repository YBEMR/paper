function z = thv_step(net,theta,p,dt)
% Exact two-exponential representation; numerical endpoints + internal roots.
assert(dt>=0); theta=theta(:); p=p(:);
eq=net.G\p; coeff=net.V.*(net.Vi*(theta-eq))';
lam=net.lambda; values=@(t)eq+coeff*exp(-lam*t);
finish=values(dt); peaks=max(theta,finish); times=zeros(2,1);
times(finish>theta)=dt; roots=nan(2,1);
distinct=abs(lam(2)-lam(1))>100*eps(max(lam));
if distinct
    for n=1:2
        a=lam(1)*coeff(n,1); b=lam(2)*coeff(n,2);
        if a~=0 && b~=0 && sign(a)~=sign(b)
            t=(log(abs(b))-log(abs(a)))/(lam(2)-lam(1));
            if t>0 && t<dt
                roots(n)=t; v=values(t);
                if v(n)>peaks(n), peaks(n)=v(n); times(n)=t; end
            end
        end
    end
end
z=struct('finish',finish,'peak',peaks,'peak_time',times,'roots',roots, ...
    'equilibrium',eq,'coeff',coeff,'duration',dt,'theta_start',theta,'power',p);
end
