function v = cv_validate(c,s)
% Does not classify temperature; no thermal model is evaluated here.
tol=c.time_tol; reasons={};
if any(~isfinite([s.start s.finish s.duration s.increment]))
    reasons{end+1}='nonfinite';
end
if any(s.duration<=0) || any(s.increment<0), reasons{end+1}='invalid_mode'; end
if any(abs(s.finish-s.start-s.duration)>tol), reasons{end+1}='duration'; end
if any(s.start < -tol) || any(s.start(1:2)<c.release-tol)
    reasons{end+1}='release';
end
if any(s.start(3:4)<s.finish(1:2)-tol), reasons{end+1}='precedence'; end
if overlaps(s,1,2,tol), reasons{end+1}='cpu_overlap'; end
if overlaps(s,3,4,tol), reasons{end+1}='npu_overlap'; end
if any(s.finish(3:4)>c.deadline+tol), reasons{end+1}='deadline'; end
if any(s.finish>c.window+tol), reasons{end+1}='window'; end
v=struct('feasible',isempty(reasons),'reason',strjoin(reasons,';'), ...
    'completion',s.finish(3:4),'thermal','not_evaluated');
end
function yes=overlaps(s,a,b,tol)
yes=min(s.finish(a),s.finish(b))-max(s.start(a),s.start(b))>tol;
end
