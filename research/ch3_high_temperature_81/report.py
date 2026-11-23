"""Build the bounded-study report from audited same-domain records."""
import csv
from pathlib import Path
from analyze import HERE,P,csv_rows

rows=csv_rows(HERE/"run_results.csv")
summary=csv_rows(HERE/"comparison.csv")
cells=[]
for r in summary:
    proven=r["m2_status"]=="OPTIMAL"
    cells.append("| "+" | ".join([
        "27.5°C 逆序原驻留" if "27p5C" in r["case"] else "30°C 正序原驻留",
        r["m2_deployment"], f'{float(r["m2_safe_j"]):.9f}',
        f'{float(r["kim_mean_j"]):.9f}',
        f'{float(r["observed_safe_saving_pct"]):.6f}%',
        r["m2_thermal_coverage"]+"/81",
        "完整有限域最优" if proven else "预算内安全见证",
        f'{float(r["m2_wall_s"]):.3f}',
        f'{float(r["kim_wall_median_s"]):.3f}'
    ])+" |")
a=next(r for r in rows if r["unit"]=="c0-r0")
b=next(r for r in rows if r["unit"]=="c1-r0")
text=f"""# 高温完整 81 域的 M2 与 Kim-Adapt+SAFE 核查

**27.5°C 已获得完整 81 域的节能质量证据；30°C 获得预算内安全解的质量差异，同时暴露原 M2 热回退的耗时边界。** 两个工况都完成了预登记运行。M2 每工况一次，Kim-Adapt+SAFE 沿用正式实验的五种子，合计 12 次。所有 10 次 Kim 运行都得到 SAFE 解。对 M2，27.5°C 完成全域认证，30°C 在 120 s 截止时完成 24/81 部署的热约束搜索。

| 同域工况 | M2 安全部署 | M2 安全能耗 J | Kim 安全均值 J | M2 安全解相对 Kim 节能 | 热搜索覆盖 | M2 证据范围 | M2 墙钟 s | Kim 墙钟中位数 s |
|---|---|---:|---:|---:|---|---|---:|---:|
{chr(10).join(cells)}

节能率定义为 (Kim 安全能耗 − M2 安全能耗)/Kim 安全能耗。五个种子在各自工况都取得相同能耗。27.5°C 的参照值具有完整域证书；30°C 的值是已认证安全见证，最优值仍在有效下界 {float(b["lower_bound_j"]):.9f} J 与安全上界 {float(b["safe_j"]):.9f} J 之间，差 {float(b["gap_j"]):.9f} J。两个案例的场景顺序也不同，不能从它们推断温度与节能优势的单调关系。[逐运行结果](run_results.csv) · [同域汇总](comparison.csv)

## 27.5°C 的全域结论

完整 81 域最优为 D030，频率 MHM/MHM/LLL/LLL，能耗 {float(a["safe_j"]):.9f} J，连续峰温上界 {float(a["peak_upper_c"]):.6f}°C，最小期限裕量 {float(a["slack_ms"]):.6f} ms。首次 SAFE 出现在 {float(a["first_safe_s"]):.3f} s，最佳 SAFE 首现为 {float(a["best_safe_first_s"]):.3f} s，全域证书为 {float(a["certificate_s"]):.3f} s。这三个时刻意义不同。

M2 的全域无温限最优是 D000，LHL/LHL/LLL/LLL，连续能耗 43.547968346 J；原连续评价认定它超温，于是原算法进入全部部署的约束搜索。最终完成 43,046,721 个编码的域覆盖，其中 2,141,829 个满足期限，788,076 个 SAFE、1,353,753 个超温、零未决。D030 比历史四部署子域最优 D001 再低约 0.069017 J。完整域证书据各部署的分类数组、严格安全最小值与全窗原物理复核闭合。[逐部署覆盖和证据摘要](deployment_coverage.csv)

五个 Kim 种子分别检查 21、21、20、21、22 个代理排序候选，第一个候选均超温，最终选中 D015 或 D017，能耗均为 45.276227508 J，峰温 70.644946°C，期限裕量 1.248307 ms。Kim 比 M2 更早得到 SAFE，最终方案具有更大的热裕量与期限裕量。能耗差和这些裕量应同时报告。

## 30°C 的预算边界

M2 完成全部 81 部署的无温限能耗搜索，随后进入原热约束回退。截止时完整分类前 24 个部署，正在处理第 25 个部署 D013，后 57 项整体尚未完成分类。已有完整分类中未决数为零。当前最好 SAFE 为 D007，LLL/LLL/MHM/MHM，能耗 {float(b["safe_j"]):.9f} J，峰温 {float(b["peak_upper_c"]):.6f}°C，期限裕量 {float(b["slack_ms"]):.6f} ms。首次 SAFE 为 {float(b["first_safe_s"]):.3f} s，最佳 SAFE 首现为 {float(b["best_safe_first_s"]):.3f} s。

30°C 的五个 Kim 种子分别检查 24、21、20、22、22 个候选，均选中 D015/D017 并取得 45.576665373 J，峰温上界为 71.135518°C。已有 30°C 的 D015 安全见证因此可以被更低能耗的同域安全见证改善。当前下界按部署组成，对已完成约束分类且无未决的部署采用其严格最低安全能耗，对其余部署采用已完成的无温限连续能耗最低值，再取全域最小值。下界重建仅使用截止前日志。本轮未闭合的界仍较宽，D007 的全域最优性未知。完整域内可能还存在更优安全解。

该运行最后已完成部署检查点记录，约束搜索累计 {float(b["cost_constrained_search_s"]):.3f} s，其中原连续积分回退累计 {float(b["cost_fallback_integral_s"]):.3f} s；27.5°C 全域对应约束搜索 {float(a["cost_constrained_search_s"]):.3f} s、积分回退 {float(a["cost_fallback_integral_s"]):.3f} s。两项为包含关系，不能重复求和。进程被监督器于 119.95 s 发出终止，清理后墙钟 {float(b["wall_s"]):.3f} s。最后检查点之后未完成的片段开销只由总墙钟体现。没有补跑或延长截止。

## 决策机制与合理归因

原 Kim 流程对每个访问部署用 SetFreq 产生一条四场景频率序列，按独立场景代理能耗排序，再依次完整认证，遇到首个 SAFE 即停止。M2 对全部部署的全部原频率组合进行有限域搜索。这两条搜索路径允许选择同一原合法域，候选生成和停止机制不同。

27.5°C 的三个 Kim 种子访问到了 D030，代理池排名分别为 48、45、48，另外两个种子没有生成 D030。已访问时 SetFreq 给出的频率为 LHH/LHH/LLL/LLL，与 M2 最优 MHM/MHM/LLL/LLL 不同。三个候选都位于首个 SAFE 之后，故未进入 Kim 完整认证。已有日志支持代理排序、候选频率和首 SAFE 停止与最终差距有关；各因素的独立边际贡献需要消融，当前数据不作独立归因。[候选池诊断](pool_diagnostics.csv)

D030 把 YOLOv2 的 GPU 起点从 D000/D005 的第 41 层前移到第 30 层，释放一个 DLA 常驻阶段名额，同时保留两个 tiny 的 DLA 前缀，并给 YOLOv3 配置 0–36 层的 DLA 前缀。30°C 当前最好 D007 则保留 YOLOv2 的双 DLA 前缀、一个 tiny 的 DLA 前缀以及 YOLOv3 的单 DLA 前缀。Kim 的 D015/D017 给 YOLOv3 两段 DLA 前缀，将两个 tiny 放在 GPU。具体绑定和切点以冻结目录为准，证据适用于冻结合成平台。[获选部署结构](selected_mappings.csv)

## 执行口径与复核

执行提交为 `6a4c5900cbe0d615e1eb481dbf4368190ec4d098`，父提交为 `e0f652aedf58e8fecd423472146c033ff383b5e8`。全部运行使用同一台机器、单逻辑核、串行冷进程和独立空 Numba 缓存。共同预算含导入、核对、调度、构核、搜索、回退、证据写盘及认证。M2 复用原冷 JIT 准备。Kim 沿用正式 24 个体 × 最多 64 代、95 s 生成截止、116 s 认证截止、最多 81 个候选认证和首 SAFE 停止；种子为 20261121–20261125。5 种子按既有正式配置选用。规则没有根据本轮结果调整。

原 M2 模块将环境温度写死为 25°C。本轮仅在内存加载时把缓存上下文、构核、完整回放的三个温度位置绑定到已声明工况，另在冷准备时传入相同环境。适配前验证原文件 SHA-256，完整变更见差异文件。原静态能耗下界删除温度相关漏电，仅使用固定板级/空闲能耗和全工作量活动能耗；在环境与初温均不低于参考 25°C、本模型热源与漏电斜率非负时仍成立，该表达没有提供搜索优选规则。完整证书使用实际环境下的连续热积分。[温度适配差异](ambient_binding.diff) · [正式配置](protocol.json)

原物理模块核对请求 SHA-256、每网 125 个请求、四节点 30°C 初温、80°C 温限、完整 10.04 s 计能窗、FP16 和场景热状态继承。所有已接受候选均归档完整请求完成账本和原连续峰温上下界。离线核验检查实际输入、期限、温度继承、能耗求和、完整分类数组摘要及上下界。30°C 被中止的 gzip 日志可能缺少结束标记，读取器仅接收完整记录；全域认证只接受截止前完成的证据。

M2 单次覆盖能力、Kim 五种子安全解和 30°C 截尾结果均按实测呈现。27.5°C 的小幅同域节能优势已有精确证据；30°C 已见安全解比 Kim 更低能耗，但尚缺原 M2 在限定预算内的全域证书。现阶段第三章可以补上高温下部署与频率联合选择的质量证据，同时保留精确热认证成本及搜索覆盖的边界。

```text
python -B research/ch3_high_temperature_81/analyze.py
python -B research/ch3_high_temperature_81/summarize.py
python -B research/ch3_high_temperature_81/report.py
```

复跑正式实验使用 `launch.py <新的空输出目录>`，原 120 s 配置由协议控制。原始日志、每次回执和 M2 已闭合部署的频率分类数组位于 [raw](raw)。
"""
(HERE/"README.md").write_bytes((text.rstrip()+"\n").encode("utf8"))
