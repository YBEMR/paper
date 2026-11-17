"""Build a self-contained Chinese report from the frozen run. Does not run experiments."""
import base64
import csv
import html
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
R = ROOT/'results'
def read(name): return json.loads((R/name).read_text(encoding='utf-8'))
analysis, summaries = read('analysis.json'), read('summary.json')
raw = [json.loads(x) for x in (R/'all_candidates.jsonl').read_text(encoding='utf-8').splitlines()]
full = {(x['id'],x['state']):x for x in raw if x['variant']=='full'}
env, checks = read('run_environment.json'), read('checks.json')
provenance = json.loads((ROOT/'repository_provenance.json').read_text(encoding='utf-8'))
escape = lambda x: html.escape(str(x))
def table(headers, rows, cls=''):
    return '<div class="table-scroll"><table class="'+cls+'"><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def link(url, label): return '<a href="'+html.escape(url,quote=True)+'">'+escape(label)+'</a>'
def cite(i): return '<a class="cite" href="#'+i+'">['+i+']</a>'
def num(x, n=6): return f'{x:.{n}f}'

literature = [
dict(id='L1',direction='A/C',paper='HaX-CoNN · PPoPP 2024',url='https://mehmet.belviranli.com/papers/ppopp24.pdf',scope='原文定向：§3.1、§3.4–3.5、实验；另审README、目录与layer_results.json。',objective='多DNN吞吐或最坏完成时延；非系统焦耳最小化。',decisions='合法层组映射与转换；共享内存争用进入慢化模型；Z3与动态D-HaX。',thermal_energy='有争用时延模型；未见显式温度状态/完整系统能量目标。',platform='Jetson Xavier/Orin、Snapdragon 865；不同评测的设备组合不同。',author_limit='工件README提示平台/软件版本变化需重新profile；不能说只支持静态调度。',boundary='用吞吐/时延有效建模不等于能量目标下最优。并发降速和附加功率需要分别测量。',hypothesis='同频率、同请求下，冷热入口是否改变最佳并发关系？缺匹配整机功率轨迹。'),
dict(id='L2',direction='A',paper='MEPHESTO · PACT 2020',url='https://doi.org/10.1145/3410463.3414671',scope='仓库原文提取：§3.2–3.3、§4–7。',objective='按给定energy-performance trade-off点优化归一化能量/完成时间。',decisions='映射及处理单元内次序；事件驱动剩余工作；TF/PF分别由算术强度拟合；DP启发式。',thermal_energy='已同时处理争用时间和功率因素；无显式温度RC、到达/期限与DVFS决策。',platform='Jetson Xavier CPU/GPU/PVA profiling；处理单元功率边界。',author_limit='CPU计数受限时用nvprof指标近似；更改功率上限需重新profile。',boundary='不是完全不考虑能耗的弱基线；并发PF可能下降而TF上升，不能预设功率必增。',hypothesis='固定工况争用表在另一温度/频率状态是否仍能正确排序？需包级能量与状态条件化验证。'),
dict(id='L3',direction='A/B',paper='IceEdge · 2026作者稿',url='https://www.cse.iitd.ac.in/~rijurekha/papers/tosn_2026.pdf',scope='原文定向：§3、§4、§5.3表2、§5.4；表2已渲染目视核对。期刊卷期/DOI占位未采信。',objective='在截止期/丢弃率约束下抑制持续推理温升，非完整系统能量最小化。',decisions='EDF、期限约束合批、至多两路GPU并发；温升反馈调频，在线并发profiling。',thermal_energy='显式反馈温度；GPU合批/并发与频率参与热控制。不能描述为无热模型。',platform='Jetson AGX Xavier、TVM；批1/4/8/12；长时温度评测。',author_limit='组合profiling困难、存在无并发收益配置；调度/控制开销与反馈周期需考虑。',boundary='允许丢请求，且未做可替代CPU/GPU/NPU映射；直接与全服务等精度策略比较会失真。',hypothesis='全请求服务下，加入实际整机能量与休眠状态，热相关批选择是否优于其公平适配及简单阈值？'),
dict(id='L4',direction='B',paper='Bao等 · Temperature-Aware Idle Time Distribution · TVLSI 2012',url='https://www.ida.liu.se/labs/eslab/publications/pap/db/minba_VLSI12.pdf',scope='原文定向：§IV–VIII，模型、SITD/DITD与实验。',objective='在已定次序/电压的周期任务中降低温度相关漏电与状态切换能量。',decisions='分配空闲；SITD迭代优化、DITD在线查表。',thermal_energy='RC温度、漏电、低功耗空闲与切换成本已联合考虑。',platform='单处理器模型与仿真。',author_limit='未核得需单列的作者自述失效结论；固定次序/电压是建模前提。',boundary='“热感知空闲节能”已经成立；不能将其作为本轮新贡献，也不能照搬文中高温场景。',hypothesis='真实端侧批效率和功率态共同作用是否带来新的可测批结构决策，而非已有空闲分配的改名？'),
dict(id='L5',direction='B',paper='Cheng等 · DATE 2016 / PBOO',url='https://past.date-conference.com/proceedings-archive/2016/pdf/0556.pdf',scope='作者原文：模型、PBOO、§VI-B与仿真实验。',objective='满足端到端期限下最小化峰值温度；不是能量最小化。',decisions='固定映射与频率、流水阶段ton/toff；梯度启发式。',thermal_energy='耦合RC/HotSpot与线性漏电；周期热状态。',platform='8核ARM与48核SCC模型仿真。',author_limit='§VI-B凸性以猜想提出，不能转述为已证明全局凸优化。',boundary='固定周期的峰温目标不能替代完整能耗评价；单轮冷启动不能代表稳态。',hypothesis='合批形成的休眠与周期入口反馈能否改变能耗最佳动作？须继承温度验证，当前未做。'),
dict(id='L6',direction='C',paper='Band · MobiSys 2022',url='https://changminjeon.com/publication/band/',scope='原论文定向：合法unit/subgraph、运行时、§6限制；发布工件核对。',objective='端侧多DNN调度的时延与服务表现。',decisions='由算子支持集构建合法单元/子图；动态路径与LST调度；在线profile更新。',thermal_energy='热关停处理器可被移出并恢复；非完整系统能量最小化。',platform='多款手机CPU/GPU/DSP/NPU；后端支持集决定合法性。',author_limit='§6明确把提前于降频的处理列为未来方向。',boundary='不能简化为固定分区、完全不感知热，再用事后温度过滤构造弱基线。',hypothesis='在已合法图上，提前热相关能量选择是否超过其在线重调度？先补足调用/迁移成本。'),
dict(id='L7',direction='C',paper='PELSI · RTCSA 2023',url='https://staff.science.uva.nl/a.d.pimentel/artemis/RTCSA23.pdf',scope='原文定向：建模、profile、切换、GA与实验；DOI 10.1109/RTCSA58653.2023.00011。',objective='时延约束下最小化单次推理能量。',decisions='逐层设备/频率、回归估计与切换处理，GA（使用NSGA-II实现）。',thermal_energy='含设备/频率切换、非活动单元低频；未见显式温度状态。',platform='RockPi N10/RK3399Pro的little/big/GPU；本优化不含NPU。入口INA260测板级能量。',author_limit='随机配置验证报告平均估计误差6.16–9.32%；该数不是严格误差界。',boundary='44.48%为FPS/W提升，不能直接写成能耗降低44.48%；不能删除切换成本。',hypothesis='同一合法目录中的温度相关排序变化能否超过已有估计误差，并优于最优固定映射/频率？'),
dict(id='L8',direction='C',paper='ADMS · arXiv 2025 / IEEE TMC 2026期刊版',url='https://arxiv.org/html/2503.21109v1',scope='仓库期刊原PDF定向：§III-B、运行时与§IV；网页链接为2025预印本，版本不能混同。',objective='多DNN自适应调度，评估性能及能效。',decisions='离线对模型/设备枚举ws=1..20、按平均时延选缓存；运行时按状态更新优先级。',thermal_energy='运行时监控温度、负载、频率；不能说框架没考虑热。',platform='移动异构设备，实验见期刊原PDF。',author_limit='未核得作者把ws温度适应明确列作限制；以下是选择准则的范围。',boundary='离线ws选择依据是平均时延，不等于按当前热状态选择完整能耗最佳粒度。',hypothesis='加入实际切分/搬运成本后，ws能量排序是否随温度变；仅改变优先级不构成该证据。'),
dict(id='L9',direction='C',paper='Maity等 · EMSOFT / TECS 2021',url='https://www.cse.iitk.ac.in/users/swarnendu/files/papers/thermal-emsoft21.pdf',scope='原文定向：§4–5、§7；DOI 10.1145/3477028。',objective='异构平台热管理与期限满足。',decisions='OpenCL工作组划为subtask，结合迁移/调频/空闲；粒度关联控制采样周期。',thermal_energy='明确讨论长子任务导致热恢复滞后、小子任务增加派发开销。',platform='Odroid XU4 / OpenCL；不等于任意NPU子图可切分。',author_limit='原文直接讨论粒度与控制开销矛盾；不能将这一矛盾称为首次提出。',boundary='工作组切分不是推理图融合边界；完整系统能量及实际NPU合法性仍须单独验证。',hypothesis='只有后端合法性和能量目标导致了可证明的新决策，才可能区别于已有粒度热控制。'),
dict(id='L10',direction='A/C邻近',paper='Phoenix · TECS 2026',url='https://doi.org/10.1145/3793860',scope='仓库期刊PDF定向：状态/动作/奖励、部署与实验；DOI网页受阻。',objective='时延与热降频延迟/温升的权衡；非等精度完整系统焦耳最小化。',decisions='RL共享全局状态，CPU线程/GPU/NNAPI、决策树部署与多出口。',thermal_energy='温度、频率、利用率及加速器慢化反馈；明确已有热相关调度。',platform='移动异构推理平台；具体后端能力取决于设备。',author_limit='加速器温度不可直接获取时使用慢化代理。',boundary='多出口可能改变服务精度；不能直接拿不同精度换取的收益比较固定精度任务。',hypothesis='若能量目标增加可测价值，应在相同精度/服务量下保留其热状态反馈公平比较。'),
dict(id='L11',direction='C邻近',paper='AxoNN · 2022',url='https://raw.githubusercontent.com/YBEMR/paper/92cd9f1702d96d4606bdacc921ff5d1fe4769c67/papers/2022_AxoNN_Energy-Aware_Execution_of_Neural_Network_Inference_on.pdf',scope='原PDF定向：能量预算、层转换与合法性。',objective='给定能量预算下优化推理时延。',decisions='GPU/DLA层映射，考虑层转换/融合成本；非DVFS联合问题。',thermal_energy='能量约束；当前核查未支持显式温度反馈结论。',platform='TensorRT异构后端；可切分边界受实际后端限制。',author_limit='未将未确认的作者自述局限填入；这里只使用可切分性与成本事实。',boundary='融合损失、转换成本并非本轮才发现；不能沿用任意cut假设。',hypothesis='温度是否改变合法图的能量排序，必须先取得同平台成本。'),
dict(id='L12',direction='B竞争风险',paper='Loudaros等 · MECC 2025',url='https://doi.org/10.1145/3721889.3721925',scope='仅出版商原始摘要可读，未获全文；不得作为精读结论。',objective='端侧推理能效（frames/J）。',decisions='摘要覆盖GPU频率、批大小、能效profile/学习以及greedy合批/适应等待。',thermal_energy='全文未读，不能断言没有温度模型。',platform='摘要涉及Xavier。',author_limit='未核实。',boundary='已经足以否定“合批+DVFS+等待此前无人做”；不能据摘要划定更细空白。',hypothesis='在立项前必须补读全文和成本/基线细节；当前创新性仍未闭合。'),
dict(id='L13',direction='B竞争风险',paper='BatchDVFS · TPDS工件',url='https://github.com/nabavinejad/BatchDVFS',scope='README/工件级；作者PDF访问受阻。main=f05286df4b228ac18d5e83c0e3d8a153d5a5c5fc。',objective='批处理与GPU功率控制。',decisions='动态batch与功率上限协同；README列出16个DNN及results目录。',thermal_energy='未完成全文/结果数据审计，不推断热模型缺失。',platform='具体实验条件须进一步核原文与结果文件。',author_limit='未核实。',boundary='不能声称公开批处理数据均不存在；当前缺的是与本轮温度/功率态匹配的实证闭环。',hypothesis='优先审计已有原始结果是否有时间戳、温度和包级功率；不足再考虑已拥有设备。')
]
(ROOT/'literature_matrix.json').write_text(json.dumps(literature,ensure_ascii=False,indent=2),encoding='utf-8')
with (ROOT/'literature_matrix.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(literature[0]));w.writeheader();w.writerows(literature)
audit = dict(date='2026-11-14 Asia/Shanghai',type='targeted evidence audit, not systematic review',sources=13,fulltext_targeted=11,abstract_or_artifact_only=2,
    search_boundary='从用户指定两份实验回顾、83篇文献笔记与papers目录定位近邻，再核查原文/作者站点/工件；未进行可宣称穷尽的跨库系统检索。',
    evidence='下载8份PDF并提取文本；另读MEPHESTO仓库原文提取与Cheng/Maity作者原文。所有全文条目均为针对关键章节的定向核查，不标为逐页精读完成。',
    pdf_structure_check='8份结构预检均因pypdf缺失为UNAVAILABLE，非PASS；pdftotext退出0。IceEdge表2另经页面图像核对。',
    unresolved=['Loudaros 2025全文未读','BatchDVFS全文与results未完成审计','没有匹配本轮条件的整机功率/温度原始轨迹','未做系统文献检索，不能证明不存在已有同问题方法'],
    interpretation='明确模型范围不等于作者承认缺点；候选研究空间均为本轮推断，未证明已有方法失效。')
(ROOT/'source_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')

figdir=ROOT/'figures'; figdir.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig, axes = plt.subplots(1,2,figsize=(11.5,4.0),gridspec_kw={'width_ratios':[1,1.55]})
deltas=[(full['B-22-11',t]['energy_J']-full['B-211-100',t]['energy_J'])*1000 for t in ['cool','warm']]
axes[0].bar(['40/40 C','60/60 C'],deltas,color=['#2a6382','#bd7148'],width=.5)
axes[0].axhline(0,color='#344155',lw=.8);axes[0].set_ylim(-1.7,1.7)
axes[0].set_ylabel('Energy(Q) - Energy(S), mJ')
axes[0].set_title('B: energy ranking reverses',loc='left',fontweight='bold')
for i,v in enumerate(deltas): axes[0].text(i,v+(.1 if v>0 else -.16),f'{v:+.4f}',ha='center',va='bottom' if v>0 else 'top')
ax=axes[1]
for yi,aid in [(1,'B-211-100'),(0,'B-22-11')]:
    action=next(x for x in read('actions.json') if x['id']==aid)
    row=full[aid,'cool']
    durations=json.loads((ROOT/'parameters.json').read_text())['B']['batch_duration_s']
    for st,b in zip(row['batch_starts_s'],action['batches']):
        length=durations[str(b)]*1000
        ax.broken_barh([(st*1000,length)],(yi-.23,.46),facecolors='#2a6382' if yi==1 else '#bd7148',edgecolors='white',linewidth=.8)
        ax.text(st*1000+length/2,yi,f'b={b}',ha='center',va='center',color='white',fontweight='bold')
for t in [0,50,100,150]: ax.axvline(t,color='#b9c4ca',lw=.7,ls=':')
ax.set_yticks([1,0],['S: 2+1+1','Q: 2+2']);ax.set_xlim(-5,255);ax.set_ylim(-.6,1.6)
ax.set_xlabel('Time (ms); dotted lines = request arrivals')
ax.set_title('Same 4 requests; legal in both states',loc='left',fontweight='bold')
fig.text(.5,.012,'Synthetic and uncalibrated | H = 0.4 s | adaptive gain over best common fixed action = 0.0595%',ha='center',fontsize=10,color='#435264')
fig.tight_layout(rect=[0,.055,1,1]);fig.savefig(figdir/'mechanism_screen.png',dpi=170);plt.close(fig)
image64=base64.b64encode((figdir/'mechanism_screen.png').read_bytes()).decode('ascii')

css='''
:root{--ink:#23313f;--muted:#586675;--accent:#205f7b;--line:#dce3e8;--paper:#fff;--bg:#eef2f4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.8 "Microsoft YaHei","PingFang SC",sans-serif}main{max-width:1180px;margin:30px auto;background:white;padding:48px 56px 60px;border-radius:10px}h1{font-size:31px;line-height:1.4;margin:9px 0 14px}h2{font-size:24px;margin:44px 0 14px;padding-top:8px;border-top:2px solid var(--line)}h3{font-size:19px;margin:26px 0 10px}p{margin:10px 0}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}.eyebrow{font-size:13px;letter-spacing:1px;font-weight:700;color:var(--accent)}.meta,.small{font-size:13px;color:var(--muted)}.box{border-left:4px solid var(--accent);background:#eff6f9;padding:17px 22px;margin:20px 0}.warning{background:#fcf5ed;border-color:#b66d36}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0}.card{border:1px solid var(--line);border-radius:7px;padding:15px 18px}.card b{display:block;font-size:20px;color:var(--accent)}.table-scroll{overflow-x:auto;margin:16px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.65}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#edf3f6;color:#234c60;font-weight:700}tr:nth-child(even)td{background:#fafbfc}.matrix{min-width:970px;table-layout:fixed}.matrix th:nth-child(1){width:15%}.matrix th:nth-child(2){width:24%}.matrix th:nth-child(3){width:25%}.matrix th:nth-child(4){width:36%}code,pre{font-family:Consolas,monospace;font-size:13px}code{overflow-wrap:anywhere}pre{white-space:pre-wrap;background:#f4f6f8;padding:18px;border-radius:6px;line-height:1.7}img{display:block;max-width:100%;height:auto;margin:20px auto}ul,ol{padding-left:24px}li{margin:6px 0}.cite{font-size:12px;margin-left:4px}details{border:1px solid var(--line);padding:12px 16px;margin:16px 0}summary{cursor:pointer;font-weight:600}.formula{font-family:Consolas,"Microsoft YaHei",monospace;background:#f3f6f8;padding:14px 18px;overflow-x:auto}.stamp{display:inline-block;border:1px solid #b8ccd7;color:#205f7b;border-radius:4px;padding:2px 8px;font-size:12px}.source{scroll-margin-top:20px}.nowrap{white-space:nowrap}
@media(max-width:760px){main{margin:0;padding:24px 18px;border-radius:0}h1{font-size:25px}.grid{grid-template-columns:1fr}.card b{font-size:18px}h2{font-size:21px}}
@media print{body{background:white;font-size:10pt}main{margin:0;max-width:none;padding:0}h1{font-size:22pt}h2{font-size:16pt;break-after:avoid}h3{break-after:avoid}table{font-size:8pt}.matrix{min-width:0}tr,img,.box{break-inside:avoid}details{display:block}.table-scroll{overflow:visible}a{color:inherit}pre{font-size:8pt}}
'''
parts=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>端侧异构热感知调度：研究方向评估与最小机制实验</title><style>'+css+'</style></head><body><main>',
'''<div class="eyebrow">研究方向评估 · 第一轮交付 · 2026-11-14</div>
<h1>端侧异构多核热感知高能效调度<br>方向筛选与最小机制实验</h1>
<p class="meta">对应论文题目：《面向端侧异构多核平台的热感知高能效任务调度研究》<br>本轮状态：文献定向核查完成；A/B轻量合成筛选完成；C未运行；尚未启动硬件、大规模求解或新算法开发。</p>
<div class="box"><strong>决策：暂不确立新论文主线。唯一继续事项是B方向的同平台参数与可测效应审计。</strong><p>B在合成模型中出现冷/热批次结构翻转，但相对两态共同最佳固定方案仅节能<strong>0.0595%</strong>。A未出现最佳并发关系翻转；C缺合法分区与完整成本。不能把微小合成正例、已有机制组合或温度曲线变化写成已成立的创新。</p></div>
<div class="grid"><div class="card"><b>A · 需要补证</b>争用导致串行更省能，但热状态没有改变最佳并发关系。</div><div class="card"><b>B · 仅继续参数审计</b>2＋1＋1 → 2＋2；数学机制成立，现实价值未证。</div><div class="card"><b>C · 暂缓</b>合法切分和调用/搬运成本不足，近邻文献已覆盖关键矛盾。</div></div>
<p class="small">全部性能、功率、RC及休眠数值均为 <strong>SYNTHETIC_UNCALIBRATED</strong>。1224条是有限候选评价行，不是1224个独立实验；没有真实设备节能结论。</p>
<p class="small">导航：<a href="#history">历史与边界</a> · <a href="#literature">文献矩阵</a> · <a href="#protocol">三个协议</a> · <a href="#results">实际结果</a> · <a href="#decision">决策</a> · <a href="#next">唯一下步</a> · <a href="#repro">复现与SHA</a></p>
<h2 id="history">1. 旧研究提供什么，不能证明什么</h2>
<p>第三章已有任务依赖、异构设备、离散DVFS、共享频域、四节点RC与完整窗口电热评价。R1正式A/B/C采用相同初解1.084886371304 J，最终为0.860728789677 / 0.860647236548 / 0.860642651063 J，约改善20.66%；均因时间上限停止、gap约13%，不是全局最优证明。C相对B仅再降约4.585 μJ，两级约简尚未证明稳定的端到端加速。</p>
<p>第四章形成I1安全初始化、ON阻塞反馈联合重构与ON-P结构预筛；部分新实例确有节能。但U系50°C入口下已报告最高约70.3236°C，低于80°C温限，主要收益不能归因于热约束。78°C入口的C01存在4个超温见证，但最终ON热组增量为0。固定排程周期复核9组中7安全、2超温，属于后验检验，未建立通用周期保证。</p>
<p>可复用的是完整服务窗口、共同物理评价、合法性与分项守恒的思想。并发争用、合批与后端合法划分需要新的数据和动作模型，不能用原R1或ON-P的既有收益替代。本轮没有运行或修改旧实验，也没有重写第三、四章正文。</p>''']
parts.append(table(['历史材料','本轮使用的固定提交与来源'],[[escape(x['name']),link(x['url'],'原仓库材料')+'<br><code>blob '+escape(x['blob_sha'])+'</code>'] for x in provenance['sources']]))
parts += ['''<h2 id="literature">2. 三方向文献对照与证据边界</h2>
<p>从仓库两份回顾、83篇阅读笔记与文献目录定位近邻，核查13项来源：11项做了原文关键章节定向核对，2项仅达到原始摘要/工件级。不是逐页精读全部论文，也不是穷尽性系统综述。下表把作者明确表述、模型适用范围和我们的待验假设分开；“某项未建模”本身不能证明存在有价值的研究空白。</p>''']
litrows=[]
for x in literature:
    litrows.append(['<div id="'+x['id']+'" class="source"><b>'+x['id']+' · '+escape(x['direction'])+'</b><br>'+link(x['url'],x['paper'])+'<p class="small">'+escape(x['scope'])+'</p></div>',
        '<b>目标</b> '+escape(x['objective'])+'<br><b>动作/方法</b> '+escape(x['decisions']),
        '<b>模型</b> '+escape(x['thermal_energy'])+'<br><b>平台</b> '+escape(x['platform']),
        '<b>作者表述/核查边界</b> '+escape(x['author_limit'])+'<br><b>模型范围及公平对照</b> '+escape(x['boundary'])+'<br><b>本轮待验假设</b> '+escape(x['hypothesis'])])
