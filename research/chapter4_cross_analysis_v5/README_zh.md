# 第四章 A–E 执行与验收准备包 v5

## 状态

- v4 `formal_runner/` 原样复制；内部锁验证通过。原 P1、G1、G2、第三章正式协议与第三章结果不变。
- v5 只新增**事后分析与审计**，不改变求解器、构造器、算法参数或24单元登记。`E_reference.json` 来自 v1 ZIP 中四个 ThermalUnion 实际端点及对应计划/证书；逐个核验 v1 计划 SHA、SAFE 能耗和初解身份。原 v1 ZIP SHA-256：`4d352ecda69b3ef72f8f8cdf262703d7b50c480946cfe08d572bc5d8e5218f1e`。
- `feedback_frozen.py` 是原 G2 `feedback.py` 的冻结副本，SHA-256 与第三章执行锁一致。分析器用其 `virtual` 计算共同目标及每轮虚拟超期，适配层只读取锁定请求表和 P1 配置时长，不参与求解。
- **正式24个900秒 C/D单元未启动。** 本环境无原 OR-Tools 且系统/Python不同。新增分析器只在真实 v1/v3 数据上测试了计划身份、能耗区间、配对运算和同前态轮次匹配逻辑；尚无完整正式 C/D 数据可验证全量审计路径。v3数据绝不能作为正式 C/D 回执。

## 原实验机器上的唯一下一步

在原 Windows/Python、原冻结依赖及 YBEMR/paper 工作树下解压本包，先阅读 `formal_runner/README.md`。下列 `<repo>` 和 `<output>` 使用真实路径，输出必须是新的仓库外目录；在本包根目录执行：

```text
python -B formal_runner/run_cross.py plan
python -B formal_runner/run_cross.py check --repo "<repo>"
python -B formal_runner/run_cross.py smoke --repo "<repo>" --out "<output>/smoke" --confirm-original-environment
```

`check` 必须确认全部锁文件、原环境版本及200份 OR-Tools 运行时文件通过，实际机器及物理核口径也由执行者核实。只有 smoke 两臂均 PASS 且执行者明确批准长批次后才运行：

```text
python -B formal_runner/run_cross.py execute --repo "<repo>" --out "<output>/formal" --smoke-gate "<output>/smoke/smoke_gate.json" --confirm-original-environment
```

总登记24×900秒＝21600方法秒，不是实际耗时预测。仅串行启动独立 C/D，不调用第三章165单元主函数。失败不自动重跑、不覆盖原记录。

## 正式结果验收

有完整回执后再执行：

```text
python -B analyze_cross.py --repo "<repo>" --run "<output>/formal" --out "<output>/analysis"
```

默认从原仓库的 `research/chapter3_final_evaluation/formal/cells` 读取原 A/B 逐轮日志；如果原日志已另行从正式分片归档恢复，可通过 `--ab-root "<恢复目录>"` 指定。原 A/B 质量参照仍从哈希固定的 `results/endpoints.csv` 获取；原始轮次日志必须与正式端点和回执逐项匹配才参与同轮次/同耗时对照。

输出：

- `inventory.csv`：逐臂审计状态、预算、配置/后处理轮数及证书数量。若原 A/B 日志不可用，保留已发布质量数据，同时显式标为原日志未审计。C/D 任何缺失或不合格不纳入完整配对。
- `paired.csv`、`paired_summary.csv`：按种子和阶段计算 A−B、C−D、A−C、B−D、交互差；最终 D−E 和认证区间差；E 为每工况一份确定性端点，不冒充独立随机种子。正 A−B/C−D 表示反馈方法节能；正 D−E 表示 E 更节能。正交互差仅表示原初解上的反馈收益更大，不能单独归因于冲突消除。
- `round_mechanisms.csv`：基于实际轮前计划和目标重建虚拟超期；区分选中补偿、实际改动补偿、跨场景补偿和配置变更。
- `matched_rounds.csv`：同前态、同目标、同规模匹配，标记实际变更的普通邻域外补偿与两侧求解器状态。TIME_LIMIT 不作为精确域最优证据。
- `common_checkpoints.csv`：共同完成轮次及固定配置阶段时间点（30/60/120/300/600秒）；时间从首轮开始的日志估计值计，使用已完成轮末在位解，超过最后记录的轮次/时间记为截尾，不外推。不是精确首次 SAFE 时间或候选接纳时间。原/新批次即使硬件和版本相同，也可能因并行负载及启动方式不同存在计时差异；跨批次计时只能在实际环境确认后描述，不能直接宣称加速比。
- `audit.json`：完整 C/D 审计状态。分析器是已保存证据的一致性核验工具，不重新运行热核认证，也不替代原发布审计。正式前仍须通过原 E2-a smoke，正式后须保留全部原计划、证书、热轨迹、运行回执及异常尝试。若分析器发现问题，保留原输出，单独修复分析器并记录版本；不得改原实验数据。

## 当前核验

`probe_parser_check.json`：真实 v3 32轮日志，15个匹配轮次，D2第3轮普通邻域外实际改动请求100，两侧均 TIME_LIMIT，差额4.2058149349mJ。`probe_arithmetic_check.json`：使用真实 v3 终点证书与 v1 E 端点检验差值/区间。`verified_roster.json`：24个固定正式登记单元。`manifest.sha256`：本包文件内容身份；仅用于完整性校验，不代表已运行正式实验。
