保留 SAFE，但因技术错误提前终止（763.156 s，预算 900 s）。已保存全局安全方案；未证实相对最佳已成初始化池的严格节能改善。

| 项目 | 保存值 / 审计 |
|---|---|
| 原问题 / 策略 | base__R1 / auto_low_immediate_v1 |
| 方法预算 / scene soft slice | 900 s / 60.0 s |
| 状态 / 停止原因 | SAFE / CONDITION_TECHNICAL_FAILURE |
| 方法耗时 / 清理 | 763.155999999959 s / 7.594000000040978 s |
| 图中轨迹终点 / 未使用预算 | 763.156 s / 136.844 s |
| 最终已保存 U（J） | 1.08082345；回执审计 True |
| 首次全局 SAFE / 全局 U 更新 | 26.640000000130385 s / 1 条通过审计 |
| 独立原域 L0（J） | 0.738285994 |
| U−L0 / 相对 gap | 0.342537457 J / 0.316922673 |
| 已成初始化池 | 保存 5；审计 5；最小上端 1.08082345 J；所有初始化下端的最小值 1.08082345 J |
| 严格池比较 final_hi < all_initial_lomin | False |
| 名义条件 / 已访问 / 未访问 | 16 / 5 / 11 |
| 源冻结身份 | 29 项，快照匹配 True；后处理脚本另存 SHA |

原生故障（条件 4，场景 AC_offset_0ms，round 1，状态 ERROR）：`MATLAB:fileread:cannotOpenFile`。

```text
错误使用 fileread
无法打开文件
F:\by\11111\research\chapter3_experiments\results\shared_search_diagnostic01\invocation\matlab\request_000010.request.json。Permission
denied。

出错 solve_model (第 28 行)
        req = jsondecode(fileread([prefix '.request.json']));
```

全局 U 更新按两个独立轴归因：

| 保存来源 | 同一 a（含首个 U） | 切换 a |
|---|---:|---:|
| 初始化构造器 | 1 | 0 |
| 含 inner MILP 场景回执 | 0 | 0 |

换 a 后的初始化改善归初始化/外层访问；inner 来源表示至少一个场景采用后续 MILP 回执。上界下降与严格能量区间分离分别保存在 CSV；同条件 inner 对其初始化的比较见 per_condition.csv。

| 条件 | 访问 | 保存状态 / 原因 | 初始 U（J） | 最终 U（J） | inner 严格改善 |
|---:|---|---|---:|---:|---|
| 0 | True | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE | 1.08082345 | 1.08082345 | False |
| 1 | True | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE | 1.19607922 | 1.19607922 | False |
| 2 | True | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE | 1.27080146 | 1.27080146 | False |
| 3 | True | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE | 1.27069075 | 1.27069075 | False |
| 4 | True | SAFE / SOLVER_INTERFACE_ERROR | 1.08889118 | 1.08889118 | False |
| 5 | False | UNVISITED / NOT_VISITED | — | — | None |
| 6 | False | UNVISITED / NOT_VISITED | — | — | None |
| 7 | False | UNVISITED / NOT_VISITED | — | — | None |
| 8 | False | UNVISITED / NOT_VISITED | — | — | None |
| 9 | False | UNVISITED / NOT_VISITED | — | — | None |
| 10 | False | UNVISITED / NOT_VISITED | — | — | None |
| 11 | False | UNVISITED / NOT_VISITED | — | — | None |
| 12 | False | UNVISITED / NOT_VISITED | — | — | None |
| 13 | False | UNVISITED / NOT_VISITED | — | — | None |
| 14 | False | UNVISITED / NOT_VISITED | — | — | None |
| 15 | False | UNVISITED / NOT_VISITED | — | — | None |

保存热反馈 0 条、约束行 0 行；仅说明触发/处理记录，不构成反馈优势消融。
所有原场景（包括零权重）须有匹配 SAFE 回执才有全局 U。图中初始化曲线只引用已成回执，可能在传递越过预算后才归档；它不是新增搜索上界。图中 U 只用原存且提交、聚合均严格早于方法截止时刻的更新。
U、初始化参考与 L0 曲线均截止于实际方法停止时刻；其后阴影为未使用预算，不表示方法继续运行或继续持有一段搜索轨迹。
逐场景 solver-reported 内部界、节点/原生状态、x0 与反馈分列在 per_condition.csv，不合成独立原域下界，也不作跨方法节点等价解释。
未访问/覆盖不足、模型未成、数值接纳冲突、原生请求未返回及技术失败仍是未决。单候选失败不排除部署；遍历名义条件不等于证明最优。本次单问题诊断不推断总体胜率。

归档审计问题：[]；条件技术/数值/归档问题：1 组；最终 U 审计：{"errors":[],"formed_at_s":26.625,"valid":true}。细项见 checks.json。

本汇总只读已保存 JSON 与冻结源快照；未调用构模、连续热评价或求解，未读取历史参考答案，未补造预算内数据或新 U。
