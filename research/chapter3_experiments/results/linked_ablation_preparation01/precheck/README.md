# K172纯夹具预检

最终`run02/checks.json`：8项全通过，0构模／优化／热评价／正式候选生成／研究调用。科学模块未导入，进程未启动；12份读入源码与原R1／R3档案前后hash不变。原7项记录`run01`保留。

执行入口：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/linked_ablation_preparation01/precheck/check_labels.py --out <全新目录>
```

## 已核内容

- AST提取原`anchor_preelimination.filter_closed_anchor_options`与`linked_neighborhood._member`。只移除filter内部唯一的模块导入，注入Fraction、场景索引、canonical hash与**夹具身份stub**；不运行真实SAFE身份校验。
- 四组手写模式／起点标签共1188种赋值，独立资源／依赖oracle的合法集合在过滤前后相同，分别为105／81／138／195。核对半开区间、非整结束、同核互斥、同域异频、独立域、直接前驱／后继边界、开放warm不作为锚及warm保留。
- 缺关闭锚拒绝，空开放域显式登记；伪造结束时刻／模式／域／身份拒绝；原对象及选项顺序保留。
- 只提取`interval.py`的Budget／Exhausted、`thermal.py`的Budget、`timing.py`的MethodBudget类，不导入这些模块。以同一fake-clock根对象模拟A的150秒场景上限及B／C的60秒上限；solver MaxTime同时受场景剩余与300秒根剩余约束，不重置时钟。正常截止后原有夹具证据仍在，新过滤被拒绝；夹具不构成SAFE或能量U。
- 为避免只镜像时限公式，追加AST完整提取原`partial_method._solve_scene`，用只返回手写字典的fake model、无x的fake session与fake recorder运行其原body。A的150秒cap扣2秒导出后实传148秒；根仅余80秒时实传78秒；B／C的60秒cap实传58秒。每次无x早停仅发一次假传输，不自动重启、不重置根截止。截止分支保留原fixture证据，禁止新评价；5次**假传输不是5次研究求解**。
- 原R1／R3各只读到一次fresh构造尝试，两phase的seed身份一致；第二阶段关闭锚来自该次第一阶段最后完整SAFE代次。原始记录不被作为未来调用的免费初始化。

## 旧测试的复用边界

`test_anchor_preelimination.py`已有Cartesian合法集合、结构矩阵、边界、场景隔离、同shared多请求、畸形标签及中断检查；`test_linked_neighborhood.py`已有seed固定设备与warm关闭OPP／起点分层、身份与预算校验。其**测试思路和既有证据可以引用**，整模块含MILP／热依赖与结构构模，本轮没有导入或执行。

本轮只重新核标签层必要含义及根时钟。不证明新矩阵逐行／逐浮点相同，不重新认证热安全、不证明预消元加速、不批准真实运行。

## R1／R3关闭锚事实

| 原题 | 场景 | 关闭Stage | 设备 | OPP | 起点ms |
|---|---|---|---|---|---:|
| R1 | AB | B.main | NPU0 | L | 85 |
| R1 | AB | B.post | CPU2 | L | 150 |
| R1 | AC | C.main | GPU0 | L | 40 |
| R1 | AC | C.post | CPU1 | L | 130 |
| R3 | AB | B.main | NPU0 | M | 85 |
| R3 | AB | B.post | CPU2 | L | 120 |
| R3 | AC | C.main | GPU0 | L | 40 |
| R3 | AC | C.post | CPU2 | L | 130 |

独立B／C调用即使同题使用相同fresh构造规则与第一阶段配置，也不保证预算内最终warm锚相同。闭锚预消元的整数域等价只针对**同一condition**；若实测warm hash不同，质量差属于两次端到端调用，不能直接归因为预消元。须保留各臂seed／warm hash、关闭选择及阶段耗时，不能免费复制另一臂或历史warm。

最终run02 checks SHA256：`19be2e393a3540ebd53d0167ebc02dba9ab8cb734783cdc20ae276cfcaee984d`。预检脚本SHA256：`cb2a6d7f1cf7fd9e06770e34813b83019d93b93bfe0533ea6cdc072b610a62b8`。
