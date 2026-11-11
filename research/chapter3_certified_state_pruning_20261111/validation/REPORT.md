# 有证书联合状态剪枝：独立小域验收

唯一冻结测试批次通过，7项新测试和原8项纯结构回归均无失败/错误。这里验证的是一个独立、显式收窄选择域的测试夹具，不是完整原R1性能对照；未构建未缩域R1、未调用任何LP或MILP求解器。

## 冻结域与科学输入

使用已冻结auto-L R1双场景全部12次Stage执行、原400ms窗口、5ms起点网格、初温50°C、80°C温限、请求/依赖/权重/平台及所有模式中的原duration/power值。仅fixture取原模式/起点子域，原科学输入文件不改。模式选择来自此前归档全H固定时间表的设备/H身份，C.post另外保留原CPU1/L模式以包含原9.6ms非整数时长。A.main取10或15ms，A.post取40或45ms（各场景独立）；其余按归档起点。

全部原Stage和场景数据逐字段不变；fixture的stage_modes逐项是原模式的完整字典子集，没有手改时长、功耗或温度。fixture显式输入在execution/fixture.json；config在execution/config.json。32个完整选择组合全部独立判定：12个结构合法，全部12项的两侧完整合法身份集合相同。该夹具不重新搜索真实R1调度，没有优化初始化或求解暖启动。

冻结时间UTC 2026-11-11T08:15:00.384232+00:00，计划hash `3e8fb82d15a0eb3f02cb20d0655ccf3c65f13ce8a28eabe42badef3fc7524636`。上限为96完整组合、64次真实candidate电热评价、240秒共同测试日历、每次物理评价≤10秒，无重试。外层launch_validation.py将新测试和旧纯结构回归一起限制在240秒内。

## 验证结果

- OFF/ON模型使用相同fixture/config/既有baseline flags；propagate_support两侧均True，仅新prune_joint_states不同。原options/events相同；所有共同变量的导出上下界逐name重编号完全相同；所有存活温度/能量条件行，包括系数、rhs、Big-M和舍入metadata，逐name规范化后完全相同。
- 两小域模型分别488/486变量、1609/1589行、17个option。剪去2个w和20条电热行；这不是完整原R1的规模结果。
- 独立合法性及auto-L状态oracle不调用新分类器或生产合法性helper；32完整组合中12合法，逐两场景共228个区间状态投影全部保留，完整合法集合12→12。
- 12个完整合法候选各在OFF/ON真实评价一次，共24次，全部双场景SAFE，覆盖完整400ms尾段。完整电热科学字段逐字相同，比较仅排除计时字段；既比较能量上下界，也比较连续峰温证据、合法性与控制状态，未仅比较一个目标值。12方案能量区间覆盖约1.079562844035–1.084886371304J；最大峰温上界约53.127365662632°C，均非新算法收益。每次原始完整receipt保存在physical_*_OFF/ON.json。
- 对旧OFF模型对应被删w的20条原电热行，用独立Fraction循环对实际导出binary64盒求gate=0最大残差，严格≤0；不是调用被测helper复核自身。对新能量强化约束的53个active-state/source-row组合，独立精确计算cut残差减原lower-energy行残差在原盒上的最大值，全部≤0；一热gates和source row映射逐项匹配存活状态。
- 数值负例：把冗余row的rhs降一个ULP造成严格正违反，helper拒绝；把导出依赖rhs减弱到路径margin=0，状态保留UNKNOWN；篡改精确onehot拒绝。另测2^-40正margin可作精确数值证明，但exceeds_path_row_tolerance=False，明确不能把精确矩阵语义混同求解器容差管道。
- cap=0所有状态保留UNKNOWN_CAP；production物理gate0审计被故意置为失败时，build_model抛错，不能返回未经验收的ON模型。该人为失败是预先固定的负例测试，不是科研失败重跑。
- 默认关闭的新路径与冻结pre-feature源码在无物理的小域构造上names/rows/boxes/c/indices/options完全相同；strict bool和hold-last不支持时的拒绝均通过。
- 原8项纯结构回归通过：266目录完整合法集186→186，512条删除证据重放。未运行旧物理集成测试的其他fixture，没有附加热调用。

本批5次fixture build_model尝试包括2个物理模型、2个默认OFF无物理回归模型和1个故意门审计失败的模型。临时删状态行preview不是完整调度模型。真正原R1新构模次数0；LP/MILP次数0。实际测试热调用24≤64，外层12.122046秒≤240，无超时或重试。

## 命令与真实时间

工作目录`/workspace/paper`。实际冻结/运行命令：

```sh
python3 research/chapter3_experiments/test_joint_state_support.py freeze --output research/chapter3_certified_state_pruning_20261111/validation/execution
python3 -B research/chapter3_certified_state_pruning_20261111/validation/launch_validation.py > research/chapter3_certified_state_pruning_20261111/validation/controller.stdout.log 2> research/chapter3_certified_state_pruning_20261111/validation/controller.stderr.log
```

controller实际子命令及起止在command_receipts.json。新测试程序为`python3 -B research/chapter3_experiments/test_joint_state_support.py run --output research/chapter3_certified_state_pruning_20261111/validation/execution`；原回归命令为`python3 -B research/chapter3_experiments/test_option_support_structural.py --output research/chapter3_certified_state_pruning_20261111/validation/old_structural_regression`。

外层批次UTC 2026-11-11T08:15:39.420927+00:00–2026-11-11T08:15:51.542964+00:00，即北京时间16:15:39.420927–16:15:51.542964，12.122046477秒。新测试内部UTC 2026-11-11T08:15:40.171464+00:00–2026-11-11T08:15:51.108892+00:00，10.937455032秒。原结构回归外层0.315957秒，内部0.185305秒。源文件在冻结及运行结束时hash完全一致。

主要证据：execution/plan.json、fixture.json、config.json、complete_candidate_sets.json、pruning_report.json、exact_gate_zero_and_energy_cuts.json、results.json和24份physical receipts；原回归证据在old_structural_regression/；command_0/1.stdout.log与stderr.log保留完整输出。frozen/保存六份本批实际代码。

## 限制与验收层级

这是小域有限全集和可重放精确数值检查，不是对所有输入的经验性证明。物理复核两侧使用同一原电热评价器，不称独立热实现；独立的是完整结构合法性、状态投影及binary64矩阵门0/强化蕴含的精确有理审计。测试验证原整数y语义及现有数值行的必要支持，不承诺LP松弛多面体或求解器近整数/容差管道完全相同。本批未声称任何求解加速，生产实装全R1静态配对仍由主任务按全部验收门放行。未提交/推送/合并。
