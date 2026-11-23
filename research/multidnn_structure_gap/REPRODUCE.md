# 复算与审查

## 只复算归档结果

在包含旧研究依赖的完整仓库中，从仓库根目录运行（无需 Torch 导入、模型权重或 GPU）：

```powershell
python -B -X utf8 research/multidnn_structure_gap/analyze_gap.py
python -B -X utf8 research/multidnn_structure_gap/verify_gap.py
python -B -X utf8 research/multidnn_structure_gap/plot_gap.py
```

`analyze_gap.py` 不调用优化器或物理评价器；`verify_gap.py` 校验输入/源文件哈希、逐运行收据、已归档连续热证书、每份获胜请求账本、精确枚举覆盖。它不重新枚举整个域，不把归档一致性核验说成独立形式化求解证明。`plot_gap.py` 仅读取汇总；SVG保留可编辑文本，PNG可直接查看。PDF遵循仓库忽略规则，只在本地复算生成。

`run_results.csv` 含实际墙钟、首份完整SAFE证书时间、最终最好SAFE解首次出现时间、部署/频率、峰温、期限裕量、调用数量与耗时。`case_summary.csv` 区分同域已证最优与最好已见。`mechanism_evidence.csv` 仅使用正式日志中的候选、代理和认证记录归因。空的 `gap_pct` 表示缺乏相应最优证书，不能当作零差距。

`time_to_0_1pct_s` 的时间门槛为 `E <= 1.001 E* + 1e-7 J`；主能耗Gap仍按用户定义，以Kim能耗为分母。`e0_j/e0_status` 必须结合 `e0_proven` 阅读：后者为false时，只是当前扫描前缀中的最低候选，不是全域无温限最优。`reference_deployment` 是精确法保存的一个最优见证；物理绑定不同但达到相同能耗仍算达到最优。

计时项中 `setfreq_inclusive_s`、`proxy_inclusive_s`、`continuous_replay_s`、`evidence_s` 都含子调用，不能直接求和。耗时图只相加事件调度、核构建、核查询、直接热积分四项，剩余墙钟归为初始化、遗传运算、日志与其他开销。

## 重做必要正确性检查

```powershell
python -B -X utf8 research/multidnn_structure_gap/checks.py
```

包括官方参数数量/结构检查、旧模型27频点阶段回归、旧500请求完整回归、8个固定微型仿射/标量对照。输出会重写 `checks.json`，因此不要在本归档上随后直接启动批次；执行冻结校验会拒绝任何字节漂移。

## 独立重现实验

应在单独干净检出中使用执行冻结提交 `fd2c3f3`，先核对 `execution_manifest.json`，再运行：

```powershell
python -B -X utf8 research/multidnn_structure_gap/run_gap.py
```

环境版本见 `software_versions.json`；当前研究使用 Windows、Python 3.12.4，CPU亲和性固定到逻辑核0/2/4/6，数值库单线程。其他设备若没有这些核，必须事先记录环境适配；不能把不同平台时间直接归因于算法。新运行结果不得覆盖本次 `raw/`。脚本在目录已存在时拒绝第二批运行，故需要新检出而非删除原始记录。

执行冻结固定8个主输入、精确参照8次、Kim24次；120秒完整墙钟、116秒接纳截止。运行器不补种子、不延时、不重跑未决。四个 `inputs/holdout/` 没有执行；后续研究使用它们需另行声明任务范围。

## 参数与证据来源

- 图来源、权重地址与缺失验证见 `sources.md`、`sources/audit.json`。`sources/*.txt` 按原始字节保留已安装官方源码及许可证（包含原换行/空白），便于哈希核查；不是自行重新发布训练权重。
- `prepare.py` 的来源快照读取本机已安装 TorchVision 路径；其他机器应使用仓库锁定的 `sources/` 与 `inputs/graphs/` 复核，不把本机安装路径当作可移植依赖。
- 新图仅有结构驱动的合成时延与功率；无双DLA板端时延、功率、引擎放置、输出一致性或FP16精度保证。
- `frozen_old_sources.json` 与执行清单确保旧 M2、Energy-Only、Kim、物理模型及历史输入没有被改写。数值最优性仍遵循既有 binary64、连续峰温上界与1e-7 J容差，不是有向舍入数学证明。
