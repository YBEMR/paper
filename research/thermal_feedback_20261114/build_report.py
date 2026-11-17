"""Build presentation and evidence tables from existing results; no simulation."""
import base64,csv,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import markdown

R=Path(__file__).resolve().parent;O=R/'results';F=R/'figures';F.mkdir(exist_ok=True)
def read(name):return json.loads((R/name).read_text(encoding='utf-8'))
def writejson(name,obj):(R/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
P=read('design.json');S=read('results/scenario_summary.json');A=read('results/structural_audit.json');M=read('results/selected_methods.json');V=read('results/numerical_validation.json')

# Add the source-code evidence obtained after the initial artifact download.
manifest=read('source_manifest.json');tele=R.parent/'throttle_sources/sev/03_code/telemetry/telemetry_pipeline.py'
if tele.exists():
    data=tele.read_bytes();git=lambda b:hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();expected='29515b75248a818cddb24afdc5c117b927bca4e6'
    if git(data)!=expected and data.endswith(b'\n') and git(data[:-1])==expected:data=data[:-1];tele.write_bytes(data)
    assert git(data)==expected,'Telemetry source byte identity failed'
    new={'name':'sev/03_code/telemetry/telemetry_pipeline.py','url':'https://raw.githubusercontent.com/Aayush-Marasini/sustained-edge-vision/faddf01ffb3d1651f2b654faa77eaee59fbbde4a/03_code/telemetry/telemetry_pipeline.py','git_blob':expected,'original_path':'03_code/telemetry/telemetry_pipeline.py','kind':'sev','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'status':'CONNECTOR_FETCH_GIT_BLOB_VERIFIED'}
    manifest=[x for x in manifest if x['name']!=new['name']]+[new]
phoenix=R.parent/'sources/2026_Jeon_Phoenix.pdf'
if phoenix.exists():
    dat=phoenix.read_bytes();dest=R.parent/'throttle_sources'/phoenix.name
    if not dest.exists():shutil.copyfile(phoenix,dest)
    new={'name':phoenix.name,'url':'https://raw.githubusercontent.com/YBEMR/paper/92cd9f1702d96d4606bdacc921ff5d1fe4769c67/papers/2026_Jeon_Phoenix.pdf','kind':'pdf','bytes':len(dat),'sha256':hashlib.sha256(dat).hexdigest(),'status':'REUSED_PREVIOUS_DOWNLOAD_HASH_VERIFIED','extract_exit':0}
    manifest=[x for x in manifest if x['name']!=new['name']]+[new]
writejson('source_manifest.json',manifest)

rows=[]
def par(name,status,platform,value,source,limit):rows.append(dict(parameter=name,status=status,platform=platform,value=value,source=source,identifiability_limit=limit))
ref='SEV author commit faddf01ffb3d1651f2b654faa77eaee59fbbde4a'
par('temperature_and_inference_log','AVAILABLE','Raspberry Pi 5, FP32 YOLOv8n',{'static_runs':3,'telemetry_rows_each':3600},ref,'One preselected replicate per state, descriptive only; not heterogeneous')
par('reported_frequency_column_MHz','AVAILABLE','Raspberry Pi 5',[2400,1800,1500],ref,'scaling_cur_freq/request-related field; not calibrated effective clocks')
par('effective_frequency_time_series','UNKNOWN','Raspberry Pi 5',None,ref+' telemetry_pipeline.py; Linux CPUFreq docs','Flag set while reported MHz remains 2400; actual clocks unidentified')
par('hardware_trip_temperature','PARTIAL','Raspberry Pi 5',{'official_progressive_start_C':80,'official_further_limit_C':85},'Raspberry Pi official cooling guide','Not measured exact state-transition thresholds or universal single trip')
for name,platform,lim in [('hardware_release_hysteresis','same target SoC','Exact release, sampling and confirmation unavailable'),('actual_OPP_transition_time_and_energy','same target SoC','No aligned effective-frequency transition trace'),('runtime_power_by_effective_OPP','same target SoC','Requested-state aggregate is not effective OPP calibration'),('full_window_synchronized_input_power','Raspberry Pi 5','Raw PowerZ databases available on request; aggregate/filtered output only'),('CPU_GPU_NPU_same_model_support','same target SoC','No complete legal task support and precision table obtained'),('device_thermal_capacitance','same target SoC','Not independently identified from available data'),('ambient_conductance','same target SoC','Cooling boundary and synchronized heat input incomplete'),('cross_device_conductance','same target SoC','Single CPU log cannot identify two-resource coupling'),('transfer_and_memory_contention','same target SoC','No matched transfer/bandwidth contention costs'),('decision_monitoring_overhead','same target SoC','No measured whole-policy energy overhead')]:par(name,'UNKNOWN',platform,None,'Bounded primary/artifact audit, 2026-11-14',lim)
par('example_throttling','AVAILABLE_PLATFORM_SPECIFIC','Odroid XU3',{'reported_C':75,'CPU_before_MHz':2000,'CPU_after_MHz':900},'OPTiC author manuscript, section II','Evidence of mechanism only; no parameter transfer to XU4, Pi, Jetson or synthetic model')
for key in ['work','rates','arrivals','relative_deadline','main_horizon','tail','C','Genv','Gcouple','idle_power','active_base','dynamic_coefficient','leak_coefficient','external_power','trip','release','throttled_frequency','hardware_sample','frequency_transition_time','frequency_transition_energy','initial_requested_frequency','reactive_trip','reactive_release','dt']:
    par(key,'SYNTHETIC','abstract X/Y, dimensionless',P[key],'design.json frozen before simulation','Not hardware calibrated; value never inferred by combining platforms')
par('hardware_confirmation_delays','SYNTHETIC','abstract X/Y',{'entry':.2,'release':.5,'slow_case':[.5,1]},'design.json','Explicit sample-count semantics in MODEL.md')
par('scenario_region','SYNTHETIC','abstract X/Y',P['scenarios'],'design.json','Physically admissible sensitivity cases, not empirical uncertainty/confidence region')
writejson('parameter_identifiability.json',rows)
with (R/'parameter_identifiability.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows([{**x,'value':json.dumps(x['value'],ensure_ascii=False)} for x in rows])

plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':130,'svg.fonttype':'none'})
fig,(ax,bx)=plt.subplots(1,2,figsize=(13,5),gridspec_kw={'width_ratios':[1.35,1]})
y=np.arange(len(S));ax.barh(y,[s['catalogue_gain_pct'] for s in S],color='#236b8e',label='Best catalogue vs best constant template')
ax.scatter(np.zeros(len(S)),y,color='#c45c37',marker='D',s=22,label='Lookahead vs best one-switch plan',zorder=4)
ax.axvline(1,color='#555',linestyle=':',label='1% investment reference');ax.set(yticks=y,yticklabels=[s['scenario'] for s in S],xlabel='Whole-window energy improvement (%)',xlim=(-1,24));ax.invert_yaxis();ax.legend(loc='lower right',fontsize=8)
nom=[x for x in M if x['scenario']=='nominal'];chosen=[next(x for x in nom if x['method']==m) for m in ['cold_fixed_plus_hardware','safe_low_fixed','reactive_threshold','best_thermal_fixed','two_period_lookahead']]
bars=bx.bar(range(6),[x['energy'] for x in chosen]+[A['rows'][0]['energy']],color=['#ccc']*3+['#236b8e','#c45c37','#428b59'])
for i,x in enumerate(chosen):
    if not x['feasible']:bars[i].set_hatch('///');bx.text(i,x['energy']+1,'FAIL',ha='center',fontsize=8,color='#9b3434')
bx.set(xticks=range(6),xticklabels=['Cold\nfixed','Low\nfixed','Reactive\nfreq cap','Best\nconstant','2-period\nlookahead','Best\none-switch'],ylabel='Normalized energy, service + common tail',ylim=(0,57));bx.tick_params(axis='x',labelsize=8)
fig.suptitle('Synthetic fixed-service audit | one-switch plans close the entire observed gap',fontsize=13);fig.tight_layout();fig.savefig(F/'comparison.png',bbox_inches='tight');fig.savefig(F/'comparison.svg',bbox_inches='tight');plt.close(fig)

trace=next(x for x in read('results/selected_traces.json') if x['scenario']=='nominal');fig,axes=plt.subplots(3,1,figsize=(11,7.5),sharex=True)
colors=['#9a533a','#20658a','#438856'];seqs=[[10,10,10],[15,10,10],[15,15,15]];labels=['Cold fixed (infeasible)','One-switch = lookahead = catalogue','Best constant (feasible)']
for seq,col,label in zip(seqs,colors,labels):
    j=trace['sequences'].index(seq);rs=[r for r in trace['samples'] if r['trajectory']==j];t=[r['t'] for r in rs]
    axes[0].plot(t,[r['x'][0] for r in rs],color=col,label=label)
    axes[1].step(t,[r['actual'][0] for r in rs],where='post',color=col,alpha=.85)
    axes[2].plot(t,[r['energy'] for r in rs],color=col)
axes[0].axhline(1,color='#444',ls='--',lw=1,label='X hardware trip');axes[0].axhline(.8,color='#888',ls=':',lw=1,label='X hardware release');axes[0].legend(ncol=2,fontsize=9);axes[0].set_ylabel('Normalized X temperature')
axes[1].set_ylabel('X applied frequency');axes[1].set_ylim(.45,1.05);axes[2].set_ylabel('Cumulative normalized energy');axes[2].set_xlabel('Normalized time')
for ax in axes:
    ax.axvspan(24,34,color='#ddd',alpha=.45);ax.set_xlim(0,34)
    for z in [8,16,24]:ax.axvline(z,color='#aaa',lw=.7,ls=':')
fig.suptitle('Nominal case: hardware feedback changes feasibility and device allocation\nShaded interval: common idle tail; same 12 mandatory tasks',fontsize=12);fig.tight_layout();fig.savefig(F/'mechanism.png',bbox_inches='tight');fig.savefig(F/'mechanism.svg',bbox_inches='tight');plt.close(fig)

labels={'cold_fixed_plus_hardware':'冷态最优固定+硬件管理','safe_low_fixed':'固定最低频（非期限安全）','reactive_threshold':'简单反应式频率阈值','best_thermal_fixed':'实际反馈下最佳共同固定','two_period_lookahead':'两周期前瞻','catalogue_best':'4096目录最佳'}
mt='|方法|三次模板|完成任务/12|期限违约数|全窗能量|可行|\n|---|---|---:|---:|---:|---|\n'
for x in nom:mt+=f"|{labels[x['method']]}|{','.join(map(str,x['sequence_indices']))}|{x['complete_tasks']}|{x['deadline_misses']}|{x['energy']:.6f}{'（失败）' if not x['feasible'] else ''}|{'是' if x['feasible'] else '否'}|\n"
mt+=f"|事后最佳一次切换预排|15,10,10|12|0|{A['rows'][0]['energy']:.6f}|是|\n"
st='|冻结情景|目录可行数/4096|至少一次硬件trip的候选数|最佳序列|相对最佳共同固定节能%|前瞻相对一次切换节能%|\n|---|---:|---:|---|---:|---:|\n'
for s in S:st+=f"|{s['scenario']}|{s['feasible_catalogue']}|{s['any_hardware_trip_candidates']}|{','.join(map(str,s['catalogue_sequence']))}|{s['catalogue_gain_pct']:.3f}|0.000|\n"
report='''# 固定服务量下的热降频反馈：有限机制验证

**结论：热反馈能改变合成实例中的最低能耗可行安排；本轮没有继续开发复杂算法的必要证据。** 名义情景相对“每次重复使用同一个模板”的最佳固定安排节能20.6395%，但一个离线预排、至多切换一次模板的简单方案已达到相同质量。两周期前瞻相对该强简单类额外节能为0%。这些数值不是硬件实测。

真实数据方面，已核查6项近邻并复算公开Pi日志；有效频率、同步全窗功率、双资源执行支持与热参数未闭合。因此交付的是**未标定的条件机制实验及可辨识性报告**，不能称为真实SoC验证或已成立论文创新。

## 文献与数据结论

OPTiC已显式处理热降频下CPU/GPU共同执行时间；F-DTM有热预测、异构分配与实际速度反馈；Phoenix存在关闭早退出的完整骨干分配消融。目标不同不等于这些方法不能适配固定工作量能耗问题。HBTASP仅取得出版商预览，结论保留覆盖限制。[完整近邻对照与来源](EVIDENCE.md)。

Sustainable Edge Vision公开S0日志出现1910个节流标志样本，频率列却始终2400MHz；实现优先读取可能只代表请求P-state的scaling_cur_freq。原始外部功率也未公开。不能用单CPU数据拼接Jetson功率或假设NPU。真实未知量保持null，[可辨识性表](parameter_identifiability.csv)。

## 冻结实验口径

两条二节点链、两种抽象资源X/Y，每资源两档，固定三次重复、12任务、6完整服务；到达0/8/16，期限8/16/24；统一计费至34，含共同10单位尾段。非抢占、不迁移，实际频率随同一硬件迟滞、确认延迟和切换暂停改变，执行进度按实际处理率积分。13情景首次运行前冻结，全部保留；参数均无量纲合成。完整参数、动作、事件顺序、能量组成及解析条件见[MODEL.md](MODEL.md)、[PROTOCOL.md](PROTOCOL.md)、[design.json](design.json)。

主扫描61440条目录评价耗时40.313秒；另冷表和阈值执行。未开发MILP或新启发式，未扩大情景。无额外控制计算能量，因此任何收益首先是理想上界。

## 名义情景：变化在哪里

'''+mt+'''
模板10把A2交Y低档、B2交X高档；模板15把A2/B2都交Y高档，A1/B1仍在X。热反馈下，最佳序列从冷态10,10,10变成**15,10,10**：首周期把B2移到Y并提高Y请求频率，减轻X的连续忙负载；后两周期恢复能效较好的分配。任务执行中不迁移，也没有主动插空或改变优先级。

冷态固定在名义热模型中只完成11任务，第二周期B2结束于18.492>16；其低能耗不可作为节能分母。两周期前瞻完成12任务且满足期限，能量38.987072；每次同模板的最佳固定为49.126544。最优预排仍发生2次X硬件cap进入，受限忙时2.384615，说明最优并不等于完全避免节流。

关闭cap而保留温度、功率、到达与窗口的反事实：名义目录最佳回到10,10,10，能量33.181207且可行；15,10,10在同一反事实中能量38.501579。再打开cap，10,10,10违约。这支持“实际能力反馈改变安排”的条件机制，不是仅报告温度下降，也不是可部署的无热管理基线。

![完整能耗与强简单比较](figures/comparison.svg)

![名义机制轨迹](figures/mechanism.svg)

## 全部冻结情景与负结果

'''+st+'''
G×1.5时整个4096目录无硬件trip，保留该负结果；冷入口时最佳固定实际触发节流，但额外前瞻仍无收益。其余两个零收益情景为G×1.1的两个角点。9/13相对共同固定有收益只是已选情景计数，不代表真实设备发生概率。

**±10% G/C角点同时包含正收益与零收益；名义15,10,10原样迁移还会在G×.8及(.9,.9)角点违约。** 因而没有证明参数误差下统一有效，更没有实测不确定性下≥1%保证。逐情景最佳只是知道真实参数的参照。

## 强简单方法是否已经足够

事后从既有目录提取全部496种“至多一次模板切换”方案，13情景的最佳值全部等于4096目录最佳，也等于两周期前瞻。该检查未增加轨迹，但在看到结果后提出，不能冒充事先冻结验证。它证明当前有限实例不需要复杂在线算法；选择哪种预排仍依赖初始状态和参数，不是一个已部署的鲁棒策略。

本轮反应式只控制频率，不包含温度到设备映射；它的失败不能用于否定所有阈值方法。最低频也不自动满足期限，故保留失败。最强简单类的0%额外差距才是投资判断，20.64%不能写成“优于所有简单方法”。

## A/B/C/D判定与停止

- **A 参与性：是，但有完整无触发区域。** 名义2746/4096候选发生硬件trip；G×1.5全部不触发。
- **B 安排改变：是，条件成立。** 名义首周期改变B2设备和Y频率，实际能力积分造成可行性翻转；仅在合成三周期目录成立。
- **C 简单充分性：本轮是。** 一次切换预排已同等质量，复杂前瞻额外0%，未达到1%投入参考。
- **D 区域证据：不足以支持鲁棒部署。** 正例不止一个点，但±10%角点含零收益和冻结策略失效；该范围没有实测依据。

决定：停止本轮复杂算法投入；保留机制正例、零收益和失败区域，不恢复B或旧R1/ON-P。下一轮若另行授权，应先研究有效频率/功率可辨识性、简单设备映射阈值和多周期稳态是否仍有机会。没有新数据也可继续条件理论，但不能声称真实平台收益。

## 数值验证与复算

前置23检查、75项数值检查通过；7条独立标量实现轨迹一致。已选78策略在.01/.005步长下可行性不变，能量差最大0.217007%；未重扫细网格全目录，不声称连续最优。完整范围与11项推断风险检查见[REVIEW.md](REVIEW.md)。

复算需Python 3.12及requirements.txt依赖。先保留已发布results，再在副本目录执行：

```text
python preflight.py
python run_experiment.py
python validate_results.py
python structural_analysis.py
python build_report.py
```

主程序预算240秒、验证90秒，超时不自动扩预算。原始公开数据复核为可选独立步骤：`python download_sources.py`后`python audit_public_data.py`；下载固定作者工件，仅读取不执行作者控制代码。离线合成复算无需联网。`build_report.py`在无原始来源缓存时使用已归档来源清单和结果，图表不触发仿真。

GitHub以`results/candidates/`按情景分片保存全部61440行，`python assemble_candidates.py`可按索引与SHA256重建all_candidates.csv；本地复现ZIP同时提供聚合CSV与NPZ。NPZ也可由主程序生成。PDF、外部原始数据不重新分发。第三、四章和前三轮研究目录不改；本轮为独立`research/thermal_feedback_20261114/`。
'''
(R/'REPORT.md').write_text(report,encoding='utf-8')
readme='''# 热降频反馈：固定服务量机制验证（TF20261114）

入口：[结论与全部结果](REPORT.md) · [完整可读报告](report.html) · [近邻与原始数据审计](EVIDENCE.md) · [冻结模型](MODEL.md) · [质量与停止记录](REVIEW.md)

合成名义例中，考虑硬件降频使最优可行安排改变；相对每次同模板的最佳固定方案节能20.6395%。但事后最佳一次切换预排已达目录最优，前瞻额外0%；停止复杂算法投入。真实平台参数未辨识，不能称硬件收益。

`PROTOCOL.md`/`design.json`为运行前冻结；`structural_analysis.py`为事后、仅读取既有结果的强简单类审计。报告内有完整复算命令和数据范围。所有能量为归一化合成单位，失败候选能量不能与可行者计算节能率。`scenario_summary`的strong_simple仅指原六方法，请结合`structural_audit`读取最终结论。
'''
(R/'README.md').write_text(readme,encoding='utf-8')
parts=[('report',report),('evidence',(R/'EVIDENCE.md').read_text(encoding='utf-8')),('model',(R/'MODEL.md').read_text(encoding='utf-8')),('review',(R/'REVIEW.md').read_text(encoding='utf-8'))]
html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>固定服务量热降频反馈审计</title><style>body{max-width:1180px;margin:36px auto;padding:0 28px;color:#202b35;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif}h1{font-size:27px;color:#173e58}h2{font-size:21px;margin-top:36px;border-top:1px solid #ddd;padding-top:15px}table{border-collapse:collapse;display:block;overflow-x:auto;font-size:14px;margin:20px 0}th,td{border:1px solid #d4dbe0;padding:9px 11px;text-align:left;vertical-align:top}th{background:#eaf1f6}tr:nth-child(even){background:#f7f9fa}a{color:#176a8c}img{max-width:100%}code,pre{background:#f0f3f5}pre{padding:14px;overflow:auto}section{margin-bottom:70px}nav{background:#eaf1f6;padding:12px}</style><nav><a href="#report">结果</a> · <a href="#evidence">文献与可辨识性</a> · <a href="#model">冻结模型与解析条件</a> · <a href="#review">质量与停止</a></nav>'
for ident,body in parts:
    h=markdown.markdown(body,extensions=['tables','fenced_code'])
    for q in F.glob('*.png'):
        for ext in ['.png','.svg']:h=h.replace('src="figures/'+q.stem+ext+'"','src="data:image/png;base64,'+base64.b64encode(q.read_bytes()).decode()+'"')
    for old,new in [('EVIDENCE.md','#evidence'),('MODEL.md','#model'),('REVIEW.md','#review'),('REPORT.md','#report')]:h=h.replace('href="'+old+'"','href="'+new+'"')
    html+='<section id="'+ident+'">'+h+'</section>'
html+='</html>';(R/'report.html').write_text(html,encoding='utf-8')
print(json.dumps({'parameter_rows':len(rows),'source_files':len(manifest),'figures':4,'report_bytes':len(html.encode())}))
