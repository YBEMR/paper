# K.130：运行故障排查与生命周期修复

**当前启动／读写／清理链路验收通过，可以回到新版质量验证；历史Errno22的直接根因尚未证实。** 本轮未生成研究候选或调用优化器，旧K129失败不补写结果。

## 1．已定位的实际问题

原K129档案mtime显示：Python失败在01:56:38.553 UTC，MATLAB缓存警告在01:56:45.527，READY在01:56:55.516。后来有READY不等于Python当时成功握手；缓存警告晚于失败。报错路径103字符、无非法名，磁盘约124 GB可用；无法据此把原异常归为永久路径／空间故障。mtime是在本机原文件上捕获，见runtime_io_probe03/environment_audit.json。
实际无求解检查复现两类清理问题：受限执行上下文中taskkill被拒，真实子进程残留；在获批host上下文中taskkill成功后父退出1，原判断仍记失败。此外，父正常退出0时一个子进程稍后才退出，立即核验也会误报未决。这些清理问题已定位；不能据此断言它们与原Errno22同根。

## 2．最小修复

READY、close开始及强制前保存本次launcher与子进程的PID／创建时间；最终只核这些所属身份。共享原40秒清理上限，最后最多等待10秒确认已有子进程退出。正常退出、强制且已确认退出、未决分列，保留原退出码／taskkill回执／耗时。权限不足、PID身份不符、子仍活或证据缺失均不放行，不向复用PID发信号。
N1生命周期、固定设备配对入口及技术探针统一使用cleanup_is_complete。强制清理完成仍保存session_cleanup；原启动／读写／求解错误、归档失败及已成SAFE不被覆盖。没有放宽热安全或接纳超预算候选。

## 3．真实检查与失败记录

| 记录 | READY数 | 墙钟/s | 原状态与含义 |
|---|---:|---:|---|
| runtime_io_probe01 | 1 | 33.063 | 通过：单次启动／I/O／正常退出 |
| runtime_io_probe02 | 1 | 36.219 | 失败：受限上下文清理被拒，停止第二次启动 |
| runtime_io_probe03 | 1 | 32.234 | 失败保留：host强杀成功，但旧规则因exit1停止 |
| runtime_io_probe04 | 1 | 20.485 | 失败保留：父exit0、子稍后退，即时确认过早 |
| runtime_io_probe05 | 2 | 40.140 | 通过：修复后同Python进程连续两次完整生命周期 |

共6次技术READY，五个诊断程序累计162.141秒；不含编码分析。每组预先声明限制，出错即停，没有补跑原研究。最终129项回归通过，135项源与快照匹配；包含15项bridge fake边界及10项方法归档／清理用例，另核旧默认／N1模型数组等价。

所有技术组均做200次不存在文件读取、200轮JSON原子发布／回读，每个READY后另100次发布；没有复现Errno22。用户工具箱缓存各组前后SHA相同，未删除或重建缓存，未改全局配置。MATLAB关闭有时仍需强制收尾，原因未深挖，次数和成本原样保留。

最终两个worker的清理：
- worker0：forced_closed，原退出码1，3个已观察身份均退出，清理20.500秒。
- worker1：graceful_closed，原退出码0，3个已观察身份均退出，清理4.141秒。

## 4．后续口径

MATLAB原生调用使用已验收、能管理本次进程树的执行上下文；普通文件分析仍可在原工作区执行。后续所有比较方法统一上下文、统一预算，启动仍计入方法时间，清理继续单列。原02／03／04及K129失败保持，不改绿、不补U。
本轮不再加环境组合、温度扫描或求解调用。下一项是按原模型冻结新版质量验证；若再发生Errno22或清理未决，保存原始异常和所属进程证据，停止受影响调用，不用重试制造成功。

代码、检查与来源：run_runtime_io_probe.py；runtime_io_precheck02/checks.json；本目录checks.json／facts.json；只读核查MathWorks R2023b的[-batch入口](https://www.mathworks.com/help/releases/R2023b/matlab/ref/matlabwindows.html)及[路径缓存说明](https://www.mathworks.com/help/releases/R2023b/matlab/matlab_env/toolbox-path-caching-in-the-matlab-program.html)。未因缓存警告修改用户缓存。
