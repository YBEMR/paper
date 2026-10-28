# 独立期限参考器 V1

实现依据：`be8dd50f`中的[实施范围与接口草案](../第三章期限参考器实施范围与接口草案_20261028.md)第3.1、3.2、4节；用户随后明确授权第一阶段代码和人工夹具测试。

**用途：显式任务合同 → 唯一共享部署 → H/M/L参考时间表 → 独立时间检查 → 期限及诊断。** 不包含随机任务生成、功耗计算、热积分或正式优化。参考映射不限制正式方法的部署，也不是免费初解。

## 复跑人工测试

在仓库根目录使用Python 3.12（本次为Anaconda 3.12.4），仅依赖标准库：

```powershell
& F:/Anaconda3/python.exe -B -m research.chapter3_deadline_reference.run_checks --output research/chapter3_deadline_reference/results/manual_recheck04
```

输出目录必须是本模块`results/`下的新目录；已有回执拒绝覆盖。运行器保存逐测试/子测试结果、文本日志、源码快照及SHA-256、人工示例输入和完整输出、旧源码运行前后hash。它阻止旧科研模块导入、优化库导入和运行期子进程/网络操作。以上命令**只复跑人工夹具**。

- [最终47项结果](results/manual_precheck03/checks.json)，[逐项日志](results/manual_precheck03/unittest.txt)。
- [人工示例](results/manual_precheck03/manual_example.json)，[源码清单](results/manual_precheck03/source_manifest.json)。
- `manual_precheck01`是原42项通过版本；`manual_precheck02`保留补测时测试代码的NameError；03是修复后的47项通过版本。各目录有各自源码，不能混用清单。

## 输入合同

完整可读示例见`fixtures.py`及上述人工示例JSON。生产接口不从夹具获取默认参数。

| 字段 | 要求 |
|---|---|
| 身份 | `schema_version=deadline-reference-input-v1`；显式`root_family_id`、`variant_id`、`topology_id`；`derivation`含轴和父合同hash，BASE的父为null |
| 时间与执行规则 | 显式5 ms网格、原响应模型标识；不抢占/迁移/Stage内改频、域空后切频、auto-L、零额外切换/搬运/交接开销和半开区间均须声明 |
| 平台时间子合同 | CPU1/CPU2同CPU域，GPU0/NPU0独立域；三个域的L/M/H频率显式给出且递增，参考频点H |
| Stage画像 | 每共享身份的抽象工作量、逐合法单元的参考时长和α，以及完整H/M/L支持；α在[0,1]，缺档报错 |
| 场景与请求 | 显式场景权重且和为1；逐请求释放时刻和Stage实例清单；出现位置的合法单元、共享身份和依赖边；不自动补释放、权重或边 |
| 元数据 | `context`显式给出，可记人工夹具/初温等背景；它不参与排程和期限计算，也不能代替调度字段 |

所有参与计算的标量用整数或十进制/有理数字符串；拒绝二进制float和bool。规范化不修改原对象，列表排序和有理数约分后计算合同hash。不接收`deadline_ms`、`window_ms`或旧`response_variant`作为根字段。H/M/L始终表示工作点，三表使用同一响应参数。

本模块只携带**时间所需的平台子合同**，没有另建四节点RC或功耗模型；旧模型文件原样保留。时间结果不代表热安全。

## 接口与含义

| 模块/接口 | 功能 |
|---|---|
| `contract.normalize` | 输入验证、共享身份兼容域交集、DAG检查和规范化；失败抛`ContractError` |
| `scheduler.choose_mapping` | 按场景加权最快H负载排序，再按最大场景设备负载、加权总负载、单元ID选设备；保存每步代价 |
| `scheduler.build_references` | 唯一映射只生成一次，H/M/L各构造一次并独立检查；正常状态`REFERENCES_COMPLETE` |
| `scheduler.build_timetable` | 给定显式合法映射的低层排程接口，供隔离空档测试；正式参考应使用`build_references`，不能将任意手填映射称为唯一参考 |
| `checker.check_timetable` | 直接从合同和行记录重算时长、结束时刻、逐请求完成、共享映射、释放、网格、依赖和两两资源/频率冲突；不调用排程器或其时长函数 |
| `scheduler.project_references` | 从完整BASE/S2族向S1子集投影，保留映射来源，验证来源hash；不重新排程。始终从原完整族投影 |
| `deadlines.make_deadlines` | 对合法基础H表，用显式β和参考拓扑ID生成期限；仅BASE/S2可调用。低层接口认证时间合法性，不单独证明时间表由确定性规则生成 |
| `deadlines.diagnose` | 核对已有三表及映射身份，计算显式β列表的期限/余量、M/L阈值；不重新排程，不自动选择β |
| `deadlines.inherit_deadlines` | 按显式逐请求来源复制期限；S7新增请求须显式指定同相对期限规则和目标释放，旧请求不能删除或改释放；非S1不允许删场景 |
| `deadlines.compare_deadlines` | 在目标输入上检查结构合法性，再报告继承期限的余量与准时性；超期与结构非法分开 |
| `deadlines.counts` / `bounds.lower_bounds` | 分开统计共享身份、执行实例、请求和工作量；输出关键路径/设备子集容量下界及单列的固定映射界，不调用LP |

推荐调用顺序：

```python
refs = build_references(explicit_contract)
report = diagnose(explicit_contract, refs,
                  betas=["1", "1.3", "1.6", "2"],
                  reference_topology_id=explicitly_chosen_topology_id)
```

示例列表是原协议的待校准候选，API没有默认β。`check_timetable(..., required_opp=None)`可检查一般混合档安排；指定H/M/L时还检查整表对应频档。成功状态仅`TIME_STRUCTURAL_VALID`，热和能耗状态恒为`NOT_EVALUATED`，不产生SAFE、U或最优性证明。

## 首版限制

1. 输入是显式、有限、单次场景DAG；可含显式跨请求依赖。支持多场景、多请求和四执行单元，但人工测试不等于规模性能验证。
2. S2增量、S3细分、S4改拓扑、S5压力、S7复制请求由测试人工提供。**尚无这些变换的正式生成器。** 期限继承接口核对日期及来源关系，不证明任意调用者的S3变换保持了全部设备画像/功耗语义；测试只对声明的手工变换检查不变量。
3. 输入合同不含活动功率、漏电、RC、温限和完整评价窗口。导出到正式输入、原合法器和连续热评价器的端到端适配尚未实现；正式安全门没有被关闭或替换。
4. 调度器以有限区间扫描实现最早合法空档；没有预设400 ms上限。计算超时控制和批量校准账本须在校准执行入口中另行冻结，本阶段只运行小夹具。
5. 未选择随机分布、S4参考拓扑、S7释放偏移、场景组合/权重、校准种子和覆盖、明显余量阈值或窗口规则。上述参数不能从人工示例推定为正式设定。
