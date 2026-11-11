# 严格认证模板缓存：只读审查与冷helper全覆盖重放

修正后版本的严格性审查通过，可作为主代理完整性能构模前的验收证据；这不是求解器性能或统计显著性证明。审查源码milp.py SHA256为 `98c1ad5735d06e07ad8cb89e8f90e99542c1a1142ef2e7b42439fa47d5eec182`，joint_state_support.py保持fe6216af版本。

## 复用的严格性依据

模板键包含源码/数值/输入namespace、source与target角色计数、完整顺序别名布局、每个实际binary64上下界的float.hex及内部rational盒、五组全部有序区间系数的lo/hi文本。不同变量名字仅更换列身份，不影响这些已绑定的数值行；有相同别名等价布局时probe的重复变量覆盖语义也相同。

miss仍通过原Model.affine_conditional_eq产生完整10行，以verify_gate_off_rows在实际导出盒上做精确Fraction冗余检查，任何正违反均抛错。通过后只缓存不可变标量proof tuple。hit需要同一个完整键，返回独立state报告副本，不能修改cached proof。它表示复用同一已认证数值模板，不是跳过未经验证的新行，也不应被写成每hit重新做了Fraction求和。

probe按不可变box/layout复用，不改变盒后保留旧bound/template cache；源码、runtime callable、输入或数值context变化清entries和probes，随后完整重认证。每Model冷缓存，无跨模型或磁盘warm缓存。source hash、actual input digest、完整key、probe建立、export和verify均在被测helper及构模调用路径内部计费。活动cache上限4096；public template_catalogue是证据journal，可保留已清条目，不应把该journal的全部内存误称只受4096活动项上限约束。

## 发现并修复的首版边界

首版64cac462的身份检查只读取thermal.UP/DOWN别名。当实际interval kernel的UP/DOWN单独重绑定而thermal别名仍旧时，可遗漏失效。父代理决定按正确性缺口修复，未把这次改动当性能调参；首版源码、测试及耗时保留，未准其进入完整R1性能对照。

rev2先断言I的相关算术函数实际globals均为thermal._kernel.__dict__；同时保存实际kernel UP/DOWN、thermal别名四个Context对象及其precision/rounding/Emin/Emax/clamp/capitals/traps，并持有Model/I namespace callables与verifier等对象引用。kernel-only重绑定改变runtime身份，原context.prec变更改变numeric token，均清除proof与probe。新独立第6项测试已覆盖UP/DOWN分别仅重绑定和UP.prec原对象变更，均记录失效并重新认证。sticky flags不参与计算值，故不作为失效条件。

正常证明假设单线程冻结构模及通过原调用入口，不宣称防御任意外部并发篡改Python标准库或缓存私有数据。实际冻结R1角色列互异，完整重放覆盖其实际布局；其它别名布局的安全性由完整布局键及同probe映射构造论证，不冒充已穷尽所有别名组合。

## 独立冷helper重放

按照主代理明确授权，读取fe6216af保存的ON矩阵实际names/lb/ub、原输入、events、2938个删除w身份和逐state原gate0证书。只创建一个Model审计上下文壳，直接装入实际浮点盒；没有调用build_model，没有创建原任务options或任何调度约束。每个原事件区间调用新helper，比较其每state的checked_rows、gate_fixed_value、maximum_residual、minimum_slack、exact_binary64_box五字段与原版保存证据逐项相同。原身份集合也完全同。

424区间、2938删state、29380代表行全部通过。全程冷cache：284个miss直接生成并认证2840行，2654个hit复用已认证模板，共38个probe；无clear/identity invalidation。所有源码及输入hash结束保持，完整模型构建0、物理评价0、求解0、失败及重试0。这里使用静态原系数计算，不是热轨迹评价。

真实执行UTC2026-11-11 09:11:58.616108–09:12:01.934193，即北京时间17:11:58.616108–17:12:01.934193，3.318107秒。这个时间包含该验证脚本的数据读取与验证，**不是**正式静态构模性能样本，也未向后续性能worker传递暖cache。预冻结协作预算90秒，外部timeout120秒，均未触发。

```sh
python3 research/chapter3_pruning_audit_optimization_20261111/safety_review/replay_archived_audits.py freeze > research/chapter3_pruning_audit_optimization_20261111/safety_review/replay_freeze.stdout.log 2> research/chapter3_pruning_audit_optimization_20261111/safety_review/replay_freeze.stderr.log
timeout 120s python3 -u research/chapter3_pruning_audit_optimization_20261111/safety_review/replay_archived_audits.py run > research/chapter3_pruning_audit_optimization_20261111/safety_review/replay.stdout.log 2> research/chapter3_pruning_audit_optimization_20261111/safety_review/replay.stderr.log
```

工作目录/workspace/paper；Python3.12.14、NumPy2.3.5、Linux。完整冻结hash见replay_plan.json，逐区间结果replay_interval_results.json，统计及开始结束replay_result.json，原始stdout/stderr保留。本审查不修改生产源，不推送、不合并、不覆盖历史。

## 对其它验收证据的只读检查

已阅读validation/rev2/legacy_joint/results.json和cache_checks/results.json：原7项通过，32组合合法12→12，228状态投影保留，24次新物理评价科学字段一致；新6项cache测试通过，含miss/hit/clear同原精确证书、box/coeff/input/runtime变化重认证、容量清除、actual-kernel context失效。旧版ON物理回执12份是标明hash的复用，不能记为rev2新热调用。原8项结构回归及累计预算记录由validation主报告统一报告。本审查只读已有测试证据，没有重复执行它们。

严格认证能力仍限精确整数选项模型和实际binary64盒，不延伸为LP松弛或近整数容差管道不变。完整静态矩阵、2938身份、Big-M/外包、目标及能量强化的最终运行审计仍由主代理/静态执行器完成；本报告不预先声称性能加速。
