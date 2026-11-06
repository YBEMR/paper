# AC 等价矩阵独立 LP 松弛短诊断

本轮不是 MILP、SAFE 或全局最优实验。原 AC 请求矩阵、目标、连续变量界及等式保持；仅在 linprog 调用中省略整数限制，不传入 x0。

- 原矩阵 SHA256：`4e85acafcf8a3c2d260e281baf45bae273194d55b1d4b2e13113a14956efe161`；调用前后哈希一致。
- MATLAB 第二次启动：2026-11-06T22:25:21.457647+08:00；结束含清理：2026-11-06T22:26:28.493085+08:00。
- 包装耗时：67.734 秒；原生 MaxTime=29.358999999997 秒；总保护120秒。
- LP exitflag：0；迭代：13890；调用耗时：30.4899073 秒；返回向量长度：0；目标：[]。
- 原生消息：求解器过早停止。

Linprog 已停止，因为它超出了时间限制，options.MaxTime = 29.359。。
- 最低可用内存：3.305794 GiB；阈值2 GiB。
- 清理：graceful_closed；MATLAB返回码0；3个已记录进程身份均退出=True。

## 启动失败与更正

第一次 MATLAB 于北京时间22:24:06.543启动、22:24:11.217结束，默认偏好目录在沙箱中不可写，退出码1。LP调用标记和结果均不存在。完整失败保存在相邻 `ac_lp_20261106T142239Z`，未改写。确认3个身份均退出后，在新目录设置可写 MATLAB_PREFDIR，保留同一矩阵、LP代码、选项和时限，再补一次启动。总计2次MATLAB启动，实际LP调用1次，不隐瞒启动失败。

## 命令与证据

工作目录为本报告目录，实际科学命令：

```powershell
& '${PYTHON_EXE}' -B -u .\run_once.py > .\execution.log 2>&1
```

MATLAB完整argv见LAUNCH.json：`matlab.exe -wait -batch "addpath(...); ac_lp_probe"`。完整脚本及固定 linprog 选项在ac_lp_probe.m，采用R2023b双单纯形、Preprocess=none、ConstraintTolerance=1e-9、OptimalityTolerance=1e-7，MaxIterations按既有公式计算。未改变MILP的任何选项。

原生日志/结果在native/matlab.log、native/lp_result.json及native/lp_result.mat；逐样本资源在memory.jsonl，进程退出与清理在native/closed.json，完整汇总在RESULT.json、AUDIT.json。文件时间仅为写入边界，不冒充内部精确调用起止。

独立linprog松弛与intlinprog内部根LP并非同一个已观测调用，结果只能支持或削弱连续LP成本假设，不能证明MATLAB内部初解登记路径。本轮无新热评价、无MILP候选认证，无进一步重试、推送或历史覆盖。
