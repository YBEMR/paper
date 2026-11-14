"""Prepare explicit evidence/unknown registers. No fitted or synthetic numeric inputs."""
import csv,json
from pathlib import Path
R=Path(__file__).resolve().parent
def dump(name,x):(R/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
rows=[]
def add(i,quantity,state,evidence,why,required=True):rows.append({'id':i,'quantity':quantity,'state':state,'model_value':None,'required_for_numeric':required,'evidence':evidence,'why_not_identified':why})
add('platform_identity','同一板卡/软件/精度/模式身份','PARTIAL_AUTHOR_ARTIFACT','HaX: Xavier FP16、Orin INT8；README版本不一致','不能将无逐文件元数据的摘要统一认作Orin同一配置')
add('legal_support','固定任务的合法设备与GPU回退','PARTIAL_AUTHOR_ARTIFACT','HaX README prob层不能DLA；Orin构建启用GPU_FALLBACK','缺本轮任务纯设备支持/回退占用表；仅用抽象X/Y符号')
add('isolated_progress','同任务多有效OPP计算/访问进度','PARTIAL_AUTHOR_MEASUREMENT','10组GPU时长；DLA差分10项中3负','无有效频点轴；差分不能直接当任务工作时间')
add('memory_work','每任务实际访问字节和计算/访存重叠','UNKNOWN','HaX访存建模方法；OPTiC性能计数器方法','无本轮任务同频/同精度的字节与阶段数据')
add('bandwidth_curve','有效带宽B(f_EMC)','UNKNOWN','Orin官方确认EMC DVFS；25个峰值利用率百分比可读','百分比缺MHz与时间关联，不能等价GB/s曲线')
add('arbitration','两设备竞争仲裁/慢化关系','UNKNOWN','HaX使用PCCS；OPTiC XU3 GPU优先','模型形式/其他芯片优先级不能给出Orin同任务系数')
add('concurrent_progress','并发任务时长随计算/EMC有效频点变化','UNKNOWN','作者有并发性能结果与硬编码数组','无联合频率/温度/功率轴及可验证原始运行映射')
add('compute_power','任务/频点/等待状态下计算功率','UNKNOWN','OPTiC功率建模；RT-TAS固定CPU/GPU段功率','不能跨XU3/X1/Orin移植；等待/忙功率未知')
add('memory_power','EMC/DRAM功率随频率和流量变化','UNKNOWN','官方确认内存省电机制','未取得同平台功率曲线或同步总输入功率替代模型')
add('base_power','全窗口系统基础与待机功率','UNKNOWN','官方可观测功率接口','没有本轮同板卡待机/尾段输入功率')
add('power_boundary','分轨功率互斥边界与总输入一致性','UNKNOWN','tegrastats官方分轨定义','不能同时加总VDD_IN和已包含的CPU/GPU/内存轨')
add('thermal_dynamics','动态热容、热导/耦合、功率到节点映射','UNKNOWN','RT-TAS X1稳态系数；OPTiC RC形式','稳态热阻不识别热容，其他芯片系数不移植')
add('thermal_boundary','环境温度、初始状态与散热边界','UNKNOWN','RT-TAS实验关风扇','不能作为Orin统一散热条件；无同一次运行边界')
add('cap_map','温度到计算/EMC合法频率上限映射','OFFICIAL_MECHANISM_ONLY','L4T35.3.1确认热限制影响EMC DVFS','缺传感器、板级cap表；不把功率限制当温度反馈')
add('cap_timing','硬件进入/恢复、采样和确认延迟','UNKNOWN','文献和官方存在热管理','无同平台与日志匹配的完整状态机')
add('clock_transition','实际频率切换暂停/能量','UNKNOWN','官方允许调频','未取得时长和能量，不能默认零')
add('transfer_cost','层组跨设备转移时长/带宽/能量','PARTIAL_AUTHOR_MEASUREMENT','HaX 20项转移相关时长摘要','没有完整频点/能量与任务数据量配对')
add('fixed_service','固定N、工作量、精度、到达和期限','UNSET_DESIGN_INPUT','用户指定固定服务约束与两条链','仅冻结结构，不为产生效果自行填入负载数值')
add('common_horizon','共同服务窗口与尾段','UNSET_DESIGN_INPUT','用户要求完整计费','待与可行服务和热模型一起冻结，未沿用TF的24+10')
add('uncertainty','参数可信区域与测量/估计误差','UNKNOWN','当前公开资料不闭合','不能把任意±10%扰动称实测不确定性')
add('controller_cost','监测/决策额外系统能量','UNKNOWN','本轮未运行控制器','若后续计算复杂策略净收益需计开销；本轮不填零',False)
add('emc_observation','EMC百分比字段定义','OFFICIAL_MECHANISM_ONLY','tegrastats EMC X%@Y相对于当前运行频率','字段语义可用，但缺失频率不能补成有效带宽',False)
contract={'stage':'SMT20261114','status':'SYMBOLIC_ONLY_NOT_CALIBRATED','task_chains':[['A1','A2'],['B1','B2']],'resource_labels':['X','Y'],'shared_memory_resources':['M'],'numeric_template_count':None,'repetition_count':None,'empirical_platform_calibration':False,'synthetic_numeric_parameter_fills':0,'parameters':rows}
dump('parameter_contract.json',contract)
with (R/'parameter_identifiability.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
sources=[
 {'id':'HAX_PAPER','title':'Shared Memory-contention-aware Concurrent DNN Execution for Diversely Heterogeneous SoCs','year':2024,'doi':'10.1145/3627535.3638502','url':'https://mehmet.belviranli.com/papers/ppopp24.pdf','type':'PRIMARY_PAPER','scope':'Full text available; sections 3.1-3.4, 5 and artifact appendix inspected','boundary':'Performance/throughput; no matched thermal-energy parameter package obtained'},
 {'id':'HAX_CODE','title':'HaX-CoNN author artifact','year':2024,'url':'https://github.com/ismetdagli/HaX-CoNN/tree/87f5f25e6571ae04b577d1c38ddd241ffacab983','type':'PINNED_AUTHOR_ARTIFACT','scope':'105-entry tree; 54 text files fetched and hashed; static extraction, no author execution','boundary':'Summaries, metadata conflicts, fallback and negative derived differences retained'},
 {'id':'HAX_ARCHIVE','title':'HaX-CoNN Zenodo artifact','doi':'10.5281/zenodo.10225025','url':'https://doi.org/10.5281/zenodo.10225025','type':'PINNED_AUTHOR_ARCHIVE','scope':'Checksum-verified 7321491-byte ZIP; 135 members; 84 non-git regular worktree files','boundary':'Packed git history not exhaustively mined; no new joint trace in worktree'},
 {'id':'OPTIC','title':'OPTiC: Optimizing Collaborative CPU-GPU Computing on Mobile Devices With Thermal Constraints','year':2019,'doi':'10.1109/TCAD.2018.2873210','url':'https://www.comp.nus.edu.sg/~tulika/OPTiC.pdf','type':'PRIMARY_AUTHOR_MANUSCRIPT','scope':'2018 author version of 2019 publication; IV-B/C/D and V-D inspected; page7 visually checked','boundary':'XU3, compute thermal cap + memory contention already jointly modeled; fixed EMC; no full raw calibration obtained'},
 {'id':'RT_TAS','title':'Thermal-Aware Scheduling for Integrated CPUs-GPU Platforms','year':2019,'doi':'10.1145/3358235','url':'https://rtcl.eecs.umich.edu/rtclweb/assets/publications/2019/youngmoon-TECS-19.pdf','type':'PRIMARY_PUBLISHED_PDF','scope':'25-page final version; sections5-7; table2/setup page18 visually checked; 11-page draft retained separately','boundary':'Tegra X1 staged CPU/GPU tasks, configured65C and fan off; no memory-frequency contention calibration'},
 {'id':'ORIN_DVFS','title':'Jetson Orin power and performance, L4T r35.3.1','url':'https://docs.nvidia.com/jetson/archives/r35.3.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html','type':'OFFICIAL_MECHANISM','scope':'EMC frequency scaling policy, memory power management, thermal and interacting limits','boundary':'Board-specific table and thermal limits confirmed, instance-specific actual cap not identified'},
 {'id':'TEGRSTATS','title':'Tegrastats Utility r35.3.1','url':'https://docs.nvidia.com/jetson/archives/r35.3.1/DeveloperGuide/text/AT/JetsonLinuxDevelopmentTools/TegrastatsUtility.html','type':'OFFICIAL_FIELD_SEMANTICS','scope':'Web primary documentation, EMC percent/current-frequency and power fields','boundary':'Web-verified; no downloaded byte snapshot in 61-file manifest'},
 {'id':'JETPACK','title':'JetPack SDK 5.1.1','url':'https://developer.nvidia.com/embedded/jetpack-sdk-511','type':'OFFICIAL_VERSION_METADATA','scope':'Web primary metadata: L4T35.3.1, TRT8.5.2, CUDA11.4','boundary':'Does not repair unknown per-run metadata; no downloaded byte snapshot'}]
dump('source_registry.json',sources)
# Clarify the actual retrieval origin of PDFs reused from earlier caches.
manifest=json.loads((R/'source_manifest.json').read_text())
for item in manifest:
    if item['id'] in ['HaX_CoNN.pdf','OPTiC_author.pdf']:
        item['primary_url']=item['url'] if 'raw.githubusercontent' not in item['url'] else item.get('primary_url')
        name='2024_Dagli_HaX_CoNN.pdf' if item['id']=='HaX_CoNN.pdf' else '2018_Wang_OPTiC_author.pdf'
        item['url']='https://raw.githubusercontent.com/YBEMR/paper/92cd9f1702d96d4606bdacc921ff5d1fe4769c67/papers/'+name
dump('source_manifest.json',manifest)
print(json.dumps({'parameters':len(rows),'required_null':sum(x['required_for_numeric'] for x in rows),'source_entities':len(sources)}))
