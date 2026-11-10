"""Layout-only v3 from saved CSV; no kernel/evaluator import or call."""
import csv
from datetime import datetime,timezone
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path

OUT=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']='/tmp/evaluation_workpackages_matplotlib_v3'
os.environ['XDG_CACHE_HOME']='/tmp/evaluation_workpackages_fontcache_v3'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=OUT/'display_curves_AB_NPU0.csv';before=sha(source);curves={}
with source.open() as f:
    for row in csv.DictReader(f):curves.setdefault(row['curve_id'],[]).append((F(row['time_s']),F(row['T_lower_degC']),F(row['T_upper_degC'])))
refs=read(OUT/'frozen/C_reference_data.json')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,'legend.fontsize':8,'svg.fonttype':'none','pdf.fonttype':42})
fig,axes=plt.subplots(1,2,figsize=(8.2,3.8),layout='constrained');fig.suptitle('Fixed schedules: AB scenario, NPU0',fontsize=11)
colors={'75':'#D55E00','80':'#E69F00','85':'#0072B2','90':'#009E73'}
for period in ['75','80','85','90']:
    points=curves['startup_P'+period];axes[0].plot([float(t) for t,a,b in points],[float((a+b)/2) for t,a,b in points],label=f'P = {period} ms',color=colors[period],linewidth=1.35)
axes[0].axhline(80,color='#444444',linestyle='--',linewidth=.9,label='80°C limit');axes[0].axhspan(80,88,color='#D55E00',alpha=.05)
for period,time,position in [('75',1.575,(1.45,64.5)),('80',2.315,(2.25,64.5))]:
    witness=refs['startup_P'+period]['C_result']['violation_witness'];value=float(F(witness['temperature_degC'][0]));axes[0].scatter([time],[value],color=colors[period],marker='x',s=27,zorder=5)
    axes[0].annotate(f'P = {period} ms\nCertified violation point\n{time:.3f} s',xy=(time,value),xytext=position,textcoords='data',ha='center',va='center',fontsize=7,color='#333333',bbox={'boxstyle':'round,pad=.25','fc':'white','ec':'none','alpha':.88},arrowprops={'arrowstyle':'-','color':colors[period],'lw':.7})
axes[0].set(xlim=(0,3),ylim=(48,87),xlabel='Elapsed time (s)',ylabel='Temperature (°C)',title='(a) All-H startup from 50°C');axes[0].legend(loc='lower right',frameon=True);axes[0].text(.03,.96,'Above-limit continuation: model diagnostic',transform=axes[0].transAxes,va='top',fontsize=7,color='#8C3B00')
for template,color,style,width in [('All-H initial','#8064A2','-',1.5),('Enhanced HEFT final','#007F8B','-',2.0),('MILP final','#222222',(0,(5,3)),1.25)]:
    points=curves['steady_'+template.replace(' ','_')];axes[1].plot([float(t*1000) for t,a,b in points],[float((a+b)/2) for t,a,b in points],label=template,color=color,linestyle=style,linewidth=width)
axes[1].axhline(80,color='#444444',linestyle='--',linewidth=.9);axes[1].set(xlim=(0,90),ylim=(47,81),xlabel='Phase within period (ms)',ylabel='Temperature (°C)',title='(b) Periodic steady state, P = 90 ms');axes[1].legend(loc='center right',bbox_to_anchor=(.98,.55),frameon=True)
axes[1].text(.03,.05,'HEFT and MILP nearly coincide;\nno temperature offsets applied.',transform=axes[1].transAxes,fontsize=7,va='bottom')
for ax in axes:ax.grid(alpha=.2,linewidth=.5);ax.spines[['top','right']].set_visible(False)
for extension in ['png','svg','pdf']:fig.savefig(OUT/('AB_NPU0_startup_and_periodic_v3.'+extension),dpi=300)
plt.close(fig)
assert sha(source)==before
record={'utc':datetime.now(timezone.utc).isoformat(),'scope':'Visual layout only; fixed saved CSV temperatures and times unchanged','input_CSV_sha256':before,'new_original_kernel_calls':0,'new_search_calls':0,'changes':['Move right legend into empty middle area','Move both original-C witness text boxes into lower blank area; keep point locations exactly unchanged','No offsets or temperature scaling'],
    'v1_sha256':{e:sha(OUT/('AB_NPU0_startup_and_periodic.'+e)) for e in ['png','svg','pdf']},'v3_sha256':{e:sha(OUT/('AB_NPU0_startup_and_periodic_v3.'+e)) for e in ['png','svg','pdf']}}
with (OUT/'layout_v3_record.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print(str(OUT/'AB_NPU0_startup_and_periodic_v3.png'),flush=True)
