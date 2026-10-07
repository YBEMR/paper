function s=c44_schedule(c,row)
% Row = [modeA modeB unitA unitB startA startB startAN startBN].
[d,q]=cv_response(c,'task');
if nargin<2
    s=struct('modes',[nan nan],'unit',nan(1,4),'start',nan(1,4), ...
        'finish',nan(1,4),'duration',nan(1,4),'increment',nan(1,4)); return;
end
a=row(1); b=row(2);
s=struct('modes',[a b],'unit',[row(3:4) 3 3],'start',row(5:8), ...
    'duration',[d(1,a) d(2,b) c.n],'increment',[q(1,a) q(2,b) c.npu_increment]);
s.finish=s.start+s.duration;
end
