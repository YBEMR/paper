"""Saved-evidence plot only; no planner or thermal computation."""
from pathlib import Path
import json
from fractions import Fraction as F
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
RUN=HERE/'results/e4_df_01'
def main():
    summary=json.loads((RUN/'readonly_analysis.json').read_bytes())
    fig,ax=plt.subplots(1,2,figsize=(10,3.7),constrained_layout=True)
    labels=['Original HEFT','One deadline fallback']
    values=[x.get('post_U_approx_J') for x in summary['slots']]
    for n,(slot,value) in enumerate(zip(summary['slots'],values)):
        if value is None:
            ax[0].text(n,.05,'UNRESOLVED\n(no energy value)',ha='center',va='bottom',fontsize=9)
        else:
            ax[0].bar(n,value,color='#207a8a',width=.52)
            ax[0].text(n,value+.025,f'{value:.9f} J',ha='center',fontsize=9)
    ax[0].set_xticks(range(2),labels,fontsize=9)
    ax[0].set_xlim(-.6,1.6)
    ax[0].set_ylim(0,max([v for v in values if v is not None]+[1])*1.18)
    ax[0].set_ylabel('Final audited system energy (J)')
    ax[0].set_title('Same two-request input; missing is not zero',fontsize=10)
    any_events=False
    for n in range(1,3):
        v=json.loads((RUN/f'slot_{n}/plan/accepted_result.json').read_bytes())['result']
        events=v.get('archive',{}).get('events',[])
        if events:
            xs=[e['at_s'] for e in events];ys=[float(F(e['selected_true_U_J'])) for e in events]
            ax[1].step(xs,ys,where='post',label=labels[n-1]);any_events=True
    ax[1].set_xlabel('Charged planning wall time (s)')
    ax[1].set_ylabel('Selected safe energy upper bound (J)')
    ax[1].set_title('Saved improvement events; no post-budget search',fontsize=10)
    if any_events:ax[1].legend(fontsize=8);ax[1].ticklabel_format(axis='y',style='plain',useOffset=False)
    fig.savefig(RUN/'paired_outcome.png',dpi=180)
    plt.close(fig)
if __name__=='__main__':main()
