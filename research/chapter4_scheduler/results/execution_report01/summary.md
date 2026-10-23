# K.182：四方法验证首槽MATLAB启动故障，批次停止

**只运行了R1/C首槽，MATLAB在就绪前崩溃；未进入MILP优化，后续7次未启动。本轮没有形成算法质量对照。** 输入、算法源码和热安全门均未改，无补跑或预算扩展。

用户在K181明确列出预算后回复“继续吧”，随后异步明确确认“确认预算，预检通过后执行”。两条均绑定同一批8×300秒、最多8×60秒独立复核、4800秒日历，未解释为第二批或失败后的重启授权。[授权](../execution_preparation01/frozen/authorization.json)与[后续确认](../execution_preparation01/frozen/authorization_confirmation_received.json)保存；原准备声明没有改写。

## 实际发生了什么

| 项目 | 记录 |
|---|---|
| 输入／源码／环境 | R1原H输入身份匹配，277源及8保护入口hash保持，根未重置 |
| C构造阶段 | 5.359秒形成原完整电热回执，原始构造U为1.080823451833 J |
| MATLAB启动 | 用时69.343秒，`ready.json`尚未形成，进程退出码`0xC0000005` |
| 本机日志 | 明确记载Access violation，首帧位于`mwddux_logging.dll` |
| 优化执行 | `solver_request_attempts=0`、`session_total_request_count=0` |
| 结果接纳 | 原raw及构造方案保留；方法状态含INTERFACE_ERROR，清理状态unresolved，审计拒绝post／排名 |
| 后续调用 | R1的HEFT/SINGLE/PAIR与R3四版全部未启动 |

方法自身计时81.015秒，工作进程根至返回81.234秒，方法子进程墙钟82.078秒，批次墙钟82.812秒；这些是不同计时边界，不相加。方法槽已消费1次、预留300秒，post为0；剩余7槽没有消费，也没有把首槽余时或预算退回重试。

[批次终态](../execution_preparation01/frozen/batch_terminal.json)、[首槽审计](../execution_preparation01/frozen/calls/base__R1__C/audit.json)、[原始结果](../execution_preparation01/frozen/calls/base__R1__C/result.json)、[只读事实表](facts.json)均保存。`worker_return.passed=true`只表示原结果成功归档，不等于方法正常、热结果获本批独立复核或清理完成。

## 能解释什么

故障发生于MATLAB启动，早于优化请求。这不是已观测到的MILP数值冲突，也不能据此判断C、HEFT或联合图重构的优劣。故障前构造回执仍保留，但没有完成本批唯一独立post，且方法技术终态异常，不纳入正常对照。

当前日志只能定位到原生启动崩溃，不能确定根因。崩溃文件路径显示本次受限运行环境；这提供环境核查线索，尚不能证明受限环境、偏好目录、运行库或模型中的某一项是原因。已有纯夹具验收验证的是接线／预算／回执处理，不代表实际MATLAB启动已经验证。

原始MATLAB日志含本机授权及会话标识，留在本机并精确加入忽略规则；公开[脱敏日志](matlab_startup_crash_redacted.log)只移除这两项标识，[脱敏记录](log_redaction.json)保存原文件hash。没有改写原生故障元数据或物理结果。

## 下一步

**先隔离MATLAB启动故障，算法规则暂不调整。** 建议下一项仅核查启动环境，必要时另行约定一个不加载研究问题、不调用求解器的最小MATLAB启动自检；当前未执行此自检。修复后再审查剩余7槽如何续接；首槽不能暗中补跑，原终态和证据不覆盖。本轮已经停止，不自动恢复K.168、期限24次或其他实验。
