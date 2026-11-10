# 工作包A/B/C：附件访问阻碍与来源索引预备

**本文件不是工作包A完成报告。两份指定附件尚未读到正文，七份方案、九个周期配置及最多14条轨迹的名单/定义均未确认；A未完成，C/B未启动。** 当前会话提供Library写入功能，但没有读取或准备下载这两份指定文件的入口；不从文件名、旧对话或仓库内容猜测附件要求。

本轮已完成不依赖附件的仓库来源预查及一个明确标注未选定的候选家族索引。原始结果和算法没有修改；调度搜索、新热积分、周期求解均为0。需取得两份正文后再按指定范围绑定方案，不能直接使用本索引发起实验。

## 可追踪材料

- `session_start.json`：任务边界、附件引用及访问检查、各阶段阻碍。
- `candidate_source_index.json`：候选家族各文件路径、SHA256、输入/时间表身份与现有轨迹积分可用性。
- `candidate_family_closure_t50.csv`：七份既有结果的候选来源表，所有行明确标为 `CANDIDATE_FAMILY_ONLY_ATTACHMENT_TARGETS_UNKNOWN`。
- `command_01_started.json` / `command_01_return.json`、`command_01_stdout.log` / `command_01_stderr.log`：唯一来源提取命令、实际时间与输出。

## 候选家族：不是附件指定对象

家族为既有 `chapter3_closure_execution01` 的 `closure_beta1_t50__R1`，400ms，独立AB/AC场景，各3个执行，总6个Stage执行，36合法模式，5ms开始格点，50/80°C、auto-L。已实际逐字典确认七份runtime输入及config完全一致，且与准备输入语义一致。是否选用这一家族，仍需附件确认。

|既有结果id|方法/种子|既有最终能耗上界 J|
|---|---|---:|
|t50_milp|whole_milp / None|0.870308316279|
|t50_heft|heft / None|0.870324370116|
|t50_sa101|sa / 101|0.885640557396|
|t50_sa102|sa / 102|0.885634809181|
|t50_sa103|sa / 103|0.885627434135|
|t50_sa104|sa / 104|0.870335077092|
|t50_sa105|sa / 105|0.870314698381|

七份均保存完整双场景400ms凭证、每节点温度积分和7–9个面板结束轨迹点，共14条既有场景轨迹。此处只记录存在性，没有重新积分、补密或计算附件未确认的平均温度指标。

准备输入文件字节SHA为 `c4c94d3d7b8e139333853e12e312c74c5b62d1d091ca8ad0314950ab5ed714b0`；相同JSON内容的紧凑canonical SHA为 `f4578c051ba55e600c70f83dc980310f7f70b8a10c60327b83107231a2a6727b`。两种口径不同，不能据hash字符串不同就认定科学输入漂移。

## 全H模板与HEFT身份

在上述候选家族中，下列全H记录确实不同：

|记录|候选canonical SHA256|可证实差别|
|---|---|---|
|MILP原全H模板|`c212a952205da85d4dc001846a2e699dd8953ad7f27e5cf361cca3e06904b126`|AB中A.main从10ms开始，B.main从40ms开始|
|HEFT首次 `heft:eft` 全H构造|`de42dc291ef51fff4440cec05c14c6c2ca32e3bf70e291df7a79fa19c84d356f`|AB中A.main从35ms开始，B.main从0ms开始|
|增强HEFT最终方案|`58e9d4498725e4910ea9c852e30ca6212d8d4a9f2bdebf5add6295e9098b6531`|不是首次全H构造|

来源：`research/chapter3_experiments/results/chapter3_closure_execution01/slots/t50_milp__method/worker/raw_result.json` 的 `initialisation.witness.candidate`；同根 `t50_heft__method/worker/raw_result.json` 的 `evaluations[0].candidate`。SA101–105的首次 `sa_initial_heft` 均对应后一个全H构造，不能当作MILP全H模板。

另外，旧原规模 `base_initial_witness01` 与 `heft_sa_followup01` 即使都叫base__R1/400ms，也存在前者idle-hold、后者auto-L的控制语义差异，不能直接拼成公平对照。

## 周期来源与复用边界

只读检查未定位到适用于当前四节点400ms模型的周期固定方案复核器；范围为仓库活动代码、非快照结果脚本、已跟踪文件及相关文件名Git历史，不宣称机器其他位置绝无脚本。

- `research/audit_first_experiment.py:14,61–75` 来自早期3节点/24ms模型，含10898个旧方案枚举、浮点周期固定点及0.025ms采样峰温。未运行，不能直接用于本任务。
- `research/first_experiment_audit/independent_results.json` 是该旧模型的已有采样结果，不是四节点400ms连续周期安全证明。
- `research/matlab_thermal_sched_src/eval_schedules.m:8–16,44–54` 的恒功率段平衡温度与采样瞬态检查，不等于周期稳态峰值或当前模型保守周期界。
- 当前 `research/chapter3_experiments/thermal.py:178–184` 的段矩阵含各频域漏电斜率，不能照搬旧固定 `-C^-1 G` 矩阵。`:375–378` 按场景分别从声明初温评价，不应把AB/AC串成同一温度历史。

已保存的 `temperature_rise_integrals_Ks` 是相对环境温度的积分，见当前 `thermal.py:226–229,304–309,325–327`。对于完整400ms场景，节点均温可由 `Ta + integral(T-Ta)dt/(2/5 s)`导出；具体平均对象、权重和呈现口径仍需PDF确认。

现存trace主要为面板结束点，常不含t=0。补入口并连线只能用于展示，连续安全依据仍是完整SAFE凭证与连续峰值包络；违规应有有效域内点温度下界越限的见证。单轮启动峰值、周期稳态峰值、保守界、单轮/周期能耗必须分别记录。

## 继续工作所缺资料

1. 已粘贴的文本(1).txt完整正文：工作包A/B/C细则，七份方案的准确来源/选择规则，九个周期配置，以及最多14条轨迹的名单。
2. 热约束下的推理调度评价体系.pdf的正文或相关页面：周期映射、温度与平均温度指标、边界与约束定义。

不需要重新批准已授权范围；需要的是可读取的原资料。获得正文后应先确认来源映射与原输入/固定时间表，再决定是否复用积分、恢复周期脚本或进行最小后验补算。

## 执行记录

基线 `0a82ae1cd2f6121609616e7babea76d79d6e0c0a`。环境 `Linux-6.18.57-x86_64-with-glibc2.41`，Python 3.12.14。来源提取 2026-11-10T03:16:53.535778+00:00–2026-11-10T03:16:55.101340+00:00，1.565557秒（外层完整命令约1.841秒）。

实际命令（cwd `/workspace/paper`）：

```text
python -B research/chapter4_scheduler/results/evaluation_workpackages_20261110/extract_candidate_sources.py
```

提取只用JSON读取、字典比较、哈希及文件写出；未导入或执行调度/热评价/周期求解代码。旧记录保持，未推送或合并。
