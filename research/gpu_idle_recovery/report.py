"""Generate concise Chinese report from audited matched records only."""
from analyze import HERE,CFG,read
import csv
def main():
    s=read(HERE/'summary.json');v=read(HERE/'verification.json');env=read(HERE/'environment.json')
    rows=list(csv.DictReader((HERE/'comparison.csv').open(encoding='utf-8-sig')))
    coverage=list(csv.DictReader((HERE/'coverage.csv').open(encoding='utf-8-sig')))
    table=['|工况|原D017 J|D017＋空闲 J|最好SAFE J/部署|额外节能|恢复部署|完成/目标|',
           '|---|---:|---:|---|---:|---:|---:|']
    labels=['正序/基准初温','逆序/基准初温','正序/预热','逆序/预热']
    for label,r in zip(labels,s):
        table.append(f"|{label}|{r['original_D017_J']:.6f}|{r['D017_idle_J']:.6f}|{r['best_J']:.6f} / {r['best_dep']}|{r['extra_saving_pct']:.6f}%|{r['recovered_count']}|{r['min_peak_certified_deployments']}/{r['target_deployments']}|")
    safety=['|工况|D017＋空闲峰温 °C|最小期限裕量 ms|新见证/SAFE|超期见证|实际总墙钟 s|',
            '|---|---:|---:|---:|---:|---:|']
    for label,r in zip(labels,s):
        safety.append(f"|{label}|{r['D017_idle_peak_c']:.6f}|{r['D017_idle_slack_ms']:.6f}|{r['new_certificates']}/{r['SAFE_certificates']}|{r['deadline_failed']}|{r['wall_s']:.2f}|")
    gains=[100*(r['original_D017_J']-r['D017_idle_J'])/r['original_D017_J'] for r in s]
    first=s[0]['case_id']
    near=sorted([r for r in rows if r['case_id']==first and r['reason']=='minimum_peak' and r['original_safe_frequency_count']=='0'],key=lambda r:float(r['original_peak_c']))
    # Minimum-peak and minimum-energy can coincide; include the selected code once.
    selected={r['dep']:r for r in [__import__('json').loads(l) for l in (HERE/'raw'/first/'events.jsonl').read_text().splitlines()] if r['kind']=='selection'}
    near=sorted([r for r in rows if r['case_id']==first and r['original_safe_frequency_count']=='0' and r['dep'] in selected and int(r['code'])==selected[r['dep']]['min_peak_code']],key=lambda r:float(r['original_peak_c']))[:4]
    nt=['|部署|原最低峰温 °C|空闲调频后峰温 °C|新能耗 J|期限裕量 ms|', '|---|---:|---:|---:|---:|']
    for r in near:nt.append(f"|{r['dep']}|{float(r['original_peak_c']):.6f}|{float(r['peak_c']):.6f}|{float(r['energy_J']):.6f}|{float(r['min_slack_ms']):.6f}|")
    band_total=sum(int(r['band_candidates'] or 0) for r in coverage)
    pending=[r['case_id']+'/'+r['dep'] for r in coverage if int(r['original_overtemp'])>0 and r['selected_minima_completed']=='False']
    outcome='没有发现恢复后更省能的部署，最好SAFE仍为D017＋空闲调频；建议结束本轮方向的复杂联合算法探索。' if all(r['extra_saving_pct']<1e-8 for r in s) else '存在恢复或质量变化，以下按已见证范围报告，不外推新控制域最优性。'
    restored=[r for r in rows if r['recovered_deployment']=='True']
    recovery=['|工况/恢复部署|原能耗 J|原峰温 °C|新能耗 J|新峰温 °C|期限裕量 ms|较D017＋空闲额外节能|', '|---|---:|---:|---:|---:|---:|---:|']
    for case in CFG['cases']:
        for dep in sorted({r['dep'] for r in restored if r['case_id']==case}):
            r=min([r for r in restored if r['case_id']==case and r['dep']==dep],key=lambda r:float(r['energy_J']))
            recovery.append(f"|{case}/{dep}|{float(r['original_energy_J']):.6f}|{float(r['original_peak_c']):.6f}|{float(r['energy_J']):.6f}|{float(r['peak_c']):.6f}|{float(r['min_slack_ms']):.6f}|{float(r['extra_saving_vs_D017_idle_pct']):.6f}%|")
    report=f'''# 空闲调频与热可行部署恢复

**{outcome}**

## Material Passport

来源：冻结合成平台、原高并发四工况与本轮实际日志。历史输入/精确参照45b14f9，响应式策略af6dd97；执行冻结339a33a，导入冲突修复后冻结[{env['execution_commit'][:7]}](https://github.com/YBEMR/paper/commit/{env['execution_commit']})。模式：限定机制诊断；新控制域全局最优性未认证。四工况预算各120秒，结果均按实际日志归档，未调参。

## 匹配结果

{chr(10).join(table)}

额外节能分母是同工况D017＋空闲调频，不能用原超温低能耗作SAFE节能对照。“恢复部署”指历史全频率域没有SAFE频序、这次得到完整SAFE见证的部署；原已有SAFE的部署内频序变化另见CSV。D017直接空闲管理相对其原方案节省{min(gains):.3f}%–{max(gains):.3f}%，这一收益属于控制权限扩展，不是重新选择部署的收益。

{chr(10).join(safety)}

总计{v['counts']['certificates']}份新空闲调频完整证书，{v['counts']['SAFE']}份SAFE。失败方案的真实能耗、峰温、全部750请求完成记录均保留，但不计安全节能率。四组是否完成冻结候选集合：{[r['completed'] for r in s]}；未决项：{', '.join(pending) or '无'}。详见[coverage.csv](coverage.csv)，不得将未决写成不可恢复。

## 为什么没有额外部署收益

{chr(10).join(recovery)}

该表列出原全域无SAFE、现在得到SAFE见证的部署（每部署保留最低已见能耗）。额外节能为负表示虽恢复安全，仍比D017＋空闲更耗能。恢复热可行性和改善最低安全能耗是两个不同结论；不将前者自动计为后者。

正序基准初温中，原无SAFE部署里最接近温限的最低峰温频序如下；不仅检查了无温限最低能耗点。

{chr(10).join(nt)}

空闲降频确实降低峰温，但这些已核验频序仍超过80°C；其新能耗也未低于D017＋空闲调频。更低能耗但GPU更热的部署不能因降了一点温度就当作SAFE。部分原期限可行方案还因恢复延迟超期，不能只看峰温。

已完成项的原最低峰温通过原场景热核连续上下界筛选，再用原完整评价器细化，在其原0.0005°C峰温分辨率内完成核验；没有用场景末温替代峰温。80–84°C且原能耗低于原D017的保守带状筛选，在**已完成筛选部分**共收集**{band_total}**条候选。为0时，只对已筛完部署，完整旧频率数组与连续界排除了该交集；未完成部署不作推断。选取最低峰温不要求原能耗低于D017，因此仍覆盖了上表中的临界热候选。

## 适配、故障与范围

保留750请求、81个具体部署、25°C、40 ms期限、10.04秒系统计能、80°C和原四节点RC/漏电模型。预热直接继承冻结初温。按所选原频序保留CPU/GPU/DLA计算阶段频率，GPU可L/M/H，阶段不可抢占、原GPU顺序固定。仅空闲降L，100 µs等待与最短驻留，恢复100 µs、10 µJ；参数是合成假设，不是硬件实测。转换期间采用较高端点频档功热参数并计入额外热源；没有强制所有GPU计算为H。

首次启动发生适配文件physics.py与原热库同名冲突，在导入阶段停止，**没有产生候选结果**。仅改文件名/导入，冻结修复并保留[startup_fault](startup_fault/)；消耗1.674386秒计入正序基准工况的120秒，总预算未延长。其余参数、候选规则及物理源文件不变。不是性能不佳后的调参重跑。

本轮按表中范围检查旧域目标部署及声明候选集合，**没有枚举空闲调频后的全部频序**。原最低峰温频序未必仍是空闲控制后的最低峰温频序，因此“本轮未恢复”不能扩写为“任何频序都不可能恢复”。同样，最好已见SAFE不能称新域精确最优。先前的原域精确证书只用于参照和候选分类。

本轮不进行Kim同权限适配或联合算法设计，不扩大温度、负载和部署域；保留普通空闲管理的直接节能结果。若考虑其他机制，应另立明确问题，不能将本轮负结果改写为新算法收益。

## 归档与复核

源码及实际参数：[worker.py](worker.py)、[control.py](control.py)、[online_events.py](online_events.py)、[idle_certificate.py](idle_certificate.py)、[peak_selection.py](peak_selection.py)、[config.json](config.json)、[PROTOCOL.md](PROTOCOL.md)。

[完整逐频序结果](comparison.csv)、[四工况汇总](summary.csv)、[81部署覆盖](coverage.csv)、[SAFE及失败证书、温度轨迹、选择界](raw/)、[核验](verification.json)。历史两个目录逐字取自45b14f9，未改动旧文件。新文件只在research/gpu_idle_recovery。

离线复核：在仓库根目录运行 `python -B research/gpu_idle_recovery/analyze.py`，然后 `python -B research/gpu_idle_recovery/report.py`；不会启动新物理实验。交付内容先用 `python -B research/gpu_idle_recovery/archive.py` 验哈希。原始receipt保留文件摘要和进程退出状态；analyze检查阶段计算量哈希、资源互斥、释放/期限、原频率、转换时长/能耗、热连续继承、全窗能量、峰温轨迹、最低峰温筛选覆盖。执行复现应另建checkout并另存结果，不覆盖本次raw。
'''
    (HERE/'README.md').write_bytes(report.encode())
    print(outcome)
if __name__=='__main__':main()
