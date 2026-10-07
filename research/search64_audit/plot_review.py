"""Figures from saved CSV only; no new planning or thermal evaluations."""
import csv, pathlib, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=pathlib.Path(sys.argv[1])
with (p/'summary.csv').open(encoding='utf-8-sig',newline='') as f:
    rows=list(csv.DictReader(f))
truth=lambda s:s.lower() in ('1','true')
cases=list(dict.fromkeys(r['case_id'] for r in rows if r['cohort']=='main'))
methods=['full','no_repair','simple_order','bare','joint_noheat','full_suffix','thermal_reference']
lookup={(r['case_id'],r['method']):r for r in rows}
fig,ax=plt.subplots(figsize=(12,5.7))
colors=np.zeros((len(cases),len(methods),3))
for i,c in enumerate(cases):
    for j,m in enumerate(methods):
        r=lookup[c,m]
        if truth(r['safe']):
            colors[i,j]=[.78,.92,.80];label=f"{float(r['energy_mJ']):g}"
        elif truth(r['complete']) and truth(r['legal']):
            colors[i,j]=[1,.75,.70];label='unsafe'
        else:
            colors[i,j]=[.86,.86,.86];label='U'
        ax.text(j,i,label,ha='center',va='center',fontsize=10)
ax.imshow(colors,aspect='auto')
ax.set_xticks(range(len(methods)),methods,rotation=22,ha='right')
ax.set_yticks(range(len(cases)),cases)
ax.set_title('Main cases: verified safe energy (mJ); U = unresolved within budget')
fig.text(.5,.015,'Same L3 inputs and 60 s budgets. Green is a safe output, not a claim of hardware benefit.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.05,1,1));fig.savefig(p/'main_quality_review.png',dpi=170);plt.close(fig)

fig,axes=plt.subplots(2,1,figsize=(11,8),sharex=True)
for j,m in enumerate(methods[:4]):
    x=np.arange(len(cases))+(j-1.5)*.18
    axes[0].bar(x,[float(lookup[c,m]['popped']) for c in cases],width=.18,label=m)
    axes[1].bar(x,[float(lookup[c,m]['elapsed_s']) for c in cases],width=.18,label=m)
axes[0].set_ylabel('Nodes popped');axes[0].legend(ncol=4)
axes[0].set_title('Ablations: visited nodes and single-run wall time')
axes[1].set_ylabel('Seconds');axes[1].set_xticks(range(len(cases)),cases,rotation=30,ha='right')
for ax in axes:ax.grid(axis='y',alpha=.25);ax.set_axisbelow(True)
fig.tight_layout();fig.savefig(p/'ablation_review.png',dpi=170);plt.close(fig)

fig,ax=plt.subplots(figsize=(10,5))
for m in methods[:4]:
    a=np.loadtxt(p/f'bounds_06_{m}.csv',delimiter=',',ndmin=2)
    line,=ax.step(a[:,0],a[:,1],where='post',label=m+' lower')
    valid=np.isfinite(a[:,2])
    ax.scatter(a[valid,0],a[valid,2],marker='x',s=65,color=line.get_color(),label=m+' safe upper')
ax.set_xlabel('Seconds');ax.set_ylabel('Energy (mJ)');ax.set_title('P_high_D6_hot: bounds and first safe output')
ax.grid(alpha=.25);ax.legend(ncol=2,fontsize=8);fig.tight_layout()
fig.savefig(p/'bounds_hot_review.png',dpi=170);plt.close(fig)