parts.append(table(['论文与阅读级别','问题、目标和方法','热/能耗及平台','限制、误读风险与可证伪空间'],litrows,'matrix'))
parts += ['<h3>可直接使用的现实证据</h3><p>IceEdge表2的(4,4)并发组合，单独时延和为49.97 ms，最终并发profile为33.19 ms；(4,8)则从78.36 ms变为124.12 ms。并发可能改善也可能恶化完成时间，不能用单独时延和作为普适上界。这是时延证据，不能转写成整机功率或能耗参数。'+cite('L3')+'</p>',
    '<p>HaX-CoNN工件已审README、递归目录及layer_results.json，得到层时延/转换/EMC相关表；在<strong>已审范围</strong>内未找到与热入口匹配的包级能量曲线。BatchDVFS的README列有results目录，尚未完成其原始数据审计，不能宣称公开数据不存在。'+cite('L1')+cite('L13')+'</p>',
    '<p>上述证据支持研究矛盾的现实可能性，但还没有闭合“温度 → 最佳动作变化 → 完整系统节能 → 超过强简单基线”的证据链。B的最新合批能效近邻全文仍缺，创新性判断必须保留。'+cite('L12')+'</p>',
'''<h2 id="protocol">3. 冻结的最小机制实验与C补证协议</h2>
<p>先冻结参数与成功/失败标准，再执行。A/B均采用完全可枚举目录，不调用MILP、MATLAB、CPLEX或Gurobi；不调温限、不搜索极端入口、不扫描参数寻找大百分比。以下“合法”仅指合成目录内部合法，不能替代真实后端验证。</p>''']
parts.append(table(['方向','输入与比较','机制识别 / 消融','成功与失败'],[
['<b>A：初温改变最佳并发关系？</b>','两完整任务X/Y，均允许抽象CPU或GPU。4映射×2首任务次序×7启动偏移，共56参数化动作（40条唯一事件表）；完全并发、部分重叠、串行；相同250 ms期限。','full；常量漏电；状态无关仿射漏电对照；去争用。所有规划结果原样回full评价，保留全部并列最优。先固定映射区分并发效应，再看跨映射。','冷/热最优关系不同，且共同固定最佳动作有损失才支持核心假设。只有一般串行节能、温度不同、微小次序变化均不足。'],
['<b>B：初温改变最佳批结构？</b>','同模型同精度4请求，到达0/50/100/150 ms，相对期限250 ms；固定GPU，FIFO连续分组，batch仅1/2/4，每批等待仅0/20 ms，共46动作。立即执行、固定批大小、有限动态合批。','full；常量漏电；无批效率；无sleep。输出的批结构/等待回full重新执行，不修复；比较跨冷热共同选出的最佳固定方案。入口40/40、60/60、60/40°C。','最优结构集合不相交、共同固定方案有超过数值误差的损失，且同服务量/期限。量级很小、DPM不真实、收益仅来自批效率时不能升级为实际价值。'],
['<b>C：初温改变最佳合法划分？</b>','最多3种真实合法图：整体、有限切分、较细切分；同模型/权重/精度。每段至多2个已证支持设备，记录数据布局、同步、调用、搬运、融合损失和编译生命周期。','固定图下最佳映射/频率、温度无关规划、禁迁移/调频；无搬运成本只能作诊断，最终全部回含成本模型。保留Band/PELSI已有能力。','完整能耗最优图随温态变且超出全部切换成本/误差才通过。只变映射、不变图不算。缺合法分区或成本即停止；本轮未运行，详细协议见PROTOCOL_C.txt。']]))
parts += ['''<h3>共同物理与计量边界</h3>
<div class="formula">Cᵢ dTᵢ/dt = −Gᵢ,env(Tᵢ−Tₐ) − Gcouple(Tᵢ−Tⱼ) + Pbase,ᵢ + Pdynamic,ᵢ + Pleak,ᵢ(Tᵢ) + Pswitch,ᵢ<br>
E = ∫₀ᴴ [Pexternal + Σᵢ(Pbase,ᵢ + Pdynamic,ᵢ + Pleak,ᵢ + Pswitch,ᵢ)] dt<br>
Pleak,ᵢ = gstate · Lᵢ,40 · exp[β(Tᵢ−40)]；awake时gstate=1，sleep时0.15。</div>
<p>两个被动耦合RC节点，动态/基础/漏电/唤醒热量注入本地节点，外部常量仅计系统能量。主窗统一为0.4 s，包括全部空闲和尾段；所有full候选另接10 s相同空闲动作。每个请求均完成，不丢帧、不早退出，不用完成时刻截断计量。A全窗awake；B的CPU全窗awake，GPU按预定间隙进入合成sleep。</p>''']
parts.append(table(['参数组（均为自设合成值）','数值与单位','解释 / 边界'],[
['热网络','Tₐ=25°C；C=[1.25,2.4] J/K；Genv=[0.25,0.20] W/K；Gcouple=0.04 W/K','无耦合近似时间常数5/12 s；不是实测拟合。'],
['温度及功耗','入口[40,40]、[60,60]、[60,40]°C；上限80°C；L40=[0.15,0.20] W；β=0.035/K','温度可能在窗口内冷却；热状态指入口温度，不暗示每轮都自发升温。'],
['基础与休眠','awake=[0.15,0.20] W；sleep=[0.03,0.03] W；外部0.30 W；sleep漏电系数0.15','≥10 ms间隙可sleep；唤醒1 ms、额外1 mJ。进入sleep瞬时且零额外代价，是明确理想化。'],
['A任务性能','X CPU/GPU=110/50 ms、2.5/4 W；Y=60/80 ms、3/3.5 W','跨设备重叠时进度率0.8，各节点附加0.15 W；结束重叠恢复独占速率。并非HaX-CoNN实测数值。'],
['B批性能','batch1/2/4：40/65/110 ms，动态4/5/7 W','单请求动态能量分别0.160/0.1625/0.1925 J；合批没有被假设为动态能量必降。潜在优势来自压缩awake时间。'],
['数值','DOP853 rtol=1e−9、atol=1e−11；并列容差1e−7 J','事件分段；主窗峰温≤1 ms取样。只称数值采样可行，不称连续安全证书。']]))
parts += ['''<h3>一个应先排除的无效机制</h3>
<p><strong>状态无关仿射漏电下，初温可能完全不改变能耗排序。</strong>若每个候选s均满足 Ṫ=A T+bₛ(t)，且A对所有候选相同；系统功率为cₛ(t)+ℓᵀT，ℓ固定；比较窗口H相同，动作时序不随初温变，可行域也不因初温改变，则：</p>
<div class="formula">Eₛ(T₀) = Kₛ + ℓᵀ [∫₀ᴴ exp(At)dt] T₀<br>所以 Eₛ(T₀)−Eᵣ(T₀)=Kₛ−Kᵣ，与T₀无关。</div>
<p>证明只用线性系统解的叠加；这是本轮用于排除错误实验预期的推导，不主张为新定理。温限活跃、非线性漏电、动作相关的门控/电压漏电斜率、热降频改变执行时长或反馈策略都可能破坏前提，但不会自动保证翻转。A的仿射对照验证了不变排序；B的功率态门控本身已破坏“所有候选同一A/ℓ”的前提，不能把B效应全归为指数非线性。</p>
<h2 id="results">4. 已完成实验：结果与反例</h2>''']
parts.append('<p>实际完成 <strong>1224条候选评价</strong>：A为56×3入口×4模型=672，B为46×3×4=552。共102个参数化动作；A去重后40条事件表。耗时'+num(env['elapsed_s'],2)+' s。全部原始可行/不可行行均保存；没有剔除负结果。</p>')
parts.append('<img alt="B合成能量排序翻转和两种批处理时间线" src="data:image/png;base64,'+image64+'">')
parts += ['''<h3>4.1 A：争用可使错开更省能，但热没有改变最佳并发关系</h3>
<p>完整模型下三个入口均选择X在GPU、Y在CPU，X先开始、Y在120 ms开始，串行而非重叠。56个动作全部满足主窗期限与采样温限。以下固定同一映射，避免把设备选择收益混作并发收益：</p>''']
arows=[]
for aid,label in [('A-10-0-0','完全并发'),('A-10-0-2','40 ms偏移'),('A-10-0-3','60 ms偏移 / 串行'),('A-10-0-6','120 ms偏移 / 主窗最优')]:
    c,w=full[aid,'cool'],full[aid,'warm']
    arows.append([label+'<br><code>'+aid+'</code>',num(c['completion_s']*1000,1),num(c['dynamic_J']),num(c['energy_J']),num(w['energy_J']),num(c['peak_C'],4)+' / '+num(w['peak_C'],4)])
