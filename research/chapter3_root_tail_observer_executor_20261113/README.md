# D279：有限根 LP 后观测执行器

**已具备申请一次独立科研调用授权的工程条件；当前未批准、未执行。** 56 项纯控制测试通过，历史 221 份来源及 19 份执行器文件哈希未变。本轮新 MATLAB / MILP / LP / 完整 R1 构模 / 完整评价均为 0。

保存 `C_noheur` 原矩阵、互补门控矩阵和原初解，仅增加 `Display=iter`、公开 Profiler 与自有进程资源采样。固定 600 秒方法窗、550 秒响应及完整 Profiler 读取截止，原动态原生配额，最多一次调用、不补跑。修复累计停止范围丢失，后续正常组不能解除此前阻断。

R2023b 接口经版本文档及本机源码静态核查、模拟 MAT/JSON 接线；**未进行 MATLAB 语法检查器或运行时实测**。不能据此保证受保护求解内核可见、历史不截断或预算足够。Profiler `info` 会停止记录；迭代日志接收时间不等于内部事件时间。

O0 验完整性；O1 验新增根后观测；O2 需独立只读语义复核，区分具体机制与其他解释。自动结果保持 O2 未建立；有完整时间线仅表示可复核，不等于获准干预。若仍黑箱，停止参数扫描。优化终点仍为不同原生调度、合法、完整双场景 SAFE、严格能耗下降。

- [完整报告、成本规则、O0/O1/O2 与停止条件](REPORT.txt)
- [冻结计划](executor/plan.json)、[计划身份](executor/plan.identity.json)、[未批准模板](executor/approval.template.json)
- [入口](executor/run_observation.py)、[保存矩阵适配器](executor/runtime.py)、[观测解析及采样](executor/observation.py)、[累计停止范围](executor/scope.py)
- [测试结果](control_test_result.json)、[测试日志](control_tests.log)、[静态核查](verification.json)、[R2023b 兼容性及来源](compatibility.json)、[原生脚本差异](native_observer.diff)
- [全部交付校验和](SHA256SUMS)

## 复核与独立申请

计划绑定本工作区的已有科学文件与保存 C_noheur 材料。这是保存矩阵诊断，不能改称重新构模的 A/B/C 性能实验。可将 `executor/` 按原布局放到工作区 `work/root_tail_observer_v1/`；不得改写路径/文件后仍沿用此身份。`freeze_root_tail_observer.py` 用于说明本次冻结来源，非运行前重新生成批准计划的步骤。

仅纯控制测试可直接复核：

```text
F:/Anaconda3/python.exe -B work/root_tail_observer_v1/test_control.py <新的测试回执路径>
```

测试只使用合成回执、假时钟、假进程、微型矩阵和假科学接口。真正入口要求新的明确用户批准、匹配计划 SHA、独立一次性账本和父子进程身份。此提交及 `approved=false` 模板均不构成执行授权。没有批准文件，没有执行账本，不复用任何历史授权。

计划 SHA-256：`fa49d83b3252108de870e3930739ceb3a27cfc56b65d03ec4decf7cb5aa8f0bc`。

官方出处：[R2023b profile](https://www.mathworks.com/help/releases/R2023b/matlab/ref/profile.html)、[intlinprog](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html)、[回调语义](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog-output-functions-and-plot-functions.html)。不分发 MathWorks 专有源码；受保护实现只记录文件身份。
