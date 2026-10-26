"""Static plots of archived E2 evidence only; no scientific backend calls."""
from pathlib import Path
from fractions import Fraction as F
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;OUT=HERE/'results/e2_res_01'

def main():
    a=json.loads((OUT/'analysis.json').read_bytes());s=a['slots']
    if any(x['state']!='POST_SAFE' for x in s):raise ValueError('plot requires all four final post-safe slots')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,(left,right)=plt.subplots(1,2,figsize=(10,3.7),layout='constrained')
    names=['CPU','CPU+GPU','CPU+NPU','CPU+GPU+NPU'];xs=list(range(4));bottom=[0.0]*4
    for key,label,color in [('external_common','Common','#9da7b1'),('baseline','Baseline','#79a5c8'),
                            ('activity','Stage activity','#366a91'),('temperature_correction','Temperature correction','#db8e3f')]:
        values=[float(F(v['weighted_components_J'][key][1])) for v in s]
        left.bar(xs,values,bottom=bottom,label=label,color=color,width=.64)
        bottom=[x+y for x,y in zip(bottom,values)]
    for x,v in zip(xs,s):left.text(x,v['post_U_approx_J']+.025,f"{v['post_U_approx_J']:.4f}",ha='center',fontsize=9)
    left.set(xticks=xs,xticklabels=names,ylabel='Weighted full-window energy (J)',ylim=(0,1.65),title='Same platform; mapping availability changes')
    left.legend(loc='upper right',fontsize=8,frameon=False);left.tick_params(axis='x',labelsize=8)
    peaks=[float(F(v['peak_temperature_upper_degC'])) for v in s]
    right.bar(xs,peaks,color='#527e70',width=.64)
    for x,y in zip(xs,peaks):right.text(x,y+.8,f'{y:.2f}',ha='center',fontsize=9)
    right.axhline(80,color='#a44b40',linestyle='--',lw=1,label='Declared limit: 80 C')
    right.axhline(50,color='#999999',linestyle=':',lw=1,label='Entry: 50 C')
    right.set(xticks=xs,xticklabels=names,ylabel='Continuous peak upper bound (C)',ylim=(0,88),title='All four final schedules pass the same check')
    right.legend(loc='upper right',fontsize=8,frameon=True,facecolor='white',framealpha=1,edgecolor='none');right.tick_params(axis='x',labelsize=8)
    fig.savefig(OUT/'e2_energy_temperature.png',dpi=220)
    fig.savefig(OUT/'e2_energy_temperature.pdf')
    plt.close(fig)

if __name__=='__main__':main()
