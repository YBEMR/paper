"""Render the descriptive report from audited search records; no simulation."""
import json,sys
from fractions import Fraction as F
from pathlib import Path

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def number(x,d=3):return '未知' if x is None else f'{float(x):.{d}f}'
def joules(e):return number(F(e['upper']),9) if e else '—'
def main(root):
    d=read(root/'results/analysis.json');slots=d['slots'];pairs=d['pairs'];c=d['quality_counts']['C'];b=d['quality_counts']['B']
    labels={'STRICT_LOWER':'严格降低','STRICT_HIGHER':'严格升高','EXACT_SAME_INTERVAL':'区间完全相同',
      'OVERLAP_NO_CERTIFIED_ORDER':'重叠：未证实严格顺序','FEASIBILITY_ONLY':'只比较可行性'}
    lines=['# 同等300秒总预算下的ON-P认证增量受控搜索','',
      f"**完整可用SAFE：{d['eligible_SAFE']}/12。C相对A：{c.get('STRICT_LOWER',0)}根严格降低、{c.get('STRICT_HIGHER',0)}根严格升高、{c.get('EXACT_SAME_INTERVAL',0)}根区间完全相同。** 所有结论按最终完整SAFE能量区间给出，候选数量不是节能代理量。",'',
      'A：原完整评价；B：仅整场景复用；C：整场景复用＋严格同路径前缀检查点。三臂均运行原ON-P搜索，保留原完整候选哈希缓存。','',
      '用户授权固定U07—U10、每根A/B/C各一次、300秒根预算及180秒原I1初始化准入；顺序U07 ABC、U08 BCA、U09 CAB、U10 ACB。原ON-P、物理模型、工作量、精度和输入参数保持，不重做MILP、不扩例、不自动追加运行。','',
      '[执行前冻结](https://github.com/YBEMR/paper/commit/239f1a49fb6f5dedbaf511af9c91fb8ce1be65fc)；[统计接口修复及授权续跑冻结](https://github.com/YBEMR/paper/commit/eae1ed96407422ec09ae66d9ac74d89e4a1803ad)。原搜索基线0de4d191966294dc673c21ed244616f1b5a6a85c，增量内核基线52c3370e76a235ab4a328d136912c2ee7bb4186d。','',
      '## 1. 最终能耗与可行性','',
      '|根|臂|原终止状态|完整可用SAFE|初解能耗上界J|最终能耗上界J|最终证据形成s|搜索严格接纳次数|',
      '|---|---|---|---|---:|---:|---:|---:|']
    for r in slots:
        lines.append(f"|{r['case']}|{r['arm']}|{r['status']}|{r['eligible']}|{joules(r.get('initial_energy'))}|{joules(r.get('final_energy'))}|{number(r.get('final_formed_s'))}|{r.get('strict_search_improvements','—')}|")
    lines+=['','J是原合成电热模型下固定服务量的完整能耗；运行秒数/内存MiB是本机搜索开销，两者不作换算。表中只为显示取小数，排序与接纳使用原精确区间；完整有理数端点位于results/analysis.json和各槽原始回执。每臂从自身初始化开始，初解不同仍可作同预算端到端比较，但不能全部归因为初始化后的搜索。','',
      '|根|比较|区间判定|保守节能下界%|初始候选相同|初始能量区间相同|最终候选相同|',
      '|---|---|---|---:|---|---|---|']
    for p in pairs:
        saving=p.get('saving_percent_interval',[None])[0]
        lines.append(f"|{p['case']}|{p['arm']}/{p['reference']}|{labels[p['kind']]}|{number(saving,6)}|{p.get('same_initial_candidate','—')}|{p.get('same_initial_energy','—')}|{p.get('same_final_candidate','—')}|")
    lines+=['','保守节能区间按[1−新上界/参照下界，1−新下界/参照上界]计算。若任一方没有完整可用SAFE，不给能耗百分比；区间重叠不按打印数值宣布优劣。零收益、劣化和初解变化全部逐根保留，不用四根平均值掩盖方向差异。','',
      '## 2. 相同预算下实际做了什么','',
      '|根/臂|方法计费s|进程墙钟s|初始化交接s|评价调用|SAFE/热违规/未决/中断|完整哈希命中|新增面板|极值调用|峰值工作集MiB|',
      '|---|---:|---:|---:|---:|---|---:|---:|---:|---:|']
    for r in slots:
        st=r.get('returned_states',{});memory=(r.get('memory') or {}).get('peak_rss_bytes')
        lines.append(f"|{r['case']}/{r['arm']}|{number(r.get('method_charged_s'))}|{number(r.get('process_wall_s'))}|{number(r.get('initialization',{}).get('returned_at_s'))}|{r.get('evaluation_attempts','—')}|{st.get('SAFE','—')}/{st.get('THERMAL_VIOLATION','—')}/{st.get('UNRESOLVED','—')}/{st.get('INTERRUPTED','—')}|{r.get('full_hash_hits','—')}|{r.get('physical_panels','—')}|{r.get('extremum_calls','—')}|{number(memory/2**20 if memory else None,2)}|")
    lines+=['','所有方法的根预算上限均为300秒；原搜索完成可提前终止，剩余预算不转移、不重开。SEARCH_COMPLETED仅表示原声明邻域无进一步改进，不证明全局最优。实际候选集可随原初始化截止和接纳路径变化。多评候选、多次接纳、较少面板或更早首SAFE均不直接等于最终节能。原协作检查点可产生小幅超时，证据形成必须仍早于300秒。进程墙钟含启动及归档；已测峰值内存包含候选、证据、检查点及归档，不是缓存独占量。','',
      '|根/臂|整场景命中/避免面板|前缀命中/避免面板|直接缓存及身份维护s|接受后的缓存回调s|CPU s|',
      '|---|---|---|---:|---:|---:|']
    for r in slots:
        m=r.get('cache_metrics',{})
        lines.append(f"|{r['case']}/{r['arm']}|{m.get('scene_hits','—')}/{m.get('avoided_scene_panels','—')}|{m.get('prefix_hits','—')}/{m.get('avoided_prefix_panels','—')}|{number(r.get('cache_direct_s'))}|{number(r.get('cache_accept_callback_s'))}|{number(r.get('cpu_s'))}|")
    lines+=['','直接成本含身份、场景查询/保存/恢复及前缀查询/保存/恢复；接受后回调与其中保存成本重叠，不可再相加。原时间分项、构造和预筛统计在summary.json/analysis.json中保留。由于不同臂实际完成的工作不同，本轮不将方法总耗时比例解释为固定候选认证加速。','',
      '## 3. 正确性与覆盖边界','',
      '本轮32项接口检查通过，覆盖原完整候选缓存、初始化/严格改进接纳、180秒准入关闭后继续搜索、数值未决后禁止再发证；前轮43项增量核验证继承为已有证据，未冒充本轮重新执行。原38份算法/输入文件及3份增量来源保持原字节；修复前后唯一执行源码差异为Windows内存统计API签名。',
      '', '|根|三臂共同SAFE候选|至少两臂共同SAFE候选|SAFE候选并集|各臂独有SAFE候选A/B/C|','|---|---:|---:|---:|---|']
    for r in d['common_candidate_exact_semantics']:
        u=r['unique_to_arm'];lines.append(f"|{r['case']}|{r['triple_SAFE_candidates']}|{r['at_least_two_arms']}|{r['unique_SAFE_union']}|{u['A']}/{u['B']}/{u['C']}|")
    lines+=['','同一根、同一候选的共同完整数值证据按精确语义摘要一致核对，包含区间端点、全能量分项、峰谷、积分、守恒和完整trace；只排除形成时间、根累计计数及复用来源等元数据。各自独有候选依赖已验收的同路径增量核与原完整SAFE合同，**本轮没有额外无缓存物理复评**，不能声称所有新候选均经过独立数值重算或任意输入的形式化软件证明。',
      '', '原ON-P/I1的生成、预筛、排序、接纳和180秒准入执行原源码；缓存提交发生在原完整SAFE接纳后，前缀基准只随原接纳变化。同根之前形成的证据可复用，不读未来轨迹、不跨根借结果。最终与初始完整回执保留全文；其余trace和合法性正文保留精确摘要，候选载荷和所有数值包络完整归档。','',
      '## 4. 故障、负结果和停止','',
      '首槽U07/A搜索正常结束并保存SAFE后，Windows峰值内存查询发生64位参数转换错误。原批次按协议停止，余11槽未开始。只读恢复核验了A的证据；用户随后明确授权仅续跑剩余11槽。没有重跑A或追加实例；execution/保留原退出码1与批次停止，continuation/单独记录授权后的11槽。细节见CORRECTION.md。',
      '', 'A的峰值内存、CPU和部分汇总计时没有保存，永久标为未知；只恢复日志能支持的数据。两版本仅结束后的统计接口签名不同，最终能耗可按已有完整证据比较，但U07/A的配对内存/CPU成本不能补造。修复后的独立内存探针不是A的性能测量。',
      '', f"本轮实际返回{d['completed']}个搜索进程，记录{d['worker_nonzero_exits']}个非零退出；数值预算未决合计{d['unresolved_total']}次、中断{d['interrupted_total']}次。续跑状态：{'全部11槽完成，无异常停止' if d['batch_stop_reason'] is None else d['batch_stop_reason']}。全部槽位、失败和原未开始状态保留；不自动增加重复、预算、种子、根数或新算法。",'',
      '## 5. 结论范围与交付','',
      '本批支持“认证复用可以在同一预算上限下改善最终完整SAFE能耗”，没有把多评候选当成节能。B、C均在四根严格优于A；但U10两者相对A均不足1%。这仍只是四根各一次的描述性结果。','',
      '前缀层C/B的保守净改善分别为U07 3.710345%、U08 1.004114%、U09 0.211656%、U10 0.014005%。按1%投入参考，只有2/4根达到，其中U08仅略过门槛；不能宣称前缀层稳定有明显额外价值。该门槛不是物理规律或显著性标准。所有A配对均有初解变化；B/C只有U08初始候选及精确能量区间一致，且C更早完成初始化，因此仍是整个300秒流程的收益。','',
      'C的直接缓存/身份维护耗时7.931—10.108秒、峰值工作集323.28—493.88 MiB；B分别为0.423—0.549秒、153.04—237.43 MiB。峰值包括整个进程，不能都归因于缓存。U10/B、C按原规则分别在258.031、208.719秒正常完成，最终能耗几乎相同；不追加工作用满300秒。U07/A的CPU/内存未知。','',
      '决策：整场景复用有继续验证的依据；前缀层应保留为可关闭组件，先验证重复性及内存代价，再决定是否扩大正式实验。当前证据不支持开发新搜索算法，也不支持把单次收益推广到真实硬件或所有DAG。本轮到此停止，后续实验需另行授权。','',
      f"B/A的逐根类别：{b}；C/A：{c}。这回答本批冻结条件下是否获得最终完整SAFE能耗改善，不能用前轮49.43%固定候选提速换算为本轮节能率。初解不同组仅支持整个同预算流程的比较，不单独证明后续搜索改进。",'',
      '四个已见同族合成根、每臂一次、同机串行且未隔离全部背景活动；不提供显著性、跨硬件稳定性或真实设备节能主张。截止时刻附近的工作量可能随运行环境变化；不通过重跑强制得到相同轨迹或更有利结论。本轮完成后停止，不自动扩例。',
      '', '[协议](PROTOCOL.md)、[协议来源](SOURCE_PROTOCOL.md)、[修正及授权](CORRECTION.md)、[源身份](sources.json)、[完整统计](results/analysis.json)、[复现说明](README.md)。execution/与continuation/保存两阶段原始计时、候选分片、原合同回执和退出记录；repair/保存故障恢复与独立接口探针。',
      '', 'Material Passport：SIC20261115；执行完成状态以全部槽位记录为准；描述性精确区间分析，非统计因果总体推断。统计解释检查11/11：逐根保留避免聚合反转；不跨层推广；样本选择固定且已见；不按候选数或成功筛样条件化；无基率推断；不择极端重测；失败及未决全保留；不多重筛选正结果；执行前冻结且修正透明；仅解释受控范围内差异；无反向因果外推。']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    summary={k:d[k] for k in ['completed','eligible_SAFE','quality_counts','prefix_increment_counts','prefix_at_least_one_percent_cases','worker_nonzero_exits','initial_batch_stop_reason','batch_stop_reason','user_authorized_continuation','unresolved_total','interrupted_total','thermal_violation_total']}
    summary['pairs']=pairs;summary['scope']='Final complete SAFE energy; candidate counts are not energy evidence; no automatic expansion.'
    (root/'results/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main(Path(sys.argv[1]))