parts.append(table(['动作','完工 / ms','动态 / J','冷态总能量 / J','温态总能量 / J','冷 / 温峰温 °C'],arows))
parts += ['''<p>完全并发比串行多耗约0.1065 J，主要对应争用拉长的动态执行与附加功率，不能归因为热感知。串行从60 ms偏移推迟到120 ms，在冷态仅再省42.477 μJ。常量漏电规划有8个并列最优，其中已包含full最优；回放冷态差距范围0–50.587 μJ、温态0–100.400 μJ。不能挑一个较差并列解就宣称非热方法必然损失。</p>
<p><strong>主窗冷/热共同固定最佳动作与逐态最佳动作相同，热适应收益=0。</strong>仿射对照和去争用诊断也没有改变这一结论。移除温限后最优不变；热可行域没有筛掉任何full动作。</p>
<h3>4.2 B：批次结构确实翻转，但强固定基线已吃掉几乎全部收益</h3>
<p>令S=批次(2,1,1)、额外等待(20,0,0) ms；Q=批次(2,2)、额外等待(20,20) ms。两者都完成相同4请求且满足期限。S只唤醒1次，GPU awake共146 ms；Q唤醒2次，awake共132 ms，少14 ms。CPU入口单独升到60°C时仍选S，表明该实例的转折主要在GPU局部功率态/漏电权衡。</p>''']
brows=[]
for aid,label in [('B-1111-0000','立即执行'),('B-22-00','固定batch2、零额外等待'),('B-211-100','S：2＋1＋1'),('B-22-11','Q：2＋2'),('B-4-0','一次batch4')]:
    c,w=full[aid,'cool'],full[aid,'warm']
    brows.append([label+'<br><code>'+aid+'</code>',num(c['completion_s']*1000,1),num(c['energy_J']),num(w['energy_J']),('满足' if c['feasible'] else '<b>首请求超期</b>'),num(c['peak_C'],4)+' / '+num(w['peak_C'],4)])
