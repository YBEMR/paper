# 第三章共同输入适配与语义预检

本包将已有校准任务转换为正式输入合同。物理平台、响应公式、连续热评价器及旧算法不改；原C的随机任务邻域泛化仍未实施。

## 输入与输出

```python
from research.chapter3_formal_input_adapter.core import adapt_bundle

result = adapt_bundle(
    bundle, deadline_receipt, window_receipt,
    member_key="2", config=original_config, instance_id="declared-instance-id",
)
config, instance, receipt = result["config"], result["instance"], result["receipt"]
```

调用者必须显式提供已选β的期限回执和组窗口回执。适配器不选择β、不生成根任务、不重算期限或参考时间表。它校验原bundle、期限、窗口成员hash，以及原物理来源、频率、精度和执行规则。

- 请求和执行实例改为`场景ID::原ID`，保存双向身份表；`shared_stage_id`保持。
- 在当前场景子集内对共享Stage求合法设备交集，逐设备/OPP展开精确时长与活动功率；不重复乘工作量倍率。
- 保留显式依赖、请求释放/绝对期限、场景权重、入口温度和共同窗口。未出现的Stage不进入模式表。
- 从原配置显式声明auto-L；config的旧默认窗口不作为实际W，实际W只由`instance.window_ms`提供。
- 不接收参考映射、参考时间表或历史最优解，不能据此固定设备或免费初始化。

当前只支持本项目既有四节点物理来源与校准合同，不宣称通用硬件导入。whole/HEFT/SA的返回标记为`COMMON_INPUT_ONLY_NOT_RUN`；原C标记为仍需邻域泛化。数据合同相同不代表算法搜索域相同。

## 可复跑人工检查

```text
F:/Anaconda3/python.exe -B -m research.chapter3_formal_input_adapter.run_checks --output research/chapter3_formal_input_adapter/results/<新目录>
```

输出测试明细、源码快照/hash和旧科学源码前后hash。该入口禁止优化器、热积分、算法搜索及外部进程；人工参考时间表仅用于测试，不是随机校准或正式实验。

## 有界完整电热预检

`semantic_precheck.py`分prepare/execute。prepare先保存来源hash、完整输入/候选、预算和停止规则，execute拒绝源码漂移、载荷漂移、重复消费或旧输出目录。

固定两份实际候选，各最多60秒、合计120秒，整包300秒：

1. 归档C01、6 Stage、S1前2场景、显式β13/10、共同230ms窗口；归档H表只作验证候选。保留50°C/80°C、原四节点和auto-L。
2. 原P2/R1既有违规候选，原78°C/80°C与400ms窗口，完全保留原输入；这是旧输入热违规回归，不能充当新DAG违规证据。

任何实际状态不符预期、技术错误或预算截止都保存并停止，不换样本或重试。附加超期候选只做时间检查；零面板资源注入检查未决，求解截止仅用纯模拟分别检查有/无先前SAFE。**模拟不等于本轮发生原生求解超时。** 本包没有MATLAB、MILP、HEFT、SA搜索调用，也不产生方法排名或正式SR/E统计。

成功只说明指定小样本的输入与完整电热合同连通，不能代替多请求实际热验证、真实求解入口验证、大规模成本或50根性能实验。
