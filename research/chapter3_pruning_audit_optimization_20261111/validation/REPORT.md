# 严格认证缓存：独立验证和物理小域

最终rev2验收通过：原7项联合测试、原8项结构回归及6项新增缓存边界测试，共21项全部通过。原7/8文件未修改，与fe6216af逐字节一致。本子任务没有构建完整未缩域R1，没有LP/MILP求解，不报告性能收益。

## 版本与必要修订

基准`fe6216afcd0e8d94742adbc0ff62d70651dd60ba`，旧ON源码SHA `43e259d03ce5c65e38a9fb1148fdd45acfecb3b4fb132e1f6d14ea34963e65b4`。当前通过源码SHA `98c1ad5735d06e07ad8cb89e8f90e99542c1a1142ef2e7b42439fa47d5eec182`，joint_state_support.py保持原d4f7ee版本。独立新增测试正式路径为 `research/chapter3_experiments/test_joint_audit_cache.py`，SHA `a7536a384d476c6e452b696e55595c3a60845dd9f04fbbcf64f3582c5c2a8345`。

第一版64cac源的20项测试实际全部运行通过，但独立源码审查发现其缓存身份未覆盖实际thermal kernel上下文单独重绑定。暂停请求送达时该批次已经全部结束，不能撤销已消费的36次热评价；首版整体不接纳，结果、源码和计划全部保留。随后仅修复这一正确性缺口并加入UP/DOWN重绑定/精度变化测试，未作性能参数调优。

## 固定小域和比较方式

保留原auto-L R1的AB/AC双场景、全部12次Stage、原物理参数、四节点RC、50°C入口、80°C温限、400ms窗口、原模式的持续时间/功率及依赖/共享部署。仅在独立fixture声明原mode/start子域，32个完整安排，其中12个完整结构合法，状态投影228个。真实R1输入不改。

- rev2原7项测试重新实际运行24次原完整电热评价（12候选×OFF/优化ON），全部SAFE，完整科学字段相同，只忽略计时字段。
- 独立新测试另构建fe原版ON和优化ON两份小域模型，所有names/rows（含Big-M、rhs_interval、rounding_allowance）、bounds、目标、整数、options、events、states、candidate_states及energy_bound_certificates逐项完全相同。完整合法身份12→12，228状态投影保留。
- 为不超额，rev2不再次评价旧ON的12个候选，而复用rev1已经实际运行的固定fe旧源码回执。freeze绑定旧源码、fixture、config及每份旧回执SHA；候选/输入身份及完整科学字段与rev2新ON逐项相同。这12份是复用已有证据，**不是rev2新跑**，其原成本仍计入累计账本。
- 同一原热评价器用于物理两侧，不称独立热实现；独立部分为完整结构合法性、状态投影及原/新数值行审计。全部评价覆盖400ms含空闲尾段。

## 缓存边界检查

6项新测试覆盖：旧/新完整数值模型及状态证书相同；完整物理回执相同；cold/miss/hit/explicit-clear与原版逐state精确slack相同；source/target盒、完整系数及其RHS常数、声明和实际input摘要变化重认证；runtime verifier更换不能从既有hit绕过；容量清空后重新认证；实际kernel.UP和DOWN单独重绑定以及precision属性改变均使原cache失效。

每次首次miss仍调用真实verify_gate_off_rows，hit只复用同模板已完成的严格证明。独立计数样例：miss4、hit2、真正执行严格检查40行，表示的逐state行60；clear一次后再次严格执行。原7项另检查一个ULP正违反拒绝、篡改onehot拒绝、零margin/超限保留，以及生产门检查故意失败时不能返回模型。

这些说明冻结精确整数y语义及actual binary64盒上严格冗余认证未被缓存替代成容差检查。不声称保持整个LP松弛或任意求解器近整数/行容差接受管道。

## 预算、时间与调用计费

|批次|测试数|新增真实热调用|接受状态|外层wall/s|
|---|---:|---:|---|---:|
|rev1|7+8+5=20|36|整体不接纳，代码审查发现上下文身份缺口|72.192997|
|rev2|7+8+6=21|24|接受；旧ON12回执只复用，不再评价|13.098141|
|累计|分批记录，不合并成“41项最终验收”|60|上限64|85.291137|

总测试运行墙钟上限240s，实际累计85.291137s；准备、等待修订和报告时间另披露，不伪装为测试运行。每次热评价≤10s，无LP/MILP，0完整未缩域R1模型。每批7项构模尝试5次（含预设故意失败负例）＋新测试中旧ON/优化ON各一次，总计每批7次小域build_model尝试、两批14次；临时探针/合成cache对象不算完整调度模型，cache strict成本另有stats。

北京时间UTC+8：

- rev1实际 `2026-11-11T17:04:47.953034+08:00` 至 `2026-11-11T17:06:00.146021+08:00`。
- rev2实际 `2026-11-11T17:10:01.901631+08:00` 至 `2026-11-11T17:10:14.999764+08:00`。
- rev2主测试11.408346s、旧结构回归0.265011s、新缓存测试1.424448s；有独立回执，非性能配对数据。

## 命令和证据

工作目录`/workspace/paper`，Python3.12.14/Linux。两个修订的完整freeze/run命令和实际子进程argv可由源码与回执核对：

```sh
python3 research/chapter3_pruning_audit_optimization_20261111/validation/launch_validation.py freeze
python3 -u research/chapter3_pruning_audit_optimization_20261111/validation/launch_validation.py run
python3 research/chapter3_pruning_audit_optimization_20261111/validation/rev2/launch_validation.py freeze
python3 -u research/chapter3_pruning_audit_optimization_20261111/validation/rev2/launch_validation.py run
```

每个launcher依次实际调用原7项、原8项和新cache测试；记录在各自command_receipts.json、command_0/1/2.stdout.log和stderr.log。完整fixture、计划及源hash在legacy_joint/plan.json、cache_checks/plan.json，最终对应rev2子目录；rev2缓存计划还保存复用旧回执的12个SHA。原版fe源码以baseline_milp.py.txt保存，新cache首版测试源码保存cache_checks/test_joint_audit_cache.rev1.py.txt，最终源快照在rev2/source_snapshots/。

验收机器结果为acceptance_summary.json；累计成本为cumulative_budget_ledger.json。rev1根目录结果保留不覆盖，source64cac快照另在同任务implementation/milp.cache_rev1.py，修后98c1快照在implementation/milp.cache_rev2.py。对完整R1的16919变量/94958行/990904非零和2938状态身份，仍须由父任务冻结的后续全域静态配对核验，本子任务不冒充已执行该配对。

没有推送、合并、改历史或为漂亮耗时重复调参。唯一复验是必要上下文身份正确性修复，并完整计入成本。
