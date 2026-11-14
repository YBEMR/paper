"""Symbolic consistency checks only. No device parameters or trajectories supplied."""
import json
from pathlib import Path
import sympy as s
R=Path(__file__).resolve().parent;O=R/'results';O.mkdir(exist_ok=True);checks=[]
def verify(name,expr):
    residual=s.simplify(expr);assert residual==0,(name,residual);checks.append({'name':name,'residual':str(residual),'passed':True})
E00,E10,E01,E11,a,b,c,d=s.symbols('E00 E10 E01 E11 a b c d')
interaction=E11-E10-E01+E00
verify('fixed_schedule_additive_effect_has_zero_interaction',interaction.subs({E00:a,E10:a+b,E01:a+c,E11:a+b+c}))
verify('cross_term_is_interaction',interaction.subs({E00:a,E10:a+b,E01:a+c,E11:a+b+c+d})-d)
Ei,Ej,hi,hj=s.symbols('Ei Ej hi hj');margin=Ei-Ej
verify('pair_order_reversal_margin',(Ei+hi)-(Ej+hj)-(margin+hi-hj))
W,Bh,Bl,kc,ks,D,Tfix=s.symbols('W B_h B_l k_concurrent k_serial D T_fixed',positive=True)
dc=2*W/Bh+(2*W/Bl-2*W/Bh)
verify('concurrent_bandwidth_bottleneck_duration',dc-2*W/Bl)
verify('serial_vs_capped_concurrent_service_gap',2*W/Bl-2*W/Bh-2*W*(1/Bl-1/Bh))
verify('energy_order_of_equal_byte_pair',2*W*kc/Bl-2*W*ks/Bh-2*W*(kc/Bl-ks/Bh))
t,tau,ell,kH,kL,kpause,RC,RS=s.symbols('t tau ell k_H k_L k_pause R_C R_S',positive=True)
tcap=tau+ell+2*W*(1-tau/t)/Bl
verify('delayed_cap_remaining_bytes_conserved',2*W*tau/t+Bl*(tcap-tau-ell)-2*W)
verify('deadline_reversal_boundary', (tcap-2*t).subs(Bl,2*W*(t-tau)/(t*(2*t-tau-ell))))
verify('delayed_cap_energy_difference',(kH*tau+kpause*ell+kL*(tcap-tau-ell)+RC)-(2*ks*t+RS)-(kH*tau+kpause*ell+2*W*kL*(1-tau/t)/Bl-2*ks*t+RC-RS))
Eb,Ea,eps,delta=s.symbols('E_simple E_joint epsilon delta',positive=True)
verify('gain_after_control_cost',(1-(Ea+delta)/Eb)-((Eb-Ea-delta)/Eb))
verify('one_percent_overhead_budget',(1-eps)*Eb-Ea-(Eb-Ea-eps*Eb))
Rcost=s.symbols('R_cost');verify('overlap_energy_budget',((Ei+Rcost)-Ej)-((Ei-Ej)+Rcost))
m=s.symbols('m',positive=True,integer=True)
verify('one_switch_equals_full_catalogue_if_one_repeat',m-m**1)
verify('one_switch_equals_full_catalogue_if_two_repeats',m+m*(m-1)-m**2)
out={'status':'SYMBOLIC_IDENTITIES_CHECKED_ONLY','sympy':s.__version__,'checks':checks,'numerical_schedule_evaluations':0,'parameters_filled':0,'warning':'Identities do not establish a measured positive region, cap participation, model adequacy, or energy savings.'}
(O/'symbolic_checks.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'checks':len(checks),'status':out['status'],'schedule_evaluations':0}))
