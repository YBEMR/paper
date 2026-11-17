"""Publication-style static plots of saved results, without rerunning simulation."""
import csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','axes.titleweight':'bold'})
summary=json.loads((OUT/'interpretation.json').read_text(encoding='utf-8'))
cfg=json.loads((ROOT/'design.json').read_text());data=np.load(OUT/'all_candidate_arrays.npz',allow_pickle=False)
ci=next(i for i,s in enumerate(cfg['scenarios']) if s['id']==cfg['nominal_id']);T=data['temperatures'];nom=summary['overview']['main_0.4s']['nominal'];e=data['energy'][ci,0];oracle=np.min(np.where(data['feasible'][ci,0],e,np.inf),axis=0)
fig,axs=plt.subplots(2,2,figsize=(13,8.8),layout='constrained')
ax=axs[0,0];x=np.linspace(0,2,301);low=.014*(.17+.17*x*np.exp(.035*(25-40)))*1000;high=.014*(.17+.17*x*np.exp(.035*(75-40)))*1000
ax.fill_between(x,0,low,color='#dcecf7',label='Q 全温区较优');ax.fill_between(x,low,high,color='#91c7bb',label='S→Q 翻转区');ax.fill_between(x,high,20,color='#f0dfc7',label='S 全温区较优')
ax.plot(x,low,color='#316c9b',lw=1);ax.plot(x,high,color='#896039',lw=1);ax.scatter([1],[6],color='#172c45',zorder=4,s=36);ax.annotate('名义合成点',(1,6),xytext=(1.1,4.6))
ax.set(xlim=(0,2),ylim=(0,20),xlabel='温度相关功率幅值倍数 α（自设）',ylabel='额外成本 K（mJ）',title='A  固定温度近似：连续参数关系')
ax.legend(loc='upper left',frameon=False,fontsize=9)
ax=axs[0,1]
ax.plot(T,(e[nom['fixed_index']]-oracle)*1000,label='共同最佳固定',color='#9f5c3d',lw=2)
for key,label,color in [('SQ','S/Q 单阈值','#377ca8'),('two_action','任意两动作单阈值','#208976')]:
    p=nom[key];ix=np.where(T<p['threshold_C'],p['left_index'],p['right_index']);ax.plot(T,(e[ix,np.arange(len(T))]-oracle)*1000,label=label,color=color,marker='o',ms=3,lw=1.5)
ax.axhline(0,color='#777',lw=.8);ax.set(xlabel='初始温度（°C）',ylabel='相对逐温度目录最优的能量差（mJ）',title='B  名义参数：主窗中简单策略的剩余空间');ax.legend(frameon=False)
ax=axs[1,0]
rr=list(csv.DictReader((OUT/'dynamic_corner_sign_envelope.csv').open()));rr=[r for r in rr if r['horizon']=='main_0.4s'];lo=np.array([float(r['sampled_corner_min_Q_minus_S_J'])*1000 for r in rr]);hi=np.array([float(r['sampled_corner_max_Q_minus_S_J'])*1000 for r in rr]);acts=json.loads((OUT/'catalogue.json').read_text());ids=[a['id'] for a in acts]
ax.fill_between(T,lo,hi,color='#d4dde9',label='16 个假设参数角点包络（非实测误差）');ax.plot(T,(e[ids.index('B-22-11-on')]-e[ids.index('B-211-100-on')])*1000,color='#208976',lw=2,label='名义参数');ax.axhline(0,color='#333',ls='--',lw=.8)
ax.set(xlabel='初始温度（°C）',ylabel='Q − S 能量（mJ）',title='C  批成本等参数的不确定性可改变排序');ax.legend(frameon=False,loc='upper right',fontsize=9)
ax=axs[1,1];overview=summary['overview'];vals=[overview['main_0.4s']['max_oracle_gain_pct'],overview['common_tail_10.4s']['max_oracle_gain_pct']];bounds=[overview['main_0.4s']['max_distribution_free_grid_bound_pct'],overview['common_tail_10.4s']['max_distribution_free_grid_bound_pct']]
pos=np.arange(2);ax.bar(pos-.17,vals,width=.32,color='#208976',label='均匀温度权重：最高理想收益');ax.bar(pos+.17,bounds,width=.32,color='#a7bccf',label='任意网格权重：保守上界')
for xx,v in zip(list(pos-.17)+list(pos+.17),vals+bounds):ax.text(xx,v+.015,f'{v:.4f}%',ha='center',fontsize=9)
ax.axhline(1,color='#a2463d',ls='--',lw=1.4);ax.text(.5,1.02,'1% 研究投入参考',ha='center',color='#a2463d');ax.set(xticks=pos,xticklabels=['0.4 s 主窗','10.4 s 共同延长窗'],ylim=(0,1.13),ylabel='相对共同最佳固定方案的节能（%）',title='D  67 个预定情景均未达到 1%');ax.legend(frameon=False,loc='upper left',bbox_to_anchor=(0,.90),fontsize=9)
fig.suptitle('B 参数区域与稳健性｜条件化合成分析，非 AGX 标定结果',fontsize=16,fontweight='bold')
fig.savefig(ROOT/'region_summary.png',dpi=180)
fig.savefig(ROOT/'region_summary.svg')
plt.close(fig)
print('Saved region_summary.png and SVG')
