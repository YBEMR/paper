from pathlib import Path
import csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
def read(path):
    with (ROOT/path).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
rows=read('results/comparisons.csv');arms=read('results/arms.csv')
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(2,2,figsize=(12,8),layout='constrained')
methods=['NT','DelayRepair','D_C','D_M','TC1','TC2','TC4']
gaps=[max(float(x['excess_over_joint_pct']) for x in rows if x['method']==m) for m in methods]
ax[0,0].bar(methods,gaps,color=['#b46535','#c99562']+['#367ea2']*5)
ax[0,0].set(ylabel='Maximum excess energy over J (%)',title='(a) Exact timing optimization removes the entire gap')
ax[0,0].tick_params(axis='x',labelsize=9)
f=read('analysis/factorial_nt_gap.csv')
for shared,shift in [(0,-.16),(1,.16)]:
 q=[x for x in f if int(x['shared'])==shared]
 ax[0,1].bar(np.arange(4)+shift,[float(x['max_excess_pct']) for x in q],width=.3,label='Shared domain '+('on' if shared else 'off'))
ax[0,1].set(xticks=range(4),xticklabels=['C0 L0','C0 L1','C1 L0','C1 L1'],ylabel='Maximum NT excess (%)',title='(b) Small timing gap requires leakage feedback')
ax[0,1].legend(fontsize=9)
q=[x for x in arms if x['arm'].endswith('c1l1s1h1') and x['initial_C']=='78']
ax[1,0].bar(range(4),[int(x['legal']) for x in q],label='Timing/resource-legal',color='#c9dfe9')
ax[1,0].bar(range(4),[int(x['unsafe']) for x in q],label='Rejected by 80 C bound',color='#b46535')
ax[1,0].set(xticks=range(4),xticklabels=['W0 tight','W0 loose','W1 tight','W1 loose'],ylabel='Candidate schedules',title='(c) Heat rejects candidates, but not chosen policies')
ax[1,0].legend(fontsize=8)
selected='w1_d149500_t78_c1l1s1h1';z=np.load(ROOT/'results/w1_d149500_pool.npz')
colors=['#7d80a9','#319b88','#cd943b','#7d80a9']
for y,method in enumerate(['NT','J / D_C / TC1']):
 row=next(x for x in rows if x['arm']==selected and x['method']==('NT' if y==0 else 'J'))
 k=int(row['candidate_id']);cfg=z['configs'][z['pool'][k,0]];starts=z['pool'][k,2:6]*.1;duration=cfg[8:12]*.1
 for i in range(4):
  yy=y*3+(1 if i==2 else 0)
  ax[1,1].broken_barh([(starts[i],duration[i])],(yy,.65),facecolors=colors[i])
  ax[1,1].text(starts[i]+duration[i]/2,yy+.325,f'S{i}',ha='center',va='center',fontsize=8,color='white')
ax[1,1].axvline(149.5,color='gray',ls='--');ax[1,1].set(yticks=[.8,3.8],yticklabels=['NT','J / D_C / TC1'],xlabel='Time (ms); full energy window continues to 400 ms',xlim=(-2,157),title='(d) Same mapping/frequencies; a later schedule')
fig.suptitle('DJ-M1: synthetic model; finite-grid reference; no remaining decomposition loss',fontsize=13)
(ROOT/'figures').mkdir(exist_ok=True);fig.savefig(ROOT/'figures/boundary_results.png',dpi=170);plt.close(fig)
