# K191：执行K190独立连续LP诊断

用户确认优先执行报告协议的一次300秒LP诊断。仅取消原1681项整数性，原K187七数组/界保持；0热积分、0新SAFE/U/独立界、0重试，不自动整数释放/增广/3600秒。总日历480秒沿K190提案作为停机留证上限。

`run_once.py prepare`绑定原协议、原数组、K189回执、本机接口源、K190纯检查及新入口全部hash，并保存新授权；旧提案原样保持未批准历史。`precheck.py`只作纯fakes及原数组静态检查，硬屏蔽真实子进程/优化入口。通过后`run_once.py execute`执行唯一worker；排他launch/method/request文件禁止二次启动。

Python从科学导入与原载荷读取前启动300秒绝对根时钟。K187原x0及K189向量仅作静态数值见证，不传入MATLAB；实际payload仅含c/A/b/Aeq/beq/lb/ub，并在发布请求前再次读取逐项比较。LP允许分数坐标，原整数距离仅记录。

MATLAB采用独立`solve_lp_once.m`，只进入一次`linprog`。同进程内创建并读回dual-simplex/隐藏Preprocess none/ConstraintTolerance1e-9/OptimalityTolerance1e-7/MaxIterations2049240/Display off；任一不符就保存错误、不进入求解。MaxTime在请求剩余和MATLAB进程guard中取小，扣除读取/准备/归档成本；最终响应中的实际值为准。原生选项核查、MATLAB启动、交接和返回数值接纳均计入原300秒。无可用OutputFcn，原生标准输出、返回output/lambda及警告原样保存。

复用K189冻结的通用RootBudget/宿主资源检查/外层进程监督，及K187冻结桥中的发布读取与拥有进程清理函数；不使用其intlinprog solve入口。归档控制器的REPO/OLD/FROZEN仅作运行时路径重绑定；不编辑归档源码。纯预检专门核对该绑定。

根截止后不新接纳，清理最多40秒、worker返回监督420秒且受480秒日历约束。原生发布后退出仍按原读取器先读完整文件；清理未证与数值结果分列。所有本次进程按PID/创建时间确认退出，保留其他会话进程。

本结果只诊断独立LP数值路径，不等同于intlinprog内部根LP。原始目标可行值不直接作为MILP下界；solver最优状态不提升为独立最优证书。小域完整链设计是独立零调用材料，不消费该LP预算。
