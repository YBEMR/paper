function s=b64_schedule(d,m,t)
known=isfinite(t);mm=double(m);mm(~known)=NaN;
s=s55_schedule(d,[mm t/d.g]);
end
