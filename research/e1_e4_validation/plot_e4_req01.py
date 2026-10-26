"""Plot only archived request-count evidence; no scientific backends."""
from pathlib import Path
from fractions import Fraction as F
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;OUT=HERE/'results/e4_req_01'
def main():
    s=json.loads((OUT/'analysis.json').read_bytes())['slots'];xs=list(range(len(s)))
    labels=['1 per application','2 per application']
    fig,(left,right)=plt.subplots(1,2,figsize=(9,3.6),layout='constrained')
    for ax,field,ylabel,title in [(left,'post_U_approx_J','System energy (J)','Weighted full-window energy'),
        (right,'per_request_U_approx_J','Energy per request (J)','Same window; fixed costs amortize')]:
        for x,v in zip(xs,s):
            if v['state']=='POST_SAFE':
                y=v[field];ax.bar(x,y,width=.6,color='#366a91');ax.text(x,y*1.02,f'{y:.6f}',ha='center',fontsize=9)
            else:
                ax.bar(x,0,width=.6,color='white',edgecolor='#999999');ax.text(x,.05,v['state']+'\nNo valid energy',ha='center',fontsize=9)
        ax.set(xticks=xs,xticklabels=labels,ylabel=ylabel,title=title);ax.set_ylim(bottom=0);ax.margins(y=.2)
        ax.spines[['top','right']].set_visible(False)
    fig.savefig(OUT/'e4_requests_energy.png',dpi=220);fig.savefig(OUT/'e4_requests_energy.pdf');plt.close(fig)
if __name__=='__main__':main()