parts.append(table(['方案','完工 / ms','冷态总能量 / J','温态总能量 / J','期限','冷 / 温峰温 °C'],brows))
energyrows=[]
for state,tag in [('cool','冷态'),('warm','温态')]:
    for aid,label in [('B-211-100','S'),('B-22-11','Q')]:
        r=full[aid,state]
        energyrows.append([tag+' '+label]+[num(r[k],9) for k in ['dynamic_J','base_J','leakage_J','switching_J','energy_J']])
parts.append(table(['入口/方案','动态 / J','基础含空闲 / J','温度漏电 / J','唤醒增量 / J','总能量 / J'],energyrows))
parts += ['''<p>Q−S：冷态为<strong>+1.222559 mJ</strong>，温态为<strong>−1.196072 mJ</strong>；最优结构发生翻转。44/46个动作满足期限，两种batch4动作因首请求超期不参与排名。所有full记录峰温不超过60°C、距80°C温限至少20°C，移除温限不改变最优；这不是靠温限排除候选制造的翻转。</p>
<div class="box warning"><strong>必须使用的主比较：</strong>在冷/热两态等权条件下，先共同选出最佳固定动作S，其总能量为2.010219068 J；逐态已知最佳动作的离线参照为2.009022996 J，只少0.001196072 J，即<strong>0.0594996%</strong>。这还是不扣在线监测与决策开销的理想参照，不能据此主张实际节能。</div>
<p>即时执行和固定batch2可作诊断，但不是足够强的唯一基线。未知真实冷热占比时，这个百分比也不能代表日常节能率。全部到达已知、只枚举0/20 ms等待的离线最优，不是连续动作全局最优或已实现在线调度器。</p>
<h3>4.3 消融全部回到同一个full模型评价</h3>
<p>以下范围包含每个消融模型的<strong>所有并列最优动作</strong>，而非事后挑选有利的一项。改变时长的规划只输出原批结构/等待或映射/偏移，随后在完整模型重新执行。</p>''']
abrows=[]
vnames={'constant_leak':'常量漏电','affine_control':'仿射漏电','no_interference':'无争用','no_batch_efficiency':'无批效率','no_sleep':'无sleep'}
for x in summaries:
    if x['state'] not in ['cool','warm'] or x['variant']=='full': continue
    opt=next(y for y in summaries if y['direction']==x['direction'] and y['state']==x['state'] and y['variant']=='full')['best']['energy']
    abrows.append([x['direction']+' / '+('冷' if x['state']=='cool' else '温'),vnames[x['variant']],str(len(x['best']['ids'])),num(x['replay_full_energy_min'],9)+'–'+num(x['replay_full_energy_max'],9),num(1000*(x['replay_full_energy_min']-opt),6)+'–'+num(1000*(x['replay_full_energy_max']-opt),6)])
