# AC 原生终止状态矛盾：直接复现与相对gap单因素诊断

**两次都返回同一初解，无优化改善；均出现“exitflag=1/最优消息”与明显正gap并存。将RelativeGapTolerance从0改为1e-8后矛盾仍在。不能认定最优，也不能将两次结果推广为通用求解器bug。**

参考提交：[301407b6a7c39b952550ae984e635edd89f0f6e1](https://github.com/YBEMR/paper/commit/301407b6a7c39b952550ae984e635edd89f0f6e1)。同一优化轮AC请求2，14014变量、80272不等式、4994等式；原完整三阶段实例与固定共享映射不变。请求MAT SHA256 `bde54760351d94569dbc7524dd7fc1e30eb1efe5fa97d9e9a59938fe7ec44af7`，与该提交清单逐字节核对，九组数学数组和x0一致。

| 诊断 | RelativeGapTolerance | 原生调用/s | rootlp time/s | rootlp后到done/s | exitflag | 绝对gap / 相对gap(%) |
|---|---:|---:|---:|---:|---:|---|
| 直接intlinprog | 0 | 109.389181 | 107.3433334 | 0.4857687 | 1 | 0.352008 / 16.63925 |
| 单因素 | 1e-8 | 137.0018641 | 135.8345681 | 0.4947015 | 1 | 0.352008 / 16.63925 |

两次MaxTime=300秒、MaxFeasiblePoints=Inf，绝对gap容差0、双单纯形、原预处理/约束/整数容差均一致；单因素实际选项差异仅RelativeGapTolerance，监督脚本及请求MAT字节相同，见[差异补丁](evidence/relative_gap_1e8/single_factor.patch.txt)。原生调用未耗尽300秒。所有观察回调stop=false，原始MAT output与JSON的gap字段一致；并非只查看格式化控制台消息。原始MAT仅留本机，公开哈希索引在[BINARY_INDEX](BINARY_INDEX.json)。

| 诊断 | 北京时间开始–结束(2026-11-06) | 含启动清理/s | 最低可用内存/GiB | 返回 |
|---|---|---:|---:|---|
| 直接 | 23:26:59–23:29:35 | 156.485 | 3.074677 | 原x0，目标1.115526056796232J |
| 单因素 | 23:36:35–23:39:25 | 170.078 | 2.791431 | 同一原x0，相同目标 |

Python总保护420秒、资源停止门槛2GiB，沿用20秒宽限/40秒清理；每次只启动一次、调用一次，未自动重试。两次MATLAB都正常退出，分别3个已记录进程身份均确认退出。该记录仅说明已捕获的本任务进程身份，不是主机全局进程证明。

## 结论和边界

直接调用仍复现矛盾，说明文件桥接、事件发布、外层取消不是本例现象的必要条件。正相对容差单因素仍复现，说明不能仅归因于RelativeGapTolerance恰为0。AbsoluteGapTolerance仍为0，其他数值/内部输出更新因素未逐一辨识；没有通过任意调参“修复”或指认内部代码分支。

返回14014维向量均与原x0逐字节相同，没有优化增益。本轮没有新的物理SAFE认证，不把已保存初解的既有SAFE当成优化成果。rootlp目标仍0.7635183800868108J，返回目标1.115526056796232J；原相对gap字段是百分数，与用于停止判断的小数容差不能混用。即使以后出现一致的状态或显示为零gap，也不能由显示舍入获得独立最优证明。

## 证据与命令

- [直接复现报告](evidence/direct/REPORT_ZH.md)、[审计](evidence/direct/AUDIT.json)、[完整回调及输出](evidence/direct/native/native_result.json)、[控制台](evidence/direct/native/matlab.log.txt)
- [单因素报告](evidence/relative_gap_1e8/REPORT_ZH.md)、[审计](evidence/relative_gap_1e8/AUDIT.json)、[完整回调及输出](evidence/relative_gap_1e8/native/native_result.json)、[控制台](evidence/relative_gap_1e8/native/matlab.log.txt)
- [发布清单](MANIFEST.json)、[来源及原/发布哈希](SOURCE_INDEX.json)

两次在各自新任务目录中实际执行相同命令：

```powershell
& '${PYTHON_EXE}' -B -u .\run_once.py > .\execution.log 2>&1
```

完整MATLAB argv、时间和进程身份见各LAUNCH/CLAIM/RESULT/closed记录。实际MATLAB命令形如 `matlab.exe -wait -batch "addpath(...); ac_native_repro"`。source/保留两份项目MATLAB脚本和监督脚本快照，以及监督模块依赖。MATLAB脚本实际调用x0第9参数、options第10参数。输入MAT按原始hash保留本机，不在Git上传；此公开包提供审计与实际命令，不宣称包含全部二进制输入的一键重放环境。需在有原输入MAT、R2023b及Optimization Toolbox授权、SciPy/psutil和项目监督依赖的本机恢复占位路径后复用命令；不要自动复跑。

## 脱敏与格式

移除私人绝对路径、账号/机器/授权/凭据标识，进程PID替换为全包稳定别名；创建时间、退出状态、原生状态及所有科学数值保持。日志中嵌入的JSON也使用相同别名映射。非有限选项值如Inf在JSON可显示null，原记录另有MaxFeasiblePoints_is_Inf=true，原生MAT保留真实选项。日志转为UTF-8/LF，发布哈希与原始文件hash分列，不能混用。动态偏好目录、许可证、凭据、原始MAT、MathWorks安装源码未上传；source/中的.m为项目诊断脚本，.py.txt是脱敏审阅快照。没有更改正式基线、历史结果或合并主分支。
