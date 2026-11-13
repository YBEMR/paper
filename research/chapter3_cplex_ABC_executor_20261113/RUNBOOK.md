# D284 冻结入口（本轮不执行科研）
计划处于 FROZEN_AWAITING_INDEPENDENT_APPROVAL；execution_authorized=false。准备与纯控制测试已完成，不要将下列命令作为当前授权。

下一次用户独立批准后，创建与 plan.json 中 approval_schema 一致的新批准文件：新 approval_id、实际用户批准消息引用、包含计划与全部源码的 40 位提交 SHA、准确计划 hash；最大总 solve=3、每组=1、A/B/C、600/550 秒、不重试。不能改用旧 D283 批准。

在原工作区、原 Python/CPLEX 环境运行：
```powershell
F:/Anaconda3/python.exe -B work/cplex_ABC_v2/batch.py --workspace . --plan work/cplex_ABC_v2/plan.json --expected-sha bd5c73303c83e862ccd484df7db9dcbe1a2cf73ec63f3dc989784b019a2005d6 --approval <新批准文件>
```
批次只允许创建一次 work/cplex_ABC_execution_v1。任何部分失败不得删除该目录重跑。每组控制与工作进程由一次性 claim 与 Job 保护；完整参数、依赖、科学源码、矩阵身份分别核验。冻结提交及本机工作包字节必须一致。

测试命令（使用未存在的新输出目录；纯模拟）：
```powershell
F:/Anaconda3/python.exe -B work/cplex_ABC_v2/test_abc.py <新的控制输出目录>
```
不需要重复测试来取得科学执行权限。

结果必须区分实际原生 MaxTime、分阶段完整成本、原生目标与完整评价能耗、回调与最终候选、状态与独立证明。批次共同比较只汇总窗口内封存证据；原始日志与失败记录全部保留。事后审计不重新求解/构模/热评价。

