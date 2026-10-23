# K.183：MATLAB执行环境排查与宿主启动自检

**已找到可用执行方式：同一MATLAB安装、原桥和原偏好目录在宿主环境启动成功，14.531秒进入READY并正常关闭。后续MATLAB批次应采用这条执行路径。** 本轮仅一次技术握手，无研究任务、优化请求或热积分；K.182仍停止，剩余7次未启动。

## 环境差异与验证

| 检查项 | K.182失败调用 | 本轮技术自检 |
|---|---|---|
| 执行上下文 | 崩溃日志位于AppContainer重定向临时目录；当前默认工具进程的令牌检查也为AppContainer | 宿主进程，令牌检查为非AppContainer |
| 临时目录 | `…/Packages/sandbox.{…}/AC/Temp` | 普通用户的`AppData/Local/Temp` |
| MATLAB／桥／偏好目录 | 原R2023b、原桥、工作区偏好目录 | 均保持相同，无重置、替换或全局设置修改 |
| 启动结果 | 69.343秒后`0xC0000005`，没有READY | 14.531秒READY，R2023b，工具箱许可test／checkout通过 |
| 退出 | 原生清理未决 | 退出0，`graceful_closed`，3个已捕获进程身份均确认结束 |
| 优化请求 | 0 | 0 |

原C的历史成功调用也使用同一MATLAB绝对路径、程序hash、桥hash和偏好目录。四次历史启动耗时6.375／6.485／18.609／7.657秒；新失败输出路径全ASCII、长度短于历史成功路径，不支持单凭路径过长解释。历史未保存完整TEMP／进程令牌，不能反推当时的沙箱状态。[历史对比](history_comparison.json)保存具体来源。

本轮使用原`MatlabSession`，只执行READY握手后关闭，未生成请求文件或调用`solve`。提前声明最多1次、启动上限120秒、进程监督150秒；实际技术子进程32.782秒，未重试。原生日志为空，未读取偏好目录中的证书或密钥内容。[计划](plan.json)、[启动回执](host_handshake.json)、[监督回执](supervisor.json)、[原生关闭记录](native_closed.json)及[独立只读核查](independent_review.json)保存；原冻结277源、1依赖和8保护档案保持。

## 结论与后续

证据说明**原安装和桥在宿主环境可用，本次受限执行上下文是需要避开的运行条件**。它没有单独分离AppContainer权限、TEMP重定向、日志组件状态等因素，不能宣称已经找到DDUX内部崩溃的唯一原因，也不证明MILP求解必然成功。无需据本次故障改物理模型、容差或算法。

后续恢复实验时，应让整个公平批次的所有方法处于同一已验证宿主上下文，保持原根预算计费；增加执行上下文核对，避免仅凭Python／系统版本相同就认定环境相同。实际续接仍需单独安排：不重启已终止K.182，不补跑首槽，不自动消费剩余7次。

MathWorks官方支持将偏好写入、TEMP及运行环境列为启动排查项，并说明Windows临时目录受TMP／TEMP影响；本次只借用其排查依据，没有采用未经证实的DDUX开关，也未清空偏好或重装软件。[Windows启动支持文章](https://www.mathworks.com/matlabcentral/answers/97167-why-will-matlab-not-start-up-properly-on-my-windows-based-system)、[临时目录规则](https://www.mathworks.com/matlabcentral/answers/97720-how-do-i-change-the-temporary-directory-that-matlab-uses#answer_107069)；进程令牌检查依据[Microsoft文档](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class)。这些资料不直接证明本次崩溃根因。
