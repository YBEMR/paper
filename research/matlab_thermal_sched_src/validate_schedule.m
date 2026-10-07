function v = validate_schedule(pi,cfg,th,sub)
% Independent final checks; never turn a partial schedule into a completed one.
if nargin<4, sub=4; end
v=struct('ok',false,'complete',false,'legal',false,'thermal',false,...
    'E_mJ',NaN,'peak',NaN,'reason','incomplete');
if numel(pi)~=8 || any(~isfinite(pi)), return; end
if any(pi(1:4)~=round(pi(1:4))) || any(pi(1:4)<1 | pi(1:4)>2)
    v.reason='invalid mapping/frequency'; return;
end
s=double(pi(5:8));
d=[cfg.d_A1_ms(pi(3)) cfg.d_B1_ms(pi(4)) cfg.d_A2_ms cfg.d_B2_ms];
v.complete=all(s>=0 & s+d<=cfg.H_ms);
if ~v.complete, return; end
r=[0 0];
if isfield(cfg,'rA_ms'), r(1)=cfg.rA_ms; end
if isfield(cfg,'rB_ms'), r(2)=cfg.rB_ms; end
legal=all(s==round(s)) && all(s(1:2)>=r) && ...
    all(s(3:4)>=s(1:2)+d(1:2)) && ...
    all(s(3:4)+d(3:4)<=[cfg.D_A_ms cfg.D_B_ms]);
if pi(1)==pi(2), legal=legal && (s(1)+d(1)<=s(2) || s(2)+d(2)<=s(1)); end
legal=legal && (s(3)+d(3)<=s(4) || s(4)+d(4)<=s(3));
v.legal=legal;
if ~legal, v.reason='release/dependency/resource/deadline'; return; end
res=eval_schedules(pi,cfg,th,struct('sub',sub));
v.E_mJ=res.E*1e3; v.peak=res.Tmax; v.thermal=res.tr_ok; v.ok=res.tr_ok;
if v.ok, v.reason='ok'; else, v.reason='thermal'; end
end
