function keep=c44_prefix(c,rows,s,t,after)
% before decision: pending starts >= t; after decision: pending starts > t.
known=isfinite(s.start); keep=true(size(rows,1),1);
for j=1:4
    st=rows(:,j+4);
    if known(j)
        keep=keep & abs(st-s.start(j))<=c.time_tol;
        if j<=2, keep=keep & rows(:,j)==s.modes(j) & rows(:,j+2)==s.unit(j); end
    elseif after, keep=keep & st>t+c.time_tol;
    else, keep=keep & st>=t-c.time_tol;
    end
end
end
