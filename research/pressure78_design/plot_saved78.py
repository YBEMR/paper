"""Plot saved, budget-qualified evidence only; no scheduling/thermal calls."""
from pathlib import Path
import csv,json,math,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
RUN=Path(sys.argv[1]).resolve();OUT=RUN/'plots';OUT.mkdir(exist_ok=True)
def tab(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
rows=tab(RUN/'summary.csv')
colors={'no_good':'#2166ac','thermal_row':'#d95f02'}
styles={1:'-',2:'--'};markers={1:'o',2:'s'}
for ti in range(1,18):
    rr=[r for r in rows if int(r['trial_index'])==ti]
    fig,ax=plt.subplots(1,2,figsize=(12,4.5));fig.suptitle(rr[0]['case_id'])
    count=0
    for r in rr:
        k=int(r['call_index']);method=r['method'];rep=int(r['rep'])
        data=json.loads((RUN/f'diagnostics_call_{k:03d}.json').read_text(encoding='utf-8-sig'))
        width=data['time_origin_offset_interval_s'][1]-data['time_origin_offset_interval_s'][0]
        bt=tab(RUN/f'bounds_units_call_{k:03d}.csv')
        st=tab(RUN/f'solver_trace_units_call_{k:03d}.csv')
        # Discard any trace endpoint whose enclosing wall-time upper bound exceeds 60.
        bt=[z for z in bt if float(z['elapsed_lower_estimate_s'])+width<=60]
        st=[z for z in st if float(z['elapsed_lower_estimate_s'])+width<=60]
        label=f'{method} r{rep}';kw=dict(color=colors[method],linestyle=styles[rep],marker=markers[rep],markersize=3)
        safe=[(float(z['elapsed_lower_estimate_s']),float(z['stored_upper_units'])*.0625)
              for z in bt if math.isfinite(float(z['stored_upper_units']))] if r['safe']=='1' else []
        if safe:
            count+=1;ax[0].plot(*zip(*safe),label=label,drawstyle='steps-post',**kw)
            lo=float(r['first_safe_s']);hi=float(r['first_safe_upper_s'])
            ax[0].errorbar(lo,safe[0][1],xerr=[[0],[hi-lo]],fmt='none',ecolor=colors[method],capsize=3)
        else:ax[0].plot([],[],label=label+': no safe U',**kw)
        if bt:ax[1].plot([float(z['elapsed_lower_estimate_s']) for z in bt],
                         [float(z['stored_lower_units'])*.0625 for z in bt],label=label+' L0',**kw)
        reported=[(float(z['elapsed_lower_estimate_s']),float(z['solver_lower_units'])*.0625)
                  for z in st if math.isfinite(float(z['solver_lower_units']))]
        if reported:ax[1].plot(*zip(*reported),color=colors[method],linestyle=':',marker=markers[rep],
                               markersize=3,label=label+' reported')
    if not count:
        ax[0].text(.5,.5,'No retained safe upper bound',ha='center',transform=ax[0].transAxes)
        ax[0].set_ylim(0,1);ax[0].set_yticks([])
    ax[0].set_title('Safe U; caps show first-safe time interval')
    ax[1].set_title('Independent L0 and solver-reported lower bounds')
    time_end=min(60,max(float(r['elapsed_s']) for r in rr)*1.03)
    for a in ax:
        a.set_xlim(0,max(.01,time_end))
        a.set_xlabel('Enclosing elapsed lower estimate (s)');a.set_ylabel('System energy (mJ)')
        a.grid(alpha=.2);a.legend(fontsize=7,loc='best')
    fig.tight_layout();fig.savefig(OUT/f'bounds_trial_{ti:02d}.png',dpi=150);plt.close(fig)

bases=['P_low_D6_hot','P_low_D10_hot','P_high_D6_hot','P_high_D10_hot']
for metric,title,ylabel in [('rounds','Solver calls, including unfinished final call','Calls'),
                            ('elapsed_s','Observed wall time, two balanced-order repetitions','Seconds')]:
    fig,axes=plt.subplots(2,2,figsize=(11,7));fig.suptitle(title)
    for base,ax in zip(bases,axes.flat):
        rr=[r for r in rows if r['cohort']=='main' and r['base_id']==base]
        for method in colors:
            for rep in [1,2]:
                rs=sorted([r for r in rr if r['method']==method and int(r['rep'])==rep],key=lambda r:float(r['initial_C']))
                xx=[float(r['initial_C']) for r in rs];yy=[float(r[metric]) for r in rs]
                ax.plot(xx,yy,color=colors[method],linestyle=styles[rep],marker=markers[rep],
                        label=f'{method} r{rep}',alpha=.8)
                for x,y,r in zip(xx,yy,rs):
                    if r['safe']!='1':ax.plot(x,y,'x',color='black',markersize=10)
        ax.set_title(base.removesuffix('_hot'));ax.set_xticks([78,79,79.5,79.75])
        ax.set_xlabel('Common initial temperature (C), tested points only');ax.set_ylabel(ylabel)
        ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.text(.5,.005,'Black x: no retained safe U; connecting lines do not certify untested temperatures.',ha='center',fontsize=8)
    fig.tight_layout(rect=[0,.025,1,.97]);fig.savefig(OUT/f'{metric}_by_temperature.png',dpi=150);plt.close(fig)
print('Rendered 17 bound figures and 2 discrete comparison figures from saved records.')
