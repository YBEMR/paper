"""Generate the report figure from archived results; no scientific recomputation."""
from pathlib import Path
import csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
def read(name):
    with (ROOT/'results'/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def main():
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    rows=read('single_window.csv');states=read('initial_states.csv')
    temp=[float(x['Tj_C']) for x in states if x['case']=='nominal']
    for a in ['C','A50','B50','S_AB','S_BA']:
        vals=[float(next(x['energy_J'] for x in rows if x['case']=='nominal' and x['throttle']=='0' and x['state']==str(s) and x['action']==a)) for s in range(5)]
        ax[0,0].plot(temp,vals,'o-',label=a,ms=4)
    ax[0,0].set(xlabel='Initial junction temperature (C)',ylabel='Total model input energy (J)',title='(a) Nominal: same best action at all five states')
    ax[0,0].legend(ncols=3,fontsize=8)
    abl=read('ablation.csv');diff=[]
    for cont,leak in [(0,0),(0,1),(1,0),(1,1)]:
        q=[x for x in abl if x['state']=='0' and x['throttle']=='0' and int(x['contention'])==cont and int(x['leak'])==leak]
        diff.append(float(next(x['energy_J'] for x in q if x['action']=='C'))-float(next(x['energy_J'] for x in q if x['action']=='S_BA')))
    ax[0,1].bar(range(4),diff,color=['#4363a8','#4363a8','#cf6b3f','#cf6b3f'])
    ax[0,1].axhline(0,color='black',lw=.7)
    ax[0,1].set(xticks=range(4),xticklabels=['No contention\nConstant leak','No contention\nThermal leak','Contention\nConstant leak','Contention\nThermal leak'],ylabel='E(concurrent) - E(serial B,A) (J)',title='(b) Contention already explains the main ranking')
    ax[0,1].tick_params(axis='x',labelsize=8)
    policies=json.loads((ROOT/'results/policy_comparison.json').read_text())
    q=[x for x in policies if x['throttle']==0 and x['case']!='nominal']
    gx=[x['oracle_all_gain_pct'] for x in q]
    ax[1,0].scatter(range(len(q)),gx,label='Five-state oracle vs common fixed',s=22)
    ax[1,0].scatter(range(len(q)),[x['oracle_test_gain_pct'] for x in q],marker='x',color='#cf6b3f',label='Held-out oracle vs trained fixed',s=20)
    ax[1,0].set(xlabel='Valid sensitivity case index (62 total)',ylabel='Energy reduction (%)',title='(c) Tiny in-sample changes; zero held-out gain')
    ax[1,0].ticklabel_format(axis='y',style='sci',scilimits=(-2,2));ax[1,0].legend(fontsize=8)
    tr=read('nominal_trajectories.csv')
    for a in ['C','S_BA','threshold']:
        q=[x for x in tr if x['policy']==a]
        ax[1,1].plot([int(x['cycle']) for x in q],[float(x['energy_J']) for x in q],label=a,lw=1.5,linestyle='--' if a=='threshold' else '-')
    cold=float(next(x['energy_J'] for x in rows if x['case']=='nominal' and x['state']=='0' and x['throttle']=='0' and x['action']=='S_BA'))
    ax[1,1].axhline(cold,color='gray',ls=':',label='Free cold reset (diagnostic)')
    ax[1,1].set(xlabel='Period index (1.5 s per period)',ylabel='Input energy per period (J)',title='(d) Thermal carry-over changes energy, not policy')
    ax[1,1].legend(fontsize=8)
    fig.suptitle('A2-M1: uncalibrated literature-anchored model, not device measurements',fontsize=13)
    out=ROOT/'figures';out.mkdir(exist_ok=True)
    fig.savefig(out/'mechanism_results.png',dpi=180)
    plt.close(fig)
if __name__=='__main__':main()
