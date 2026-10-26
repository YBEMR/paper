"""Plot archived E4 deadline evidence; never invoke scientific backends."""
from pathlib import Path
from fractions import Fraction as F
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;OUT=HERE/'results/e4_dead_01'
def main():
    s=json.loads((OUT/'analysis.json').read_bytes())['slots'];xs=list(range(len(s)))
    labels=[str(v.get('deadline_beta',b)) for v,b in zip(s,('1.0','1.3','1.6'))]
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,(left,right)=plt.subplots(1,2,figsize=(9,3.6),layout='constrained');bottom=[0.0]*len(s)
    for key,label,color in [('external_common','Common','#9da7b1'),('baseline','Baseline','#79a5c8'),
        ('activity','Stage activity','#366a91'),('temperature_correction','Temperature correction','#db8e3f')]:
        values=[float(F(v['weighted_components_J'][key][1])) if v['state']=='POST_SAFE' else 0 for v in s]
        left.bar(xs,values,bottom=bottom,label=label,color=color,width=.62);bottom=[a+b for a,b in zip(bottom,values)]
    for x,v in zip(xs,s):
        if v['state']=='POST_SAFE':left.text(x,v['post_U_approx_J']+.018,f"{v['post_U_approx_J']:.6f}",ha='center',fontsize=9)
        else:left.text(x,.05,v['state'],ha='center',rotation=90)
    left.set(xticks=xs,xticklabels=labels,xlabel='Deadline multiplier beta',ylabel='Weighted full-window energy (J)',
        ylim=(0,max([1]+bottom)*1.38),title='Final verified energy; fixed workload and physics')
    left.legend(loc='upper right',fontsize=8,frameon=False)
    right.bar(xs,[v.get('plan_process_s') or 0 for v in s],label='Planning',color='#527e70',width=.62)
    right.bar(xs,[v.get('post_process_s') or 0 for v in s],bottom=[v.get('plan_process_s') or 0 for v in s],
        label='Fixed-candidate audit',color='#c6aa68',width=.62)
    for x,v in zip(xs,s):
        total=(v.get('plan_process_s') or 0)+(v.get('post_process_s') or 0)
        right.text(x,total+2,f'{total:.1f}s',ha='center',fontsize=9)
    right.set(xticks=xs,xticklabels=labels,xlabel='Deadline multiplier beta',ylabel='Observed parent wall time (s)',title='Single run per condition')
    right.legend(frameon=False,fontsize=8);right.margins(y=.2)
    fig.savefig(OUT/'e4_deadline_energy_time.png',dpi=220);fig.savefig(OUT/'e4_deadline_energy_time.pdf');plt.close(fig)
if __name__=='__main__':main()
