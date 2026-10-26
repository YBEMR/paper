# K194：K193独立穷举的一次性执行

用户回复“继续吧”，承接K193所列独立枚举范围：最多1550次、每次最多10秒、共同2400秒根／2700秒日历，不重试、不自动续跑。**不授权整体MILP、HEFT、原C、旧期限或长预算队列。**

- `run_once.py`：分离准备、监督启动和worker；parent/child共用同一绝对根时钟，保存原始回执后才接纳和写账本；监督器只管理自己的Python进程。
- `admission.py`：同输入／候选／合法性身份核对、四节点连续温度与能量守恒回执检查；仅接纳两截止前形成的内层证据，外层迟返不抹掉及时证据。
- `test_worker.py`：9项纯生命周期检查，包括1550个假回执、模拟监督启动、根截止和故障保留；所有夹具不能升级成正式参照。
- `test_admission.py`：22项假回执检查，无热积分或优化。旧K192只用于构造测试形状，不作为本批初解或缓存。

31项纯检查通过。实际执行前必须先在新目录`prepare`，核对声明SHA，再只`launch`一次；已有声明消费后不恢复。

```powershell
& 'F:/Anaconda3/python.exe' -B 'research/chapter3_experiments/small_exact_execution/test_admission.py'
& 'F:/Anaconda3/python.exe' -B 'research/chapter3_experiments/small_exact_execution/test_worker.py'
```

真正运行目录另存于`results/small_exact_execution01`。源快照／输入／清单hash及账本用于防止误混，不宣称抵御恶意篡改。枚举覆盖独立于MILP，物理评价仍共用原连续核。包络迟于根截止形成时必须标明，不能冒充预算内完成认证。