parts.append(table(['方向 / 入口','规划模型','并列动作数','回full能量范围 / J','比full最优多耗 / mJ'],abrows))
parts += ['''<p>B的常量漏电在冷热入口都给相同4个并列动作，温态回full均劣于Q。禁用sleep后各入口都选单请求批次，没有本轮主结果中的批结构翻转；去批效率也不再出现冷热不同的最优集合。这支持“批时长、有效低功耗态与温度敏感功率的共同作用”，不支持“合批天生省电”或“任何端侧GPU都能实现相同机制”。</p>
<h3>4.4 窗口敏感性与空闲计量</h3>''']
tailrows=[]
for aid,label in [('B-211-100','S'),('B-22-11','Q'),('A-10-0-6','A：X先 / 120ms'),('A-10-1-6','A：Y先 / 120ms')]:
    tailrows.append([label,num(full[aid,'cool']['extended_energy_J'],9),num(full[aid,'warm']['extended_energy_J'],9)])
parts.append(table(['动作','0–10.4 s冷态 / J','0–10.4 s温态 / J'],tailrows))
parts += ['''<p>B延长计量后仍冷态选S、温态选Q，排除了这个有限续接窗内的排序反转风险。A冷态延长窗最优变为Y先执行，微省7.665 μJ；温态仍X先，优势仅0.764 μJ。A的映射与串行关系没有变化，不能拿这种微小先后次序翻转宣称“热选择性并发”已经证实。有限10 s不是无限期冷却或周期稳态保证；热状态仍须在连续运行中继承。</p>
<p>另外对306条full记录补做互斥分项：每个设备按计算、清醒空闲、休眠、唤醒归类，分别保存基础、动态、漏电和切换能量；外部0.3 W单列。各项相加与原记录最大差8.88×10⁻¹⁶ J。该表在 <code>results/energy_accounting.csv</code>，没有把CPU空闲能量藏在GPU活动能量之外，也没有重复计费。</p>
<h3>4.5 B的可测门槛，比复杂算法更值得先做</h3>
<p>Q相比S多5 mJ动态能量、1 mJ唤醒增量，但GPU少14 ms清醒。暂把温度冻结为T，可得近似：</p>
<div class="formula">ΔE(T) = E_Q−E_S ≈ 0.006 − 0.014 × [0.17 + 0.85 × 0.2 × exp(0.035(T−40))] J</div>
<p>该合成表达式在约<strong>51.98°C</strong>过零。它揭示可检验条件：额外计算/切换代价，是否被缩短清醒时间带来的基础与温度敏感功耗节省抵消。51.98°C只是冻结温度近似下的<strong>自设参数阈值</strong>，不是RC精确转折点，更不是任何实际GPU的控制温度；没有围绕这个阈值扫描或调参。</p>
<h3>4.6 数值可信度不等于物理真实性</h3>''']
parts.append(table(['核查','结果','能支持什么'],[
['两节点RC被动性、请求/工作量、资源及事件守恒','检查通过','评价器内部基本一致。'],
['A仿射对照：冷热初温能量偏移的跨候选跨度','1.55×10⁻¹⁵ J','符合上面的排序不变性推导。'],
['仿射矩阵指数独立计算 vs ODE','最大差6.66×10⁻¹⁶ J','交叉检查线性对照实现。'],
['30条主窗紧容差 / 更密采样复核','能量最大差8.88×10⁻¹⁶ J；峰温2.84×10⁻¹⁴°C','此次实例的数值误差远小于mJ差值；不提供一般误差上界。'],
['8条关键10s续接：Radau对照','能量最大差6.22×10⁻¹⁵ J','排查积分器造成的微小排序假象。'],
['物理测量、统计显著性、周期/连续热安全','未完成 / 不适用','没有硬件误差条、置信区间或连续安全证明；不能外推。']]))
parts += ['''<h2 id="decision">5. 方向决策：三个均未达到论文主线准入</h2>''']
parts.append(table(['筛选问题','A：选择性并发','B：动态合批/空闲','C：划分粒度'],[
['现实矛盾','强：争用时延与功率已有实证；本轮缺热条件化整机能量。','强：合批、门控、等待与温度漏电均有依据；具体组合需要实证。','强：合法性、搬运/融合成本与控制粒度真实存在。'],
['热是否改变决策','主窗最佳并发关系未变；尾窗仅微小次序变化。','合成最优批结构变化，非温限过滤；异构设备联合决策尚未测。','未识别；没有合法分区成本，未模拟。'],
['前人具体边界','HaX目标性能；MEPHESTO已有争用能耗，但缺本轮状态/系统边界。不能直接断言其失败。','IceEdge有热合批；Bao有热空闲能耗；最新能效合批全文未闭合。竞争强。','Band有热反馈、PELSI有切换能耗、Maity有粒度热控制；简单组合不足。'],
['最小验证','负/弱结果；合成争用收益不能冒充热收益。','数学正例，但最佳共同固定基线只差0.0595%，投入价值低。','证据缺失；避免任意cut伪实验。'],
['数据/实现成本','需要同平台并发时延、包级功率、频率和温度；不确定性较高。','可先审计少量batch1/2与功率态日志，成本最低；真实sleep可能不可控。','后端合法图、融合损失、搬运/调用成本采集负担最高。'],
['本轮处置','<b>需要补证，暂不主选</b>。不继续扩合成并发扫描。','<b>值得仅继续参数审计</b>。未批准算法主线或硬件实验。','<b>暂缓</b>。仅有合法成本表后再重启。']]))
parts += ['''<p>现在给B排第一，仅指下一单位验证工作的价值最高，不代表新颖性、硬件可行性或硕士论文可完成性已通过。若真实效应被误差覆盖或简单阈值已足够，停止复杂算法路线本身就是有效筛选结论。无需从三个选项中硬选一个成功。</p>
<h2 id="next">6. 下一步唯一推荐：B的同平台参数与可测效应审计</h2>
<p><span class="stamp">PROPOSED_NOT_EXECUTED</span> 先审已有设备资料/公开原始日志；未自动启动硬件测量、购买设备或长时间求解。完整执行协议保存在 <code>NEXT_PROTOCOL.txt</code>。</p>
<ol>
<li><strong>先查准入：</strong>同模型、同精度、batch1/2在目标后端真实可用；有效休眠可观测。CPU调用返回不等于GPU/NPU已休眠。若论题仍是异构调度，还必须有两个合法执行设备，或有可调度CPU预/后处理的完整链；单GPU合批不足以支撑主线。</li>
<li><strong>建立可测表：</strong>固定一个模型，记录batch1/2时长与整机能量、清醒/休眠差、唤醒代价、温度/频率/风扇轨迹。只能测整机功率时直接积分，不能臆造分域漏电。优先用现存工件，缺字段时先提交明确采集方案。</li>
<li><strong>预设小验证：</strong>自然冷稳态与日常持续负载后的温态各一组；相同请求序列、精度和期限。比较S/Q、立即执行、跨两态共同最佳固定方案、温度阈值切换，以及可公平适配的原生合批/DVFS策略。先做每态10次交错配对的先导，按噪声预先锁定正式样本量，不照搬合成52°C。</li>
<li><strong>控制归因：</strong>先在同频率区间核验差值，完整计入监测、等待、切换及尾闲；增加固定续接窗和连续多轮温度继承。温度无关/相关规划在同一保留实测条件复评。另一请求序列或第二模型用于检验可迁移性。</li>
<li><strong>通过门槛：</strong>能量差符号可靠反转，超过测量联合不确定度；完整开销后优于共同固定方案。建议把“至少1%系统能耗改善且高于3倍重复性误差”作为后续算法投入门槛，或另行证明重要可行性收益。这是本项目建议，可在采集前调整，不是文献定理。</li>
<li><strong>停止条件：</strong>真实sleep无效、无热相关排序、噪声覆盖差值、牺牲吞吐/精度、缺异构决策，或简单阈值已追平。不要继续调合成参数放大百分比。</li>
</ol>
<p>只有通过后才讨论章节：第三章建立有限合法批结构/设备/功率态目录和小规模严格参照；第四章检验有限状态或滚动调度是否优于阈值控制。方法由问题决定，不预先指定MILP或ON-P。旧连续热安全证明仅在模型与假设一致时迁移。</p>
<h2 id="repro">7. 独立记录、复现与交付</h2>
<p>研究在独立本地Git仓库 <code>research-screening</code> 中开展，没有向远程仓库写入，也不声称本地提交是原仓库分支的后代。下列固定快照用于背景/数据溯源。</p>''']
parts.append(table(['原仓库分支','实际核查SHA'],[[escape(x['branch']),'<code>'+x['sha']+'</code>'] for x in provenance['branches']]))
parts.append(table(['本轮记录','SHA / 信息'],[
['参数与协议冻结','<code>7b498d6d10c83a775d4b755b38a57d769006f75b</code>'],
['主运行执行代码','<code>284cfda6cb070f3307df2c759cce5d4131c86df0</code>'],
['最终交付快照','见复现包 <code>delivery_manifest.json</code> 的 <code>delivery_commit</code>；附 <code>study_history.bundle</code> 可恢复本地历史。'],
['参数SHA256','<code>'+env['parameters_sha256']+'</code>'],
['执行源码SHA256','<code>'+env['code_sha256']+'</code>'],
['环境','Python '+env['python']+' / numpy '+env['numpy']+' / scipy '+env['scipy']+'；'+env['platform']],
['主运行成本',num(env['elapsed_s'],2)+' s；120 s软上限；无随机种子/无随机采样。']]))
parts += ['''<h3>复现包内容与步骤</h3>
<p>报告、参数、协议、代码、全部原始候选结果、分项能量、所有消融回放、数值验证、文献矩阵、源文件哈希、实验回顾快照与Git历史一并交付。论文PDF全文不打包，仅保留原始来源与校验清单。</p>
<pre>git clone study_history.bundle recovered-study
cd recovered-study
python screen.py              # 重算有限候选，建议在复制目录进行
python analyze.py             # 从原始结果生成摘要
python tail_audit.py           # 8条续接积分交叉核查
python energy_accounting.py    # 补充分设备阶段能耗
python report_builder.py      # 只读结果、生成图和本报告</pre>
<p>主程序需Python/numpy/scipy；作图另需matplotlib。较慢机器可能触发120 s软上限，保留中间结果后停止，不自动放大预算。原始CSV中应按<code>direction/state/variant</code>筛选；不能把消融模型自身的能量直接拿来当共同full物理收益。<code>summary.json</code>保存全部并列解与回放范围。</p>
<details><summary>24个方向 / 入口 / 模型组合的完整摘要</summary>''']
allrows=[]
for x in summaries:
    allrows.append([escape(x['direction']+' / '+x['state']+' / '+x['variant']),str(x['feasible'])+'/'+str(x['candidates']),num(x['best']['energy'],9),'<code>'+escape(', '.join(x['best']['ids']))+'</code>',num(x['replay_full_energy_min'],9)+'–'+num(x['replay_full_energy_max'],9)])
