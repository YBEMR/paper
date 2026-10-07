function out = waiting_scheduler(cfg, th, opts)
% WAITING_SCHEDULER Single-stage rolling prediction; no future reservations.
% Starts from t=0. Only actually started tasks contribute known future power.
% Unstarted stages are idle in prediction. A future candidate is reconsidered
% every ms and after each actual start; it never reserves a resource.
% Candidate key: incremental energy, start, peak, core, frequency index.
% opts.max_wait=0 is the matched immediate-only control; default Inf searches
% all legal remaining slots. Scheduling units are explicitly 1 ms here.
if nargin < 3, opts = struct(); end
if ~isfield(opts,'max_wait'), opts.max_wait = Inf; end
if ~isfield(opts,'sub'), opts.sub = 4; end
if ~isfield(opts,'map_mode'), opts.map_mode = 'parallel'; end
if ~isfield(opts,'priority'), opts.priority = [1 2 3 4]; end
assert(cfg.delta_ms == 1, 'waiting_scheduler:units', 'This baseline requires a 1-ms scheduling grid.');
assert(isscalar(cfg.T0) && opts.sub >= 1 && mod(opts.sub,1)==0);
assert(opts.max_wait >= 0 && (isinf(opts.max_wait) || mod(opts.max_wait,1)==0));
assert(isequal(sort(opts.priority),1:4));
H = cfg.H_ms;
idle = [cfg.P_idle_C cfg.P_idle_C cfg.P_idle_N];
Q = repmat(idle,H,1);
occupied = false(H,3);
started = false(1,4); starts = nan(1,4); finish = inf(1,4);
freq = nan(1,2); maps = nan(1,2);
release = [0 0];
if isfield(cfg,'rA_ms'), release(1)=cfg.rA_ms; end
if isfield(cfg,'rB_ms'), release(2)=cfg.rB_ms; end
deadline = [cfg.D_A_ms cfg.D_B_ms cfg.D_A_ms cfg.D_B_ms];
tail = [cfg.d_A2_ms cfg.d_B2_ms 0 0];
x = repmat(cfg.T0-th.T_amb,3,1);
step = expm(th.A * cfg.s_per_ms / opts.sub);
trace = zeros(0,13); % t,round,stage,freq,core,start,dE,peak,action,T1,T2,TN,ncand
tests = 0; tic_id = tic;
for t = 0:H-1
    round_id = 0;
    while true
        round_id = round_id+1; committed = false;
        for j = opts.priority
            if started(j), continue; end
            if j<=2 && t<release(j), continue; end
            if j>2 && finish(j-2)>t, continue; end
            if j>2
                cores=3; modes=1;
            else
                modes=[1 2];
                switch opts.map_mode
                    case 'parallel', cores=j;
                    case 'same', cores=1;
                    case 'auto', cores=[1 2];
                    otherwise, error('Unknown map mode.');
                end
            end
            cand=zeros(0,6); % dE,start,peak,core,freq,duration
            for f=modes
                [d,p] = stage_config(j,f);
                latest=min([H-d, deadline(j)-tail(j)-d, t+opts.max_wait]);
                for r=cores
                    for s=t:latest
                        if any(occupied(s+1:s+d,r)), continue; end
                        trial=Q(t+1:H,:);
                        trial(s-t+1:s-t+d,r)=p;
                        peak=predict(trial,x); tests=tests+1;
                        if peak <= cfg.T_lim
                            dE=(p-idle(r))*d*cfg.s_per_ms*1e3;
                            cand(end+1,:)=[dE s peak r f d]; %#ok<AGROW>
                        end
                    end
                end
            end
            if isempty(cand)
                trace(end+1,:)=[t round_id j nan nan nan nan nan -1 (x+th.T_amb)' 0]; %#ok<AGROW>
                continue;
            end
            cand=sortrows(cand,[1 2 3 4 5]); ch=cand(1,:);
            now=(ch(2)==t);
            trace(end+1,:)=[t round_id j ch(5) ch(4) ch(2) ch(1) ch(3) double(now) (x+th.T_amb)' size(cand,1)]; %#ok<AGROW>
            if ~now, continue; end % defer only this stage, not the whole machine
            r=ch(4); f=ch(5); d=ch(6); [~,p]=stage_config(j,f);
            Q(t+1:t+d,r)=p; occupied(t+1:t+d,r)=true;
            started(j)=true; starts(j)=t; finish(j)=t+d;
            if j<=2, freq(j)=f; maps(j)=r; end
            committed=true;
            break; % re-evaluate all remaining ready stages after this start
        end
        if ~committed, break; end
    end
    ss=th.Ginv*Q(t+1,:)';
    for k=1:opts.sub, x=ss+step*(x-ss); end
end
out.seconds=toc(tic_id);
out.pi=[maps freq starts]; out.started=started; out.finish=finish;
out.complete=all(started) && all(finish<=H);
out.partial_energy_mJ=sum(Q(:))*cfg.s_per_ms*1e3;
out.E_mJ=NaN;
if out.complete, out.E_mJ=out.partial_energy_mJ; end
out.candidate_evaluations=tests; out.power=Q; out.options=opts;
out.trace=array2table(trace,'VariableNames',{'t','round','stage','frequency','core',...
    'candidate_start','incremental_mJ','predicted_peak','action',...
    'T_C1','T_C2','T_N','feasible_candidates'});
% action: -1 no feasible candidate, 0 defer (no reservation), 1 actual start.
    function [d,p]=stage_config(j,f)
        switch j
            case 1, d=cfg.d_A1_ms(f); p=cfg.P_A1(f);
            case 2, d=cfg.d_B1_ms(f); p=cfg.P_B1(f);
            case 3, d=cfg.d_A2_ms; p=cfg.P_A2;
            case 4, d=cfg.d_B2_ms; p=cfg.P_B2;
        end
    end
    function peak=predict(q,z)
        peak=max(z+th.T_amb);
        for kk=1:size(q,1)
            ss0=th.Ginv*q(kk,:)';
            for u=1:opts.sub
                z=ss0+step*(z-ss0); peak=max(peak,max(z+th.T_amb));
            end
        end
    end
end
