# AC 同数组直接 intlinprog 复现

**同一提前停止及正gap矛盾在直接原生调用中复现。一次复现不等于通用缺陷或最优证明。**

## 身份与执行

对象为301407b6a7c39b952550ae984e635edd89f0f6e1优化轮AC请求2。原MAT SHA256 `bde54760351d94569dbc7524dd7fc1e30eb1efe5fa97d9e9a59938fe7ec44af7`，已与已发表清单匹配；原生输出MAT也按清单校验。独立副本逐字节一致。九组数学数组与既已验证的AC等价矩阵/原初解完全相同，具体见IDENTITY.json。没有构造新实例、改目标、变量、候选域或数学模型。

在隔离脚本中直接调用intlinprog，x0第9参数，options第10参数。MaxTime=300秒、MaxFeasiblePoints保持默认Inf，双单纯形、两项预处理none、原约束/整数容差及零gap容差不变。全部实际数值选项与已发表选项差异：{}。有意移除文件桥接/发布/外层consumer；改用只记录内存事件的观察回调，并保留安全stop文件及400秒MATLAB保护，Python总保护420秒和原20/40清理。观察回调实际stop全false=True。该回调差异是本次隔离因素，不隐瞒。

根开始2026-11-06T23:26:59.149321+08:00，MATLAB启动2026-11-06T23:26:59.789941+08:00，结束含清理2026-11-06T23:29:35.634496+08:00。总耗时156.485秒，原生调用109.389181秒；rootlp事件求解器time=107.3433334秒。最低可用内存3.074677GiB，阈值2GiB。只有一次MATLAB启动/一次调用，未重试或推送。

## 原始结果与限制

exitflag=1；fval=1.115526056796232；absolutegap=0.352008；relativegap=16.63925；numnodes=0；numfeaspoints=1。消息：找到最优解。

Intlinprog 在根节点处停止，因为目标值在最佳值的间隙容差范围内，options.RelativeGapTolerance = 0。intcon 变量是容差范围内的整数，options.IntegerTolerance = 1e-06。。

最终返回14014维，位级等于同一x0=True。原MAT output的gap/计数与JSON对应值一致=True；原始MAT未被JSON重编码替代。gap与最优状态冲突=True，不采信最优声明。本轮没有新热仿真或物理SAFE认证，若返回原初解，只复现交付而无优化增益。

一致性判断只覆盖这一个AC矩阵、初解、R2023b版本和选项。若冲突在直接调用仍存在，则文件桥接/事件发布/外层取消不是产生该现象的必要条件；不能据此指认受保护求解器内部哪条指令有错。没有修改容差、换求解器或额外延长预算来掩盖状态。

## 命令与证据

工作目录为本报告目录：

```powershell
& '${PYTHON_EXE}' -B -u .\run_once.py > .\execution.log 2>&1
```

完整argv在LAUNCH.json，形式为matlab.exe -wait -batch addpath(...);ac_native_repro。实际调用在ac_native_repro.m。控制台native/matlab.log、原始返回native/native_result.mat、结构化native/native_result.json（含全部回调向量）、startup.json（含版本/which/全部选项）、call_started.json、memory.jsonl、native/closed.json、RESULT.json/AUDIT.json均保留。清理状态graceful_closed，退出身份核验=True，可见MATLAB余留=[]。
