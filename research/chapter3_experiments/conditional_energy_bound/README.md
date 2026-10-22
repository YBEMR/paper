# 部分赋值能量下界：离线接口与预检

此目录提供K169下界的条件化实现，供纯代数预检使用。**尚未接入整体MILP、联动、HEFT或SA。** 不生成起点或时间表，不调用温度传播、积分器、优化器或原批次启动器。

## 输入与返回

```python
from conditional_energy_bound.bounds import prepare, pruning_decision

ctx = prepare(original_full_instance)
root = ctx.bound()
child = ctx.bound({
    'shared_units': {'A.main': 'NPU0'},
    'by_scene': {
        'AB_offset_0ms': {
            'AB_offset_0ms::A_r1::A.main': {'opp': 'H'}
        }
    }
})
```

|字段|语义|
|---|---|
|`shared_units`|固定一个共享Stage的具体执行单元，传递到所有场景／请求副本|
|`by_scene[scene][copy].unit`|限制该副本设备；若身份有其他副本，设备一致性仍传递|
|`by_scene[scene][copy].opp`|只限制该副本工作点，不把其他场景绑到同档|
|省略字段|保留原合法选择，不默认为CPU或L|
|未知／冲突／空模式集|抛出`BoundError`，没有可用界，不返回∞或原问题无解|

不接受起点、顺序、热状态或时序修复字段。原请求期限仍用于活动源下界及原前驱关系；起点、资源、热约束其余部分被放松。因此返回数值不代表存在合法或安全延伸。

`prepare`绑定原始输入SHA并复制输入；后续调用方修改原dict不改变上下文。共享设备支持先取所有副本的交集，包含零权重场景；同一场景内多个请求副本也保留设备一致性。

输出主要字段为精确有理数字符串：

- `lower_bound_J`：三份完整下界的最大值。
- `legacy_conditioned_lower_bound_J`：旧温区功率底值＋在同一部分条件下的活动最小值。
- `capacity_lower_bound_J`：新背景／源响应＋域容量分摊。
- `forced_residency_lower_bound_J`：新背景／源响应＋GPU/NPU增量＋已强制CPU阈值驻留。
- `components.forced_CPU`：各场景的强制任务、最短时长、同核工作量、容量界与DAG链界。
- `input_sha256`、`condition_sha256`：完整输入及显式条件的身份。

`legacy_conditioned`是旧下界原理在该条件上的派生对照，不是修改生产`partial_bounds.py`，也不声称旧API已有逐副本OPP接口。

## 有效性与计量

采用

\[
L=\max(L_{legacy},L_{cap},L_{forced}).
\]

两种新松弛都完整计算一次背景和活动源。`Lcap`按域容量分摊参考基准增量；`Lforced`的模式成本不计CPU增量，再另计CPU阈值驻留下界。二者**整体取最大，不相加**。

CPU阈值集合只含所有剩余模式都属于CPU且不低于该档的任务。阈值驻留取同核最短工作量、总工作量／核数、完整DAG加权链长的最大值。M/H按嵌套阈值的0.30／0.40 W增量分解，不把0.70 W的H全额重复叠加。

背景使用K169的最低基准／最小漏电比较；模式源系数使用所属请求的绝对期限。外部共同0.30 W只计电能，不注热。没有计算实际热轨迹；所用多项式原函数只是通用下界的有理闭式算术。

输入必须满足已声明的auto-L、零额外开销、共享部署范围、独立入口、参考与环境温度相同、被动RC、最低L系数及标量比较前提；不支持时拒绝。验证对象为原P0参数及手写代数夹具，不承诺适用于任意新物理模型。

完整量词与反例见[数学合同](../results/partial_bound_precheck01/review/contract_math.md)。

## 上界与排除

```python
reference = ctx.reference_from_archive(original_result_path, original_postcheck_path)
decision = pruning_decision(child, reference)
```

只接纳原P0两个调用目录中的结果／post及其同级输入、wrapper原件。检查输入、方案、U、原始回执hash、完整场景／窗口、控制规则和原300秒内形成身份；仅读原证据，不重新认证温度。

- `LB > U`：`PRUNE_ENERGY`，该条件没有优于此全域安全见证的延伸。
- `LB == U`：`KEEP_TIE`，保留并列安排。
- `LB < U`：`KEEP`，只表示该界不能排除。
- 无合格U：`NO_CERTIFIED_UPPER_BOUND`，不剪。

参考安全方案无需满足子条件：它证明全问题有一个能量不超过U的安排；因此可排除成本严格高于U的子域。反之，若某份安全方案兼容子条件，其能量就应不小于该条件界。

`compare_exact_bound`只做精确比较，不接纳热安全，也不授权剪枝。`pruning_decision`只接收本地上下文刚生成且未篡改的回执及档案接纳对象；JSON存档需重新计算后再使用。该完整性门是本地软件合同，不是签名或权限隔离。

**这些决定全部是后验预检。** 不删除模式，不启动搜索，不把历史U作为新方法的免费初始化，不把能量排除写作分支不可行或全域已证最优。未来接搜索时需重新绑定同次预算内的安全U，并将准备、计算及记录开销全部计费。

## 可复跑检查

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/conditional_energy_bound/precheck.py --out <新的输出目录>
```

输出目录必须不存在。预检包括P0五题K169界复现、人工模式分项账本、部分赋值单调性、跨场景与同场景多副本共享设备、零权重支持、错误拒绝、精确等号及旧U身份。手写夹具不属于新增研究案例，失败记录与修正版本分别保留。

冻结探针及成本协议见[预检协议](../results/partial_bound_precheck01/review/probe_protocol.md)。原K168提案和期限组16／24记录独立；本目录无真实执行入口。
