function state = schedule_state_before(pi,cfg,t)
% Decision-before-start convention: completions at t count, starts at t do not.
names={'A1','B1','A2','B2'}; resources={'C1','C2','N'};
s=double(pi(5:8));
d=[cfg.d_A1_ms(pi(3)) cfg.d_B1_ms(pi(4)) cfg.d_A2_ms cfg.d_B2_ms];
finish=s+d; assigned=[pi(1:2) 3 3];
release=[0 0 0 0];
if isfield(cfg,'rA_ms'), release(1)=cfg.rA_ms; end
if isfield(cfg,'rB_ms'), release(2)=cfg.rB_ms; end
done=finish<=t; running=s<t & finish>t;
ready=s>=t & release<=t;
ready(3)=ready(3) && done(1); ready(4)=ready(4) && done(2);
free=true(1,3); free(assigned(running))=false;
state.done=names(done); state.running=names(running);
state.ready=names(ready); state.free=resources(free);
end
