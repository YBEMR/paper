# K117 读取修复的独立范围验收

结论：**读取修复范围接受；原生预检整体仍失败（73/74，native_precheck_passed=false）。** 原 verification.json、74项断言和唯一claim均保留，不删失败、不改成PASS，不补跑。本审查为线程内部，只读源码／现存档案，未运行测试、模型、热评价、求解或 Git。

| 原始读取分支 | 直接证据 |
|---|---|
| 短锁恢复 | 真实Win32文件共享拒绝1次，2次读取后成功，0.394269秒；随后toy正常求解 |
| 完整损坏JSON | 只读1次、IO失败0；MATLAB:json:ExpectedValueAtEnd，ERROR且未入solver，解析错误未吞进重试 |
| 持续锁 | 107次真实拒读，2.005013秒后chapter3:requestReadTimeout；末原生cannotOpenFile／Permission denied保留，未入solver |
| 锁内cancel／stop | 各10次真实拒读后识别控制，BUDGET_EXHAUSTED_BEFORE_SOLVER，x为空且未入solver |
| 同worker后续正常请求 | 第5请求在坏JSON、持续锁超读窗和cancel之后正常求解；未重启worker |

Python原子发布及桥接未改；关闭.tmp后先持真实锁再rename、对最终文件名确实读失败，不是mock或仅凭耗时推定覆盖。三个源码与快照、声明及claim匹配；K116的29项生产源实际仅worker改变，原配置和关键研究档案保持。6请求共用同一180秒截止、worker PID16192；方法80.828秒（含启动63.641秒及新增5秒退出观察），清理20.344秒另记。仅两次1变量toy实际入优化器，0物理模型／热评价／研究调用；toy的accepted_for_evaluation不等于SAFE或能耗U。MATLAB单元素x=1经原桥接规范成[1.0]，其余原始字段及Python回执匹配。

**唯一失败不能消除。** final_stop_ended_worker_before_cleanup要求stop回执后5秒内OS进程自然退出。请求读取的生产契约要求有限IO重试、坏JSON明确报错、停止／取消／守卫到界不再入solver、沿原时钟计费，没有5秒OS退出保证。原close也明确允许等待20秒后终止自己的进程树，因此5秒条件是预检另加的清理要求，不能据其失败否定已直接观察的读取修复。

但本次不止“5秒阈值过严”：之后原close又等待20秒仍未自然退出，最终taskkill自己的进程树，kill返回0、进程returncode=1。清理依靠强制终止完成，**自然退出／优雅关闭尚未验收**。STOPPED回执证明已识别stop且未入solver，不能单凭它断言函数或整个OS进程自然结束；延迟或阻塞具体原因未定位。没有证据表明本轮读取恢复引入了其他求解／安全缺陷，也不能把强制清理行为称为正常。

分范围接受依据是六类原始回执逐项支持读取／解析／停止与同worker交接；它与5秒进程退出是不同命题。不重定义原74项整体标准，不构成新全PASS gate或研究重跑批准。worker守卫到界分支仅经静态核查，本次6请求未单独触发；不承诺硬实时停止、永久锁恢复或新的物理安全／节能结果。

本次16项归档／范围说明检查通过；原预检仍73/74失败。逐项哈希见independent_review.json，绑定58项现存档案和claim；清单SHA256：`d40866f51edcf6797ecac7de6d3d249ed8fcef832826b4c154e7c8f07962b230`。两份审查自身排除，避免循环哈希。
