"""Identify which actual C/D priority changes exceed the energy enclosure width."""
import itertools
from fractions import Fraction
from shared import *
def main():
    cases={}
    for c in ['D1','D2','C10']:
        root=RUN/c;diag=root/'diagnostic'
        base=read(diag/'receipt.json')['initial']['plan']
        pool=read(diag/'probe_pool.json')
        scores=read(root/'A/probe_scores.json')
        certs=[read(diag/'physical/certificates'/((r['plan'] or base)+'.json')) for r in pool]
        orders=[[r['id'] for r in sorted(scores,key=lambda r:(-r[k],r['id']))] for k in ['gain35','gainfull']]
        changes=[]
        for a,b in itertools.combinations(range(len(pool)),2):
            if (orders[0].index(a)<orders[0].index(b))==(orders[1].index(a)<orders[1].index(b)):continue
            x,y=certs[a],certs[b]
            xa,xb=x['metrics']['E_bounds'];ya,yb=y['metrics']['E_bounds']
            exact_diff=Fraction(x['exact_E35_J'])-Fraction(y['exact_E35_J'])
            changes.append(dict(regions=[a,b],reference_delta_J=float(exact_diff),same_exact_reference=not exact_diff,
                thermal_delta_J=x['metrics']['E_J']-y['metrics']['E_J'],thermal_delta_bounds_J=[xa-yb,xb-ya],
                resolved=(xb<ya or yb<xa),empty_probes=[r['id'] for r in scores if r['id'] in (a,b) and not pool[r['id']]['plan']]))
        cases[c]=dict(reference_order=orders[0],full_order=orders[1],changed_pairs=changes,
                      certified_preferences=sum(r['resolved'] for r in changes))
    put(HERE/'results'/'probe_priority_audit.json',cases)
if __name__=='__main__':main()
