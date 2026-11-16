"""Read saved results and produce descriptive tables/figures; no new physics."""
from pathlib import Path
import csv,json,time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def analyze(out):
    tic=time.perf_counter()
    rows=list(csv.DictReader((out/'cases.csv').open(encoding='utf-8')))
    methods=list(csv.DictReader((out/'methods.csv').open(encoding='utf-8')))
    stats={}
    for m in sorted(set(r['method'] for r in methods)):
        rr=[r for r in methods if r['method']==m];safe=[r for r in rr if r['status']=='SAFE']
        gaps=[float(r['gap_to_E_percent']) for r in safe]
        wall=[float(r['wall_s']) for r in rr]
        stats[m]=dict(records=len(rr),safe=len(safe),same_energy_as_E=sum(abs(g)<=1e-8 for g in gaps),
                      positive_gap=sum(g>1e-8 for g in gaps),max_gap_percent=max(gaps,default=None),
                      wall_total_s=sum(wall),wall_median_ms=float(np.median(wall))*1000,
                      wall_max_ms=max(wall)*1000,thermal_evaluations=sum(int(r['thermal_evaluations']) for r in rr))
    # First qualifying case in frozen grid order, not strongest effect.
    examples={
      'thermal_energy_change':next((r['case_id'] for r in rows if r['thermal_constraint_cost_J'] and float(r['thermal_constraint_cost_J'])>1e-10),None),
      'necessary_map_change':next((r['case_id'] for r in rows if r['optimal_map_sets_disjoint']=='True'),None),
      'D_failure_or_gap':next((r['case_id'] for r in rows if r['E_J'] and (r['D_status']!='SAFE' or float(r['D_gap_percent'])>1e-8)),None)}
    ablations=[]
    for sigma in [0,.1,.25]:
        for beta in [.85,.9,1,1.5]:
            group=[r for r in rows if float(r['concurrent_slowdown_sigma'])==sigma and float(r['deadline_npu_allowance_over_time_unit'])==beta]
            ablations.append(dict(sigma=sigma,beta=beta,cases=len(group),
                feasible=sum(bool(r['E_J']) for r in group),no_deadline_feasible=sum(int(r['deadline_feasible'])==0 for r in group),
                thermal_infeasible=sum(int(r['deadline_feasible'])>0 and int(r['safe_feasible'])==0 for r in group),
                heat_cost_positive=sum(bool(r['thermal_constraint_cost_J']) and float(r['thermal_constraint_cost_J'])>1e-10 for r in group),
                map_change=sum(r['optimal_map_sets_disjoint']=='True' for r in group)))
    result=dict(methods=stats,examples=examples,by_slowdown_deadline=ablations,
                note='Grid counts are deterministic coverage, not empirical prevalence or probabilities.')
    (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    with (out/'ablations.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=ablations[0].keys());w.writeheader();w.writerows(ablations)
    plt.rcParams.update({'font.size':10,'figure.dpi':150})
    fig,axes=plt.subplots(1,3,figsize=(12,3.9),sharey=True)
    for ax,sigma in zip(axes,[0,.1,.25]):
        g=[r for r in ablations if r['sigma']==sigma];x=np.arange(4)
        a=np.array([r['feasible'] for r in g]);b=np.array([r['thermal_infeasible'] for r in g]);c=np.array([r['no_deadline_feasible'] for r in g])
        ax.bar(x,a,label='Feasible',color='#247a68');ax.bar(x,b,bottom=a,label='Thermally infeasible',color='#d98335');ax.bar(x,c,bottom=a+b,label='Deadline infeasible',color='#a7adb4')
        ax.set_xticks(x,['0.85','0.90','1.00','1.50']);ax.set_xlabel('NPU deadline allowance / L');ax.set_title(f'Overlap slowdown = {sigma:.0%}')
    axes[0].set_ylabel('Frozen parameter cases');axes[-1].legend(fontsize=8,loc='upper left')
    fig.suptitle('Conditional synthetic model: full grid feasibility (not hardware data)');fig.tight_layout();fig.savefig(out/'feasibility.png');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    feasible=[r for r in rows if r['E_J']]
    for tau,mark in [(1,'o'),(10,'s'),(100,'^')]:
        sub=[r for r in feasible if float(r['tau_over_time_unit'])==tau]
        axes[0].scatter([float(r['entry_theta']) for r in sub],[1000*float(r['thermal_constraint_cost_J']) for r in sub],s=16,alpha=.45,marker=mark,label=f'tau/L={tau}')
    axes[0].set_xlabel('Initial normalized temperature');axes[0].set_ylabel('Thermal constraint cost (mJ)');axes[0].legend(fontsize=8)
    d=[r for r in feasible if r['D_status']=='SAFE']
    axes[1].plot(np.arange(len(d)),[max(0,float(r['D_gap_percent'])) for r in d],'.',markersize=3,label='List + local improvement')
    axes[1].axhline(0,color='#247a68',label='Ordinary complete search F')
    axes[1].set_xlabel('Feasible paired case (frozen order)');axes[1].set_ylabel('Safe energy gap to E (%)');axes[1].legend(fontsize=8)
    fig.suptitle('Synthetic thermal effects and mature baselines; unsafe plans excluded from gaps');fig.tight_layout();fig.savefig(out/'thermal_and_gaps.png');plt.close(fig)
    selected=set(v for v in examples.values() if v)
    example_rows=[r for r in methods if r['case_id'] in selected]
    (out/'example_methods.json').write_text(json.dumps(example_rows,indent=2)+'\n',encoding='utf-8')
    if examples['thermal_energy_change']:
        cid=examples['thermal_energy_change'];traces=[]
        for line in (out/'selected_trajectories.jsonl').open(encoding='utf-8'):
            tr=json.loads(line)
            if tr['case_id']==cid and any(m in tr['methods'] for m in ['E','E0_no_thermal_constraint','D']):traces.append(tr)
        case=next(r for r in rows if r['case_id']==cid)
        fig,ax=plt.subplots(figsize=(9,4))
        # Rendering uses the stored analytical segment endpoints. Safety is not
        # inferred from these straight line display connectors.
        for tr in traces:
            ax.plot(np.array(tr['times_s'])*1000,tr['temperature_C'],'o-',markersize=3,label=', '.join(m for m in tr['methods'] if m in ['E','E0_no_thermal_constraint','D']))
        ax.axhline(45,color='red',linestyle='--',label='Synthetic limit 45 C')
        ax.set(xlabel='Time (ms)',ylabel='NPU aggregate temperature (C)',title=f'{cid}: first thermal-energy-change case (endpoints; exact segments in JSON)')
        ax.legend(fontsize=8);fig.tight_layout();fig.savefig(out/'first_thermal_case.png');plt.close(fig)
    result['analysis_plot_wall_s']=time.perf_counter()-tic
    (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'analysis_plot_wall_s':result['analysis_plot_wall_s'],'examples':examples}),flush=True)

if __name__=='__main__':
    import sys
    analyze(Path(sys.argv[1]))
