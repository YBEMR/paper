# AC 等价矩阵进展交接（2026-11-06）

**已完成：AB/AC等价行检查、30秒双景通路、一次AC独立LP松弛、一次AC120秒MILP。返回点仍是初解，没有优化增益；AC的“最优”状态与正gap矛盾，不能采信。**

| 已完成记录 | 核心结果 | 证据 |
|---|---|---|
| AB/AC各约30秒 | AB返回原初解，AC空返回；双景严格门未通过 | [报告](evidence/abac30/REPORT_ZH.md)、[审计](evidence/abac30/RESULT_AUDIT.json) |
| AC独立LP松弛约29.359秒 | 13,890次迭代，exit=0，限时空返回；不是MILP/SAFE结果 | [报告](evidence/ac_lp/REPORT_ZH.md)、[原生结果](evidence/ac_lp/native/lp_result.json) |
| AC等价MILP120秒 | 116.113秒记录rootlp，117.250秒调用后返回原x0；完整SAFE上界仍1.115526056796232J | [报告](evidence/ac_milp120/REPORT_ZH.md)、[审计](evidence/ac_milp120/AUDIT.json)、[原生响应](evidence/ac_milp120/native/request_000001.response.json) |

AC120原生exitflag=1并称根节点零间隙最优，但同一output.relativegap=16.63925、absolutegap=0.352008，实际两项gap容差均为0。rootlp目标0.7635183800868108与返回初解目标1.115526056796232有明显差距。所有值保留；这不是可信的最优证明，内部原因未定。原始native回调JSON不重复嵌入所有向量，非空向量也应核对对应event文件。

## 适用范围

原β=1.3完整三阶段输入，AB/AC各6次执行；仅一个共享映射A.pre=CPU1、A.main=NPU0、A.post=CPU1。变量、物理模型、原声明候选未删；精确相反不等式对移入Aeq，AB4346对、AC4994对，保留原行数值准入与完整连续SAFE。两景30秒验证现场重新构造初解；120秒验证按明确指令复用同一保存的AC矩阵及x0，并在根预算内重做原模型及SAFE复核。预算/初始化不同，不能将包装耗时直接比较为算法优势。没有全映射搜索或正式HEFT/SA对照。

独立LP默认偏好目录不可写的首次启动失败已保留于[evidence/ac_lp_startup_failed](evidence/ac_lp_startup_failed/)。确认零LP调用、进程退出后设置隔离可写目录补启动；总2次MATLAB启动、实际1次LP调用。120秒MILP为另外一次独立诊断。所有结果/失败如实保留。

后续AB30/AC120的现场双景准备只通过18项离线测试，冻结未完成、MATLAB未启动；用户要求优先发布，故暂停，见[PENDING_FULLPATH](PENDING_FULLPATH.json)。不要把它算作已完成实验，本交接也不授权自动执行。

## 文件与脱敏

[清单](MANIFEST.json)核对发布字节；[来源映射](SOURCE_INDEX.json)分别列原文件SHA256和发布SHA256；[二进制索引](BINARY_INDEX.json)只保留未上传MAT的哈希/大小。JSON科学字段（x/fval/exitflag/output/回调/停止决策）逐项与本机原件相同。移除了私人绝对路径、机器/授权/凭据信息；进程PID以全包稳定别名替换，创建时间和退出状态保留。发布文本统一UTF-8/LF；输入源字节hash与发布字节hash分列，不能混用。动态偏好、原始MAT和MathWorks安装源码未上传。

source/是项目源码审阅快照，路径已占位且以.txt保存，不能直接视为运行包；原实验baseline固定清单与b359126725646727bd990e5cf7215631bb3d4536链条一致。原完整输入来自旧交接，重复保存仅便于核对。原配置SHA256=132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2，原实例SHA256=01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89。

实际命令、起止、预算、内存和清理在各报告/COMMAND/LAUNCH/RESULT中。全部记录在2026-11-06完成；报告已标时间为UTC或北京时间。没有合并main或覆盖历史。
