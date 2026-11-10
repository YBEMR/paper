# 工作包B：七方案400ms温度轨迹与时间均温

已复用指定提交中七个终解的14份完整场景凭证，计算56个节点/场景时间均温与每方案最坏场景/节点均温；没有新增热积分或调度搜索。时间范围完整保留400ms及任务后的空闲尾段。

|方案|完整系统能耗上界 J|连续峰温上界 °C|最坏节点/场景时间均温上界 °C|对应场景/节点|
|---|---:|---:|---:|---|
|t50_milp|0.870308316279|51.078647076|49.021997719|AB_offset_0ms / NPU0|
|t50_heft|0.870324370116|51.078597933|49.021964518|AB_offset_0ms / NPU0|
|t50_sa101|0.885640557396|51.434833787|49.357836076|AB_offset_0ms / NPU0|
|t50_sa102|0.885634809181|51.526083492|49.353655853|AB_offset_0ms / NPU0|
|t50_sa103|0.885627434135|51.444244984|49.343567508|AB_offset_0ms / NPU0|
|t50_sa104|0.870335077092|51.078597933|49.021964518|AB_offset_0ms / NPU0|
|t50_sa105|0.870314698381|51.078345091|49.021802231|AB_offset_0ms / NPU0|

均温用原记录的有向包络积分逐端点作精确有理数变换：`Ta + integral(T-Ta)dt/(2/5 s)`；完整区间与积分值在 `node_time_means.csv`，每方案取八个节点/场景均温的最大值，不作场景串接或综合加权得分。最大者区间重叠时保留全部可能最大对象。

原方法凭证与原post凭证比较：加权总能量中点最大绝对差 0 J；峰温区间中点最大绝对差 0 K。逐项差区间、区间距离与是否重叠见 `B_metrics.json`。此处比较既有两份记录，未重新求解或形成新的独立数值证书。原方法及post七份均为SAFE。

完整系统能耗仍为唯一优化目标；峰温、时间均温和运行时间均为描述性指标。没有计算寿命延长比例或加权多目标分数。

## 图与原始点

`figures/` 有14张场景图，每张四节点曲线，PNG/SVG双格式。补入各场景原声明t=0入口50°C，灰区标出最后任务完成后仍保留的空闲尾段；×号是原凭证保存的峰值点见证。折线仅连接原数值面板末点展示，不能据此宣称连续曲线安全；连续安全依据为原全窗口峰温包络与完整SAFE凭证。

- [t50_milp__AB_offset_0ms](figures/t50_milp__AB_offset_0ms.png)
- [t50_milp__AC_offset_0ms](figures/t50_milp__AC_offset_0ms.png)
- [t50_heft__AB_offset_0ms](figures/t50_heft__AB_offset_0ms.png)
- [t50_heft__AC_offset_0ms](figures/t50_heft__AC_offset_0ms.png)
- [t50_sa101__AB_offset_0ms](figures/t50_sa101__AB_offset_0ms.png)
- [t50_sa101__AC_offset_0ms](figures/t50_sa101__AC_offset_0ms.png)
- [t50_sa102__AB_offset_0ms](figures/t50_sa102__AB_offset_0ms.png)
- [t50_sa102__AC_offset_0ms](figures/t50_sa102__AC_offset_0ms.png)
- [t50_sa103__AB_offset_0ms](figures/t50_sa103__AB_offset_0ms.png)
- [t50_sa103__AC_offset_0ms](figures/t50_sa103__AC_offset_0ms.png)
- [t50_sa104__AB_offset_0ms](figures/t50_sa104__AB_offset_0ms.png)
- [t50_sa104__AC_offset_0ms](figures/t50_sa104__AC_offset_0ms.png)
- [t50_sa105__AB_offset_0ms](figures/t50_sa105__AB_offset_0ms.png)
- [t50_sa105__AC_offset_0ms](figures/t50_sa105__AC_offset_0ms.png)

`saved_trajectory_points.csv` 区分原面板末点、补入的声明入口及原峰值点见证；均未调用新热评价。

## 来源、计时与验证

固定源提交 `4339bdcc7dc6d37adf42963ed731f78d5f8ff63e`。`plan.json` 列出七个固定候选的canonical身份与所有源文件SHA256/Git blob，准备阶段逐文件核对提交与工作区字节完全相等。执行前后再核对源哈希；运行方案哈希 `f042dc6b29e8c5dc828a81ff57d280d6aa6523585bb5a413b27429323b3899e5`。

后验派生/绘图开始 2026-11-10T03:28:07.960685+00:00，结束 2026-11-10T03:28:15.275664+00:00，耗时 7.314988秒，单独记录，不并入原方法搜索耗时。准备、测试及实际命令日志见 `command_*`。

实际命令（cwd `/workspace/paper`）：

```text
python -B research/chapter4_scheduler/results/evaluation_workpackages_20261110/workpackage_B/reuse_trajectories.py prepare
python -B research/chapter4_scheduler/results/evaluation_workpackages_20261110/workpackage_B/reuse_trajectories.py derive
```

范围仅指定七份固定终解、独立AB/AC的400ms单轮描述；没有延长窗口、改变部署/频档/时间表、串接场景、周期稳态求解、参数扫描或新优化。单轮均温不能替代周期稳态峰温，也不能推断长期寿命或算法普遍性。
