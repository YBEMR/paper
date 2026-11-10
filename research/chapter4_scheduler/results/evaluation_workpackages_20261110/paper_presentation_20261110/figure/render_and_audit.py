"""Read saved plotting receipts, audit, export point CSV and paper figure."""
from collections import Counter
import csv
from datetime import datetime,timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[5];sys.path.insert(0,str(OUT))
from figure_core import signature,validate_coverage
from run_figure_points import verify
read=lambda p:json.loads(p.read_text())
def save(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    plan=read(OUT/'plan.json');identity=read(OUT/'plan_identity.json')['sha256'];verify(plan,identity);summary=read(OUT/'point_run01/summary.json');instance=read(OUT/'frozen/input_instance.json');reference=read(OUT/'frozen/C_reference_data.json');checks=[];raw={};point_rows=[];curves={}
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    check('exactly ten bounded calls',summary['complete_all_calls'] and summary['actual_original_kernel_calls']==10 and summary['wall_s']<1200)
    for result in summary['results']:
        case=result['case'];name=case['id'];power=read(OUT/'frozen'/case['power_file']);receipt=read(OUT/'point_run01'/(name+'_receipt.json'));raw[name]=receipt
        validate_coverage(power['fine_segments'],case['window_ms'])
        check(name+': full model/domain',receipt['complete'] and F(receipt['covered_until_s'])==F(case['window_ms'])/1000 and all(F(receipt['minimum_degC'][n][0])>=20 and F(receipt['peaks_degC'][n][1])<=100 for n in instance['platform']['node_order']))
        for index,row in enumerate(power['coarse_segments']):
            children=[s for s,p in zip(power['fine_segments'],power['fine_parent_indices']) if p==index]
            check(name+': exact split '+str(index),sum(F(s['duration_ms']) for s in children)==F(row['duration_ms']) and all(signature(s)==signature(row) for s in children))
        points=[{'time_s':'0','temperature_degC':{node:[value,value] for node,value in zip(instance['platform']['node_order'],case['entry_degC'])}},*receipt['trace']]
        check(name+': endpoint horizon',F(points[0]['time_s'])==0 and F(points[-1]['time_s'])==F(case['window_ms'])/1000)
        check(name+': <=2ms dense point gaps',all(0<F(b['time_s'])-F(a['time_s'])<=F(1,500) for a,b in zip(points,points[1:])))
        check(name+': bounded point count',len(points)<=case['maximum_trace_points_including_initial'])
        for point in points:
            for node,iv in point['temperature_degC'].items():point_rows.append({'case_id':name,'panel':case['panel'],'template':case['template'],'period_ms':case['period_ms'],'side':case.get('side','actual_start50'),'time_s':point['time_s'],'node':node,'T_lower_degC':iv[0],'T_upper_degC':iv[1]})
        raw[name+'_points']=points
        if case['panel']=='startup':
            curves[name]={'times':[F(v['time_s']) for v in points],'lower':[F(v['temperature_degC']['NPU0'][0]) for v in points],'upper':[F(v['temperature_degC']['NPU0'][1]) for v in points]}
            ref=reference[name]['C_result'];w=ref['violation_witness']
            if w:
                matched=next(v for v in points if F(v['time_s'])==F(w['global_time_s']));iv=matched['temperature_degC']['NPU0'];check(name+': old certified point remains over80',F(iv[0])>80 and F(iv[1])>=F(w['temperature_degC'][0]));check(name+': same old witness value display consistency',abs((F(iv[0])+F(iv[1]))/2-F(w['temperature_degC'][0]))<F(1,100000000))
    for template in ['All-H initial','Enhanced HEFT final','MILP final']:
        key='steady_'+template.replace(' ','_');lo=raw[key+'_lower_points'];hi=raw[key+'_upper_points'];check(key+': identical sample times',[v['time_s'] for v in lo]==[v['time_s'] for v in hi]);times=[F(v['time_s']) for v in lo]
        lower=[F(v['temperature_degC']['NPU0'][0]) for v in lo];upper=[F(v['temperature_degC']['NPU0'][1]) for v in hi];check(key+': ordered periodic point bounds',all(a<=b for a,b in zip(lower,upper)));curves[key]={'times':times,'lower':lower,'upper':upper}
        ref=reference[key]['C_result'];cert_hi=F(ref['periodic_bounds']['peak_by_node_degC']['NPU0'][1]);check(key+': samples consistent with old continuous envelope',max(upper)<=cert_hi+F(1,1000000000))
    with (OUT/'raw_plot_points_all_nodes.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(point_rows[0]));w.writeheader();w.writerows(point_rows)
    display_rows=[]
    for key,curve in curves.items():
        for t,a,b in zip(curve['times'],curve['lower'],curve['upper']):display_rows.append({'curve_id':key,'time_s':str(t),'node':'NPU0','T_lower_degC':str(a),'T_upper_degC':str(b),'display_midpoint_degC':float((a+b)/2)})
    with (OUT/'display_curves_AB_NPU0.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(display_rows[0]));w.writeheader();w.writerows(display_rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,'legend.fontsize':8,'svg.fonttype':'none','pdf.fonttype':42})
    fig,axes=plt.subplots(1,2,figsize=(8.2,3.8),layout='constrained');fig.suptitle('Fixed schedules: AB scenario, NPU0',fontsize=11)
    colors={'75':'#D55E00','80':'#E69F00','85':'#0072B2','90':'#009E73'}
    for period in ['75','80','85','90']:
        curve=curves['startup_P'+period];x=[float(v) for v in curve['times']];y=[float((a+b)/2) for a,b in zip(curve['lower'],curve['upper'])];axes[0].plot(x,y,label=f'P = {period} ms',color=colors[period],linewidth=1.35)
    axes[0].axhline(80,color='#444444',linestyle='--',linewidth=.9,label='80°C limit');axes[0].axhspan(80,88,color='#D55E00',alpha=.05)
    for period,time,offset in [('75',1.575,(-25,25)),('80',2.315,(-35,-33))]:
        w=reference['startup_P'+period]['C_result']['violation_witness'];value=float(F(w['temperature_degC'][0]));axes[0].scatter([time],[value],color=colors[period],marker='x',s=27,zorder=5);axes[0].annotate(f'C-certified point\n{time:.3f} s',xy=(time,value),xytext=offset,textcoords='offset points',fontsize=7,arrowprops={'arrowstyle':'-','color':colors[period],'lw':.7})
    axes[0].set(xlim=(0,3),ylim=(48,87),xlabel='Elapsed time (s)',ylabel='Temperature (°C)',title='(a) All-H startup from 50°C');axes[0].legend(loc='lower right',frameon=True);axes[0].text(.03,.96,'Above-limit continuation: model diagnostic',transform=axes[0].transAxes,va='top',fontsize=7,color='#8C3B00')
    styles=[('All-H initial','#8064A2','-',1.5),('Enhanced HEFT final','#007F8B','-',2.0),('MILP final','#222222',(0,(5,3)),1.25)]
    for template,color,style,width in styles:
        curve=curves['steady_'+template.replace(' ','_')];axes[1].plot([float(v*1000) for v in curve['times']],[float((a+b)/2) for a,b in zip(curve['lower'],curve['upper'])],label=template,color=color,linestyle=style,linewidth=width)
    axes[1].axhline(80,color='#444444',linestyle='--',linewidth=.9);axes[1].set(xlim=(0,90),ylim=(47,81),xlabel='Phase within period (ms)',ylabel='Temperature (°C)',title='(b) Periodic steady state, P = 90 ms');axes[1].legend(loc='upper right',frameon=True)
    axes[1].text(.03,.05,'HEFT and MILP nearly coincide;\nno temperature offsets applied.',transform=axes[1].transAxes,fontsize=7,va='bottom')
    for ax in axes:ax.grid(alpha=.2,linewidth=.5);ax.spines[['top','right']].set_visible(False)
    for extension in ['png','svg','pdf']:fig.savefig(OUT/('AB_NPU0_startup_and_periodic.'+extension),dpi=300)
    plt.close(fig)
    caption='''固定调度下AB场景NPU0的温度变化。左图将原全H模板按75、80、85和90 ms周期连续重复，从50°C初温传播至3 s，轮间继承末温；标记给出工作包C已经确证的两个超温点，不表示温度首次穿越80°C的精确时刻。越限后的曲线表示未实施关停或热保护策略的固定模型诊断轨迹，仅在原模型声明的20–100°C有效范围内展示。右图比较90 ms周期下全H模板、增强HEFT终解和MILP终解的周期稳态轨迹，初态采用C所包围的周期入口状态，不从50°C重新启动。HEFT与MILP曲线接近重合，未人为偏移温度。所有曲线均由原四节点模型传播得到，图中仅显示AB/NPU0；不代表其他场景或节点。曲线连接最大间隔2 ms的区间采样点中值，插值线及图形最大点不替代连续峰温包围或安全证明；连续安全和违规结论仍引用工作包C的原证据。原调度时间表、频档、物理参数及80°C温限保持，新增绘图采样不构成新调度优化。'''
    with (OUT/'caption.md').open('x') as f:f.write(caption+'\n')
    with (OUT/'caption.tex').open('x') as f:f.write('\\caption{'+caption.replace('°C',r'$^\circ$C')+'}\n')
    verify(plan,identity)
    audit={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'assertion_count':len(checks),'checks':checks,'actual_original_kernel_calls':summary['actual_original_kernel_calls'],'raw_vector_points_including_initial':sum(v['raw_trace_vector_points'] for v in summary['results']),'raw_all_node_point_rows':len(point_rows),'display_point_rows':len(display_rows),'postprocessing_new_kernel_calls':0,'no_temperature_offsets':True,'C_evidence_unchanged':True,'raw_kernel_states':dict(Counter(v['raw_receipt_state'] for v in summary['results']))}
    save(OUT/'figure_audit.json',audit)
    files={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='figure_manifest.json'};save(OUT/'figure_manifest.json',{'completed_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':identity,'files_sha256':files,'original_kernel_calls':10,'new_scheduling_calls':0,'pushed':False,'merged':False});print({'figure_png':str(OUT/'AB_NPU0_startup_and_periodic.png'),'audit_assertions':len(checks),'raw_points':audit['raw_vector_points_including_initial']},flush=True)

if __name__=='__main__':main()
