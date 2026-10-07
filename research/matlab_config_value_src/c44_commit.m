function s=c44_commit(c,s,row,t)
next=c44_schedule(c,row); now=~isfinite(s.start) & abs(next.start-t)<=c.time_tol;
for field={'unit','start','finish','duration','increment'}
    f=field{1}; s.(f)(now)=next.(f)(now);
end
for j=find(now(1:2)), s.modes(j)=next.modes(j); end
end
