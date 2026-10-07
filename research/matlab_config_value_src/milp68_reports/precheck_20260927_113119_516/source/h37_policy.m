function out = h37_policy(c,h,config,version,clock,thermal_filter)
% Event-driven policy; receives no reference schedules, bounds or results.
if nargin<5, clock=tic; end
if nargin<6, thermal_filter=strcmp(version,'P1'); end
assert(ismember(version,{'P0','P1'}));
net=thv_build(h); now=0; state=zeros(1,4); estimated=config.duration;
s=struct('modes',config.modes,'duration',config.duration,'increment',config.increment, ...
    'start',nan(1,4),'finish',nan(1,4),'model','task','cpu_order',[],'npu_order',[]);
events=struct('time_s',{},'kind',{},'stage',{},'slack_s',{},'predicted_A_s',{}, ...
    'predicted_B_s',{},'thermal',{},'peak_CPU_C',{},'peak_NPU_C',{},'state',{});
status='running'; reason=''; evaluations=0; rejected=0; uncertain=0; waits=0;
pred=nan(1,2);
while strcmp(status,'running')
    if toc(clock)>h.budget_s, status='timeout'; reason='shared_case_version_budget'; break; end
    finished=find(state==1 & s.finish<=now+c.time_tol);
    for z=finished
        state(z)=2; estimated(z)=s.finish(z)-s.start(z); logevent('complete',z,NaN,'',nan(1,2));
    end
    if all(state==2), status='completed'; break; end
    pred=predict();
    if any(pred>c.deadline+c.time_tol)
        status='prefix_deadline_failure'; reason='optimistic_completion_bound_exceeds_deadline';
        logevent('prefix_failure',0,NaN,'',nan(1,2)); break;
    end
    if now>=c.window-c.time_tol, status='incomplete'; reason='window_exhausted'; break; end
    ongrid=abs(now/h.grid-round(now/h.grid))*h.grid<=c.time_tol;
    started=false;
    if ongrid
        while true
            if toc(clock)>h.budget_s, status='timeout'; reason='shared_case_version_budget'; break; end
            pred=predict();
            if any(pred>c.deadline+c.time_tol)
                status='prefix_deadline_failure'; reason='optimistic_completion_bound_exceeds_deadline'; break;
            end
            ready=[];
            for i=1:2
                if state(i)==0 && c.release(i)<=now+c.time_tol && ~any(state(1:2)==1)
                    ready(end+1)=i;
                end
                if state(i+2)==0 && state(i)==2 && ~any(state(3:4)==1)
                    ready(end+1)=i+2;
                end
            end
            if isempty(ready), break; end
            req=mod(ready-1,2)+1;
            keys=[(c.deadline(req)-pred(req))' c.deadline(req)' c.release(req)' req' ready'];
            [~,order]=sortrows(keys,[1 2 3 4 5]); ready=ready(order);
            committed=false;
            for z=ready
                i=mod(z-1,2)+1; slack=c.deadline(i)-pred(i);
                candidate=s; candidate.start(z)=now; candidate.finish(z)=now+s.duration(z);
                thermal='not_checked'; peaks=nan(1,2); accepted=true;
                if thermal_filter
                    ev=h37_partial(c,candidate,h,net); evaluations=evaluations+1;
                    thermal=ev.status; peaks=ev.peak; accepted=strcmp(thermal,'safe');
                end
                if ~accepted
                    rejected=rejected+1; uncertain=uncertain+strcmp(thermal,'unresolved');
                    logevent('reject',z,slack,thermal,peaks); continue;
                end
                s=candidate; state(z)=1; committed=true; started=true;
                logevent('start',z,slack,thermal,peaks); break;
            end
            if ~committed, break; end
        end
    end
    if ~strcmp(status,'running'), break; end
    if ongrid && ~started
        waits=waits+1; logevent('advance_without_start',0,NaN,'',nan(1,2));
    end
    nextgrid=(floor((now+c.time_tol)/h.grid)+1)*h.grid;
    future=[nextgrid s.finish(state==1) c.release(c.release>now+c.time_tol) c.window];
    future=future(future>now+c.time_tol); assert(~isempty(future));
    now=min(future);
end
validation=[]; energy=[]; thermal=[];
if strcmp(status,'completed')
    [~,s.cpu_order]=sort(s.start(1:2)); [~,s.npu_order]=sort(s.start(3:4));
    validation=cv_validate(c,s); assert(validation.feasible);
    energy=cv_energy(c,s); thermal=thv_evaluate(c,s,h,net);
end
out=struct('version',version,'thermal_filter',thermal_filter,'status',status,'reason',reason, ...
    'schedule',s,'state',state,'events',events,'validation',validation,'energy',energy, ...
    'thermal',thermal,'thermal_evaluations',evaluations,'rejected',rejected, ...
    'unresolved_rejections',uncertain,'advances_without_start',waits, ...
    'elapsed_shared_s',toc(clock));
    function p=predict()
        freeC=max([now s.finish(1:2).*(state(1:2)==1)],[],'omitnan');
        freeN=max([now s.finish(3:4).*(state(3:4)==1)],[],'omitnan');
        p=zeros(1,2);
        for q=1:2
            if state(q)==0, ce=max([now c.release(q) freeC])+estimated(q);
            else, ce=s.finish(q); end
            if state(q+2)==0, p(q)=max([now ce freeN])+estimated(q+2);
            else, p(q)=s.finish(q+2); end
        end
    end
    function logevent(kind,z,slack,label,peaks)
        events(end+1)=struct('time_s',now,'kind',kind,'stage',z,'slack_s',slack, ...
            'predicted_A_s',pred(1),'predicted_B_s',pred(2),'thermal',label, ...
            'peak_CPU_C',peaks(1),'peak_NPU_C',peaks(2),'state',sprintf('%d',state));
    end
end
