"""E3 figure from saved evidence only: energy tie and one mapping change."""
from pathlib import Path
from fractions import Fraction as F
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;OUT=HERE/'results/e3_deploy_01'
def main():
    a=json.loads((OUT/'analysis.json').read_bytes());slots=a['slots']
    if any(s['state']!='POST_SAFE' for s in slots):raise ValueError('two post-safe results required')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,(left,right)=plt.subplots(1,2,figsize=(9.8,3.6),layout='constrained',gridspec_kw={'width_ratios':[1,1.15]})
    bottom=[0.,0.]
    for key,label,color in [('external_common','Common','#9da7b1'),('baseline','Baseline','#79a5c8'),
                            ('activity','Stage activity','#366a91'),('temperature_correction','Temperature correction','#db8e3f')]:
        values=[float(F(s['weighted_components_J'][key][1])) for s in slots]
        left.bar([0,1],values,bottom=bottom,width=.5,label=label,color=color);bottom=[b+v for b,v in zip(bottom,values)]
    for n,s in enumerate(slots):left.text(n,s['post_U_approx_J']+.02,f"{s['post_U_approx_J']:.9f}",ha='center',fontsize=9)
    left.set(xticks=[0,1],xticklabels=['Shared A','Scene-local A'],ylabel='Weighted full-window energy (J)',
             ylim=(0,1.25),title='No energy difference resolved')
    left.legend(loc='upper right',fontsize=8,frameon=False)
    changes=a['comparison'].get('stage_changes',[])
    if len(changes)==1:
        change=changes[0]
        for y,(arm,label,color) in enumerate([('SHARED','Shared A','#366a91'),('SCENE_LOCAL_A','Scene-local A','#5b8978')]):
            row=change[arm];start=float(F(row['start_ms']));end=float(F(row['end_ms']))
            right.barh(y,end-start,left=start,height=.4,color=color)
            right.text((start+end)/2,y,f"A.post / {row['unit']} / {row['opp']}",ha='center',va='center',color='white',fontsize=9)
        right.set(yticks=[0,1],yticklabels=['Shared A','Scene-local A'],xlim=(110,127),ylim=(-.6,1.6),
                  xlabel='AB scene time (ms)',title='Only AB A.post changes its CPU unit')
        right.invert_yaxis();right.text(.5,.03,'Other devices, OPPs and start times unchanged',transform=right.transAxes,ha='center',fontsize=8)
    else:right.text(.5,.5,'See schedules.csv for full comparison',ha='center',transform=right.transAxes)
    fig.savefig(OUT/'e3_energy_mapping.png',dpi=220);fig.savefig(OUT/'e3_energy_mapping.pdf');plt.close(fig)
if __name__=='__main__':main()
