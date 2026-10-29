# 校准后调整接口 V1

独立补充包。实现范围：重复菱形S4、原H锚定的错峰S7、按期限统一窗口、原四节点全空闲L安全证明绑定，以及28条件的待批准清单。旧生成器、参考器、正式算法和热评价器不改。

## 入口

| 接口 | 输入与输出 |
|---|---|
| transforms.derive_branch_multi(base_bundle) | 原基础包装→branch_multi_v1；仅修改拓扑、输出节点和对应依赖 |
| transforms.derive_staggered(base_evidence) | 原基础H表及检查/期限回执→同画像双请求；逐场景Δ为原H最晚绝对完成的一半上对齐5ms |
| transforms.validate_adjustment(base_evidence, child) | 重查原H来源、身份、画像、工作量、非允许字段及变换规则 |
| 旧 deadlines.inherit_deadlines | 原请求绝对期限保持；新增请求继承对应原请求相对期限 |
| window_policy.make_window_receipt(group_id, group_kind, members, beta=…, baseline=…) | 按显式组成员和继承期限生成独立W回执；不改旧包装中的空窗口字段 |
| idle_certificate.make_idle_certificate(config, source_sha256=…, policy=…, lower_C=…, upper_C=…) | 精确参数/源文件绑定的代数证明；不是运行温度轨迹或调度SAFE |
| manifest.make_manifest(repo) | 只读核对旧归档及哈希，列出28项身份和64份父项/对照来源；不生成补充工作负载 |

没有28条件执行入口。supplement_manifest.json中execution_authorized=false，时间预算和最终β均未设置。

S4只接受4n节点或2节点例外。S7不添加跨轮依赖；第二轮大应用可能早于第一轮小应用释放。禁止用派生H表替换原H锚。

窗口记录验证调用者声明的成员。S1要求1/2/4/6/8完整组，S7要求单请求/同步/错峰三角色；其他轴允许显式成员子集，不把该接口当作正式实验设计完整性检查器。S2每个规模单独记录。

## 人工检查

在项目根目录运行，输出必须是从未存在的新目录：

    & 'F:/Anaconda3/python.exe' -B -m research.chapter3_calibration_adjustment.run_checks --output research/chapter3_calibration_adjustment/results/manual_precheck_NEW

运行器只允许带fixture_only标记的人工任务进入参考时间表构造；禁止真实C根任务排程、随机任务/画像生成、正式算法及热模块、子进程和网络。读取旧档案只用于清单的来源核对。

- 最终回执：[manual_precheck03/checks.json](results/manual_precheck03/checks.json)：87项全通过。
- 组成：18项变换、17项窗口/空闲证明、5项清单/故障留档、47项旧参考器回归。
- [人工示例](results/manual_precheck03/manual_example.json)、[空闲证明](results/manual_precheck03/idle_certificate.json)、[待批准清单](results/manual_precheck03/supplement_manifest.json)。
- [源码哈希](results/manual_precheck03/source_manifest.json)及sources目录保存33份源；1152份旧源/档案前后哈希一致。
- [失败记录](results/manual_precheck03/failures.json)、逐项日志、测试时间和受保护文件列表一并保存。

manual_precheck01：84通过、1个临时目录权限错误；02：同一代码85项通过；03：补入三拓扑配对和初始化故障测试后87项通过。旧结果不覆盖。03日志中故意调用已有输出目录的拒绝提示属于负例测试，不是批次失败。

全空闲证明仅适用于原参数、auto_low_immediate_v1、全部工作完成且无后续新工作、终点温度在[20,80]⁴。它允许不额外增加冷却尾段，但不免除0到W的完整功率/热评价。正式输入导出、长窗口算法适配和28条件时间诊断均未实施。
