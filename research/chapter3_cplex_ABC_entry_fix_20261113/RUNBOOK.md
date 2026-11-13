# D285 冻结使用说明
本轮只完成准备及控制测试。计划未授权科研执行；不得复用 D284 已消费批准。

下一次独立用户批准须绑定包含本计划及源码的提交、计划 hash、新 approval_id 与实际用户消息；字段遵循 plan.json 的 approval_schema，maximum_solve_calls=3、每组=1、A/B/C、600/550 秒、retries=0。科研命令仅在新批准后可用：

```powershell
F:/Anaconda3/python.exe -B work/cplex_ABC_v3/batch.py --workspace . --plan work/cplex_ABC_v3/plan.json --expected-sha ff129eb1f340ad067b891542b486ec9c5f0da19c046371eacd167cb9bc75bbd5 --approval <新科研批准文件>
```

一次性生产目录是 work/cplex_ABC_execution_v2。故障后不得删除该目录补跑。

无科学入口验收另用 --entry-only、--control-output <新的独立控制目录>，批准文件必须为：
- protocol: D285-CONTROL-ENTRY-ONLY-v1
- decision: CONTROL_ONLY
- plan_sha256: 当前计划 hash
- maximum_scientific_workers: 0
- maximum_solve_calls: 0
- frozen_commit: 包含对应计划/源码的完整提交 SHA

此模式运行真实控制器、原 Job 和身份读取，但在工作进程创建前退出，不能消费生产目录或启动 CPLEX。不要把其成功回执解读为原生求解验收。

Git 主程序路径和 hash 已冻结；丢失/漂移时停止，不回退 PATH、不临时安装或更换版本。

