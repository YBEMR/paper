# AB/AC 精确等式表示有界验证

**结果：AB 复现了返回现场初解的交付改进；AC 仍限时空返回。双景严格通路验收未通过，无优化增益、无最优或不可行证明。**

## 可定位任务与材料

- 任务：`abac_exact_eq_verify_20261106T135623Z`。连接本机 Windows，Python 3.12.4，MATLAB R2023b；本轮未创建 Codex Cloud 求解任务。
- 源提交：`b359126725646727bd990e5cf7215631bb3d4536`。上游 run_ab.py、diagnose_ab.m 与 exact_equalities.py 的 Git blob 均已逐字节匹配；见 TASK_START.json。
- 输入：原 β=1.3 完整 AB/AC，各六次 pre/main/post 执行，共12次。只测试 A.pre=CPU1、A.main=NPU0、A.post=CPU1 这一共享映射；其他原声明候选保留，不代表全映射搜索。
- 原配置 SHA256：`132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2`；原实例 SHA256：`01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89`。本机原字节保持，不使用发布包的LF转换文件替代。
- 原数学基线399文件不变；实际冻结435文件运行后全部复核一致。原模型、物理参数、候选域、索引与坐标没有更改。

## 离线与接口检查

两景历史请求矩阵仅用于离线代数验证，不把历史x0或候选传入本轮。精确相反不等式对转入Aeq，所有原行覆盖一次；原等式保留，目标、上下界、intcon、x0逐字节保留。没有近似配对、缩放或容差修改。对(a*x<=b,-a*x<=-b)和a*x=b使用相同1e-9绝对准入容差，原行仍负责最终数值门。

| 场景 | 变量 | 原不等式 | 转为等式的对数 | 新不等式 | 新等式 |
|---|---:|---:|---:|---:|---:|
| AB_offset_0ms | 8738 | 40078 | 4346 | 31386 | 4346 |
| AC_offset_0ms | 14014 | 90260 | 4994 | 80272 | 4994 |

运行时每个真实请求重新生成和验证逐行证书，并绑定原/改写 payload 哈希；AB/AC 原payload哈希按请求顺序分别为 `affa9501fc75d8ee6ccc314b3b3043dce88a704f0c63d50691df9ebda7d27001`、`7c6454a946273f5ccc2d76b0ebfa264a2fee7ce326de537b474db9bb493c6e1c`。
适配器17项针对性测试通过，0次原生进程API尝试；覆盖错误证书、行遗漏、近似反向/非零区间、原等式保留、错误原矩阵初解/回调/终值、根截止与身份、时间帽及失败封闭。初次9项临时目录权限错误已保留；改为工作区fixtures后通过。
独立审查指出预扫描与原consumer重扫间的真实竞态，已在启动前修复为当前记录器实例的实际assess(vector,source)入口检查，并补新发布事件回归。最终17项为修复后结果；早期代码、冻结和测试日志均在revisions/和attempt记录中保留。

## 冻结的执行条件

共享180秒端到端根预算，从科学导入和输入读取前计时，包含源检查、模型构造、两景现场初解、原完整SAFE、MATLAB启动、等价转换、求解与准入。仅一个worker、每景一个请求、一轮反馈、不自动重试。每景native MaxTime最多30秒，是软上限，不是请求壁钟保证；转换成本计入根预算。
保留原探针worker：MaxFeasiblePoints=1、Display=iter、根dual-simplex、IntegerPreprocess/LPPreprocess=none、ConstraintTolerance=1e-9、IntegerTolerance=1e-6。只抑制普通SCENE_SLICE_END取消，与既有B控制相同；总根、资源、热违规、用户取消及20秒宽限/40秒清理协议保持。两景本次现场生成x0，未引用历史优解。

## 实际时间与结果

时间均为2026-11-06 UTC。任务准备开始13:56:23。离线矩阵检查14:02:26.081122–14:02:40.257269，14.172秒；最终17项测试14:08:06.010862–14:08:06.714374，0.703秒。
本轮根启动 `2026-11-06T14:08:55.241980+00:00`，结束含清理 `2026-11-06T14:11:20.918926+00:00`；方法 141.672 秒，清理 4.000 秒，包装总耗时 145.672 秒。MATLAB实际启动14:09:11.258994；完整LAUNCH argv、READY阶段和进程创建身份见runtime目录。

