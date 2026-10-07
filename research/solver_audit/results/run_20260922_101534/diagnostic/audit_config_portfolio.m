function out=audit_config_portfolio(p,a,clock0,budget)
% Diagnostic only: enumerate <=16 CPU mode combinations, no new planner.
out=struct('selected',zeros(1,p.n),'energy',Inf,'combinations',0,'attempts',0,'timeout',false);
n=p.requests;bits=dec2bin(0:2^n-1)-'0';[~,ix]=sortrows([sum(bits,2) bits],1:n+1);bits=bits(ix,:);
for b=1:size(bits,1)
 aa=a;
 for j=1:n
  ks=a.byStage{j};f=2-bits(b,j);aa.byStage{j}=ks(a.v(ks,3)==f);
 end
 h=audit_heuristic(p,aa,true,clock0,budget);out.combinations=out.combinations+1;
 out.attempts=out.attempts+h.attempts;
 if h.energy<out.energy,out.energy=h.energy;out.selected=h.selected;end
 % A valid analytic lower bound certifies a <=5% TOTAL-energy gap.
 if isfinite(out.energy) && (out.energy-p.energyLB)/out.energy<=.05,return;end
 if toc(clock0)>=budget,out.timeout=true;return;end
end
end