parts.append(table(['组合','可行/候选','本模型最佳 / J','全部并列动作','回full范围 / J'],allrows))
parts += ['''</details><h3>执行差异、未闭合事项与AI辅助披露</h3>
<p>冻结协议写“事件表示去重”，实际原始输出保留56个A参数化动作；分析另核实40条唯一事件表，未把重复行作为独立样本，也没有改写冻结协议。主运行后增加了能耗分项及8条续接交叉审计，没有新增入口或调参。详见<code>EXECUTION_NOTES.txt</code>。</p>
<p>八份PDF的结构预检因本地缺pypdf记为<code>UNAVAILABLE</code>，不是PASS；文本提取均成功，涉及关键数字的IceEdge表2另做页面目视核对。全文核查采用章节/表号定位，未伪造页级读取认证。最新合批近邻全文、匹配整机功率数据、真实功率态、周期长期运行和异构合批决策仍未闭合。</p>
<p>本轮由同一AI助手进行检索、原文核查、代码与报告编写及自审；没有独立专家、多模型审稿或真实硬件实验。<code>REVIEW.txt</code>保存自审项。报告中的新假设、阈值推导和方向排序属于分析建议；原文事实与本轮生成数值在矩阵和原始结果中分开保存。</p>
<p class="small">交付定位：第一轮研究方向筛选记录。当前证据允许继续B的参数审计，不允许宣称已找到新算法贡献或实际平台节能效果。</p>
</main></body></html>''']
report='\n'.join(parts)
(ROOT/'report.html').write_text(report,encoding='utf-8')
assert len(raw)==1224 and len(summaries)==24 and checks['pass']
assert abs(analysis['B']['adaptive_gain_percent']-0.05949957224613001)<1e-10
print(json.dumps(dict(report_bytes=len(report.encode('utf-8')),literature_rows=len(literature),candidate_rows=len(raw),summary_groups=len(summaries)),ensure_ascii=False))
