# D283 运行说明（当前禁止科研执行）

入口、输入路径和批准均固定，不提供自动重试或参数覆盖开关。仅在用户另行批准一次本冻结提交后，才能建立新批准记录；本轮没有批准记录、没有科研执行目录。

批准记录须包含 plan.json 内 `approval_schema` 的全部字段，`frozen_commit` 为包含本计划与源码的实际 Git SHA，`plan_sha256` 为 `3f09e26d153fe8e59fb05b75d626248b1341a4ed16c72563e3806f7e73456378`，`user_message_reference` 必须指向真实新用户决定。批准文件不是由计划本身自动生成的授权。

待独立批准后，唯一入口为：

```powershell
& F:/Anaconda3/python.exe -B work/cplex_C_solve_v2/controller.py --workspace . --plan work/cplex_C_solve_v2/plan.json --expected-sha 3f09e26d153fe8e59fb05b75d626248b1341a4ed16c72563e3806f7e73456378 --approval <新批准文件路径>
```

发布目录下 executor 与本工作目录源码字节相同。执行器还校验批准 Git 提交中的源码/计划，不接受临时修改后沿用旧批准。执行目录固定为 `work/cplex_C_scientific_execution_v1`，独占创建后即消耗一次授权；即使未进入 solve，也不自动重跑。

本轮仅运行下列纯控制入口，未运行上述科研入口：

```powershell
& F:/Anaconda3/python.exe -B work/cplex_C_solve_v2/test_control.py <新的人工控制输出目录>
```

控制入口使用人工四列 API、人工 SAFE 回执和小型 Python 进程，不导入 CPLEX、不评价真实任务。其中人工 `STRICT_ENERGY_IMPROVEMENT` 不能当成论文结果。

历史冻结代码不改；若代码、来源、参数或窗口需要改变，必须形成新冻结记录并重新申请，不在已授权一次调用中切换。普通失败/超时停止；所有未决与成本如实交付。
