"""Plots from terminal facts only; no search or physical evaluation."""
from fractions import Fraction as F
import json
import os
from pathlib import Path
import sys
REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
os.environ.setdefault('MPLCONFIGDIR',str(REPO/'.runtime/mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main(folder):
    folder=Path(folder);facts=json.loads((folder/'facts.json').read_text(encoding='utf-8'))
    rows=facts['rows'];cohorts=facts['cohorts']
    labels=['whole_milp','anchor_linked4','heft','sa101']
    fig,axes=plt.subplots(3,2,figsize=(12,11),sharex=True)
    for index,c in enumerate(cohorts):
        ax=axes.flat[index]
        for method in labels:
            row=next((v for v in rows if v['problem_id']==c['problem_id'] and v['method']==method),None)
            if row is None:continue
            curve=sorted(row['safe_curve'],key=lambda v:v['completed_at_s'])
            times=[];values=[];best=None
            for point in curve:
                t=point['completed_at_s']
                if not 0<=t<300:continue
                upper=float(F(point['energy_interval_J'][1]))
                best=upper if best is None else min(best,upper)
                times.append(t);values.append(best)
            if times:
                times.append(300);values.append(best)
                ax.step(times,values,where='post',label=method)
        lower=next((v['independent_L0_J'] for v in rows if v['problem_id']==c['problem_id'] and v['independent_L0_J'] is not None),None)
        if lower is not None:ax.axhline(lower,color='gray',linestyle='--',label='L0 retrospective reference')
        ax.set(title=c['problem_id'],xlabel='Method elapsed (s)',ylabel='Best complete-safe U (J)',xlim=(0,300))
        ax.grid(alpha=.25)
    axes.flat[5].axis('off')
    handles,names=axes.flat[0].get_legend_handles_labels()
    axes.flat[5].legend(handles,names,loc='center',fontsize=10)
    fig.suptitle('P0 segmented cohort: best safe bounds; SA101 is one seed',fontsize=14)
    fig.tight_layout();fig.savefig(folder/'safe_curves.png',dpi=180);plt.close(fig)

    x=np.arange(len(cohorts));width=.19
    fig,axes=plt.subplots(1,2,figsize=(13,4.8))
    for k,method in enumerate(labels[:3]):
        energy=[];times=[]
        for c in cohorts:
            row=next((v for v in rows if v['problem_id']==c['problem_id'] and v['method']==method),{})
            energy.append(row.get('normalized_to_HEFT') if row.get('normalized_to_HEFT') is not None else np.nan)
            times.append(row.get('method_root_s') if row.get('method_root_s') is not None else np.nan)
        axes[0].bar(x+(k-1.5)*width,energy,width,label=method)
        axes[1].bar(x+(k-1.5)*width,times,width,label=method)
    medians=[];median_times=[];low=[];high=[]
    for c in cohorts:
        subset=[v for v in rows if v['problem_id']==c['problem_id'] and v['seed'] is not None and v['comparison_usable']]
        values=[v['normalized_to_HEFT'] for v in subset if v.get('normalized_to_HEFT') is not None]
        if not values:medians.append(np.nan);low.append(0);high.append(0)
        else:
            med=float(np.median(values));medians.append(med);low.append(med-min(values));high.append(max(values)-med)
        median_times.append(float(np.median([v['method_root_s'] for v in subset])) if subset else np.nan)
    axes[0].bar(x+1.5*width,medians,width,yerr=[low,high],capsize=3,label='SA5 median, min/max (descriptive)')
    axes[1].bar(x+1.5*width,median_times,width,label='SA5 median (descriptive)')
    for ax in axes:
        ax.set_xticks(x,[c['problem_id'].split('__')[1] for c in cohorts]);ax.grid(axis='y',alpha=.25)
    axes[0].set(ylabel='Safe U / same-problem HEFT U',title='Energy; SA5 is not a best-of-five competitor')
    axes[0].axhline(1,color='gray',linestyle='--',linewidth=.8)
    axes[1].set(ylabel='Method root stop (s)',title='Includes initialization, model, solver and heat')
    handles,names=axes[0].get_legend_handles_labels()
    fig.legend(handles,names,loc='lower center',ncol=4,fontsize=8)
    fig.tight_layout(rect=(0,.07,1,1));fig.savefig(folder/'energy_and_method_time.png',dpi=180);plt.close(fig)

    fig,ax=plt.subplots(figsize=(8,4.5))
    for k,key in enumerate(('phase1_U_J','phase2_U_J')):
        vals=[next((v.get(key) for v in rows if v['problem_id']==c['problem_id'] and v['method']=='anchor_linked4'),None) for c in cohorts]
        ax.bar(x+(k-.5)*.32,[np.nan if v is None else v for v in vals],.32,label=key)
    ax.set_xticks(x,[c['problem_id'].split('__')[1] for c in cohorts])
    ax.set(ylabel='Complete safe U (J)',title='Linked method: committed energy after each phase')
    ax.grid(axis='y',alpha=.25)
    handles,names=ax.get_legend_handles_labels()
    fig.legend(handles,names,loc='lower center',ncol=2)
    fig.tight_layout(rect=(0,.08,1,1));fig.savefig(folder/'linked_phase_energy.png',dpi=180);plt.close(fig)
    print('Saved three scientific plots; incumbent curves are cumulative minima')


if __name__=='__main__':main(sys.argv[1])
