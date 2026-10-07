function v=c44_validate(c,s,partial)
if nargin<3, partial=false; end
t=c.time_tol; known=isfinite(s.start); reasons={};
if ~partial && ~all(known), reasons{end+1}='incomplete'; end
if ~isequal(known,isfinite(s.finish)) || any(~isfinite(s.duration(known))) || any(~isfinite(s.increment(known)))
    reasons{end+1}='nonfinite';
end
if any(s.duration(known)<=0) || any(s.increment(known)<0), reasons{end+1}='response'; end
if any(abs(s.finish(known)-s.start(known)-s.duration(known))>t), reasons{end+1}='duration'; end
if any(s.start(known)<-t) || any(s.finish(known)>c.window+t), reasons{end+1}='window'; end
if any(abs(s.start(known)-round(s.start(known)/c.grid)*c.grid)>t), reasons{end+1}='grid'; end
[d,q]=cv_response(c,'task');
for i=1:2
    if known(i)
        if ~ismember(s.unit(i),[1 2]) || ~ismember(s.modes(i),[1 2]), reasons{end+1}='cpu_mode';
        else
            if abs(s.duration(i)-d(i,s.modes(i)))>t || abs(s.increment(i)-q(i,s.modes(i)))>1e-12, reasons{end+1}='response'; end
        end
        if s.start(i)<c.release(i)-t, reasons{end+1}='release'; end
    end
    j=i+2;
    if known(j)
        if s.unit(j)~=3 || abs(s.duration(j)-c.n(i))>t || abs(s.increment(j)-c.npu_increment(i))>1e-12, reasons{end+1}='npu_mode'; end
        if ~known(i) || s.start(j)<s.finish(i)-t, reasons{end+1}='precedence'; end
        if s.finish(j)>c.deadline(i)+t, reasons{end+1}='deadline'; end
    end
end
if all(known(1:2)) && overlap(1,2)
    if s.unit(1)==s.unit(2), reasons{end+1}='cpu_unit_overlap'; end
    if all(ismember(s.unit(1:2),[1 2])) && c.domain(s.unit(1))==c.domain(s.unit(2)) && s.modes(1)~=s.modes(2)
        reasons{end+1}='domain_frequency_conflict';
    end
end
if all(known(3:4)) && overlap(3,4), reasons{end+1}='npu_overlap'; end
v=struct('feasible',isempty(reasons),'reason',strjoin(unique(reasons),';'),'completion',s.finish(3:4));
    function yes=overlap(a,b), yes=min(s.finish([a b]))-max(s.start([a b]))>t; end
end