| 场景 | 实际 MaxTime / s | intlinprog 调用壁钟 / s | exitflag | 返回 | 原约束及SAFE |
|---|---:|---:|---:|---|---|
| AB_offset_0ms | 29.484000 | 31.467703 | 2 | 与本次x0逐字节相同 | 原矩阵准入通过；同次原场景SAFE回执命中缓存 |
| AC_offset_0ms | 29.359000 | 29.700200 | 0 | 空向量 | 没有求解器候选；保留现场初解SAFE |

AB记录到rootlp事件（求解器time=27.2207309，松弛目标0.7240384682090559），随后返回8738维点；最大逐元素差0，与本次x0位级相同。原矩阵最大不等式残差约2.13e-14，其余残差为0。上界仍为1.046120846870405671... J，求解器报告有界限时状态，不是最优。原场景完整SAFE在本次初始化阶段已形成，因调度候选相同而合法复用；没有额外宣称对相同点重新执行了热仿真。
AC仅init/done，无记录到rootlp完成事件，输出为MaxTime、无整数向量。done.numfeaspoints=1与最终output.numfeaspoints=0的不一致仍在，不能据此证明初解被采纳、数值不可行或某个内部阶段。没有新做AC独立LP诊断，不推断未记录的内部根因。
两景回调均未发布非空x，因此真实非空live-callback门只在离线故障注入中覆盖；本轮真实新向量验收是AB最终返回通路，不能将其写成两景所有分支均通过。
原场景SAFE上界：AB 1.046120846870405671... J，AC 1.115526056796231757... J；加权聚合 **1.08082345183331871430416362243374659121963251848651500438105 J**，来源 `initial_constructor`。`inner_MILP_improved_initial_upper_bound=false`，`strict_improvement_over_initial_certified=false`。保留SAFE初解不等于两景MILP成功交付。

严格技术门：native_technical_pass=false、transport_contract_complete=false，原因是AC空返回；full_safe_aggregate_contract=true（现场初解），method_within_root=true、physical_cleanup_verified=true。无接口异常、无清理异常、无资源异常。Python入口退出码2明确表示严格验收未通过，MATLAB进程退出码0、graceful_closed，不能混为一谈。
启动前可用约4.76 GiB，运行最低 **3.368889 GiB**，高于2 GiB。3个已记录进程身份均确认退出，附加身份复核无仍运行者；可见范围以本任务进程观测为限。清理未强制关闭。

## 命令和证据索引

在本任务目录执行（全部Python均-B，无-O）：

```powershell
& '${PYTHON_EXE}' -B .\verify_offline.py > .\logs\offline_equivalence.log 2>&1
& '${PYTHON_EXE}' -B .\test_adapter_runner.py
& '${PYTHON_EXE}' -B .\freeze_validation.py
& '${PYTHON_EXE}' -B -u .\native_equivalent_entry.py > .\logs\native_execution.log 2>&1
& '${PYTHON_EXE}' -B .\collect_result.py > .\logs\collection.log 2>&1
```

- `PLAN.json`、`TASK_START.json`、`FROZEN.json`：协议、上游身份、源清单和可执行文件哈希。
- `OFFLINE_EQUIVALENCE.json`、`offline_certificates/`、`ADAPTER_TEST_RESULT.json`、`logs/adapter_tests.log`：离线检查。
- `NATIVE_CLAIM.json`、`NATIVE_END.json`、`NATIVE_EXIT.json`：唯一启动、根时间、退出。
- `runs/native_once/runtime/`：实际完整启动命令、阶段标记、内存逐样本、进程身份与清理。
- `runs/native_once/condition/matlab/request_*.equivalence.json`：每个实际请求的完整逐行证书。
- 同目录 `request_*.mat`、`*.native.mat`、`*.response.json`、`*.python.json`、`*.original_admission_*.json`、`matlab.log`：原生请求、终值、回调及原矩阵门。
- `runs/native_once/condition/result.json`：原格式完整SAFE、候选、来源、缓存命中、时间预算。
- `runs/native_once/driver_audit.json`、`RESULT_AUDIT.json`、`SUMMARY.json`：严格门与只读汇总。

## 结论边界与停止状态

这是单映射、同模型的有界接口验证，不是正式算法性能对照，也没有枚举16映射。AB成功仅复现初解交付；AC等价性已证、交付仍未验证成功，不能推广为全部完整问题已解决。所有结果和失败均保留。没有扩大时限、调整容差、换求解器或从超时后接纳候选；没有改动原基线或历史结果、提交或推送。
本轮到此停止，不自动再跑。下一步如继续，最有信息量的是对AC保留同一模型做预先固定的根LP表示诊断；应另行界定次数和预算，不能把本轮空返回写成不可行，也不能承诺延时后必定成功。
