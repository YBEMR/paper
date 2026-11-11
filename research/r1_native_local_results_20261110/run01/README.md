# R1 本机原生 OFF/ON 单次配对原始记录

此目录导入 2026-11-10 已完成的原 R1 配对包，供 Cloud Work 只读复核。此次提交只发布既有工件，没有重新构模、热评价或求解，没有修改算法、参数、历史结果或 main 分支。

- 文件：R1_native_pair_20261110_run01_results.zip
- 字节数：13,690,438
- SHA-256：b0aab1f9d62df45634400a45b526fc5a8652eaa9d4ef594270df20f7998a79f1
- 原冻结输入包 SHA-256：8e799aa5b50de04dd0683af9864859e30051133f6d7aa9661e5550345e788f73
- 本机执行计划 SHA-256：0830d2d6c546e99f2a7a93de84c86f477a6cbc37f5b44b3e8eb5d28774b1c1bb
- 控制调用 UTC：2026-11-10 12:07:03.602530 至 12:17:53.707488；退出码 0；无补跑。

## 内容与读取顺序

ZIP 保留原始字节，包含 local_records/ 下的预检、冻结计划、命令日志、两侧模型矩阵、MATLAB 事件、完整 SAFE 收据、清理凭证、verified_metrics.json 和 execution_file_manifest.json，以及 input_bundle/ 下的原冻结源码/输入包。先核验 ZIP SHA-256，再查看 local_records/verified_metrics.json、local_records/r1_pair_run01/pair_summary.json 和两侧 method/result.json。execution_file_manifest.json 可验证其所列工件；原输入 ZIP 有独立逐文件清单。

只读解压到新的目录。不要把历史向量、矩阵、收据或已消费的执行 claim 当作新调用的免费输入；此包不是新求解授权或可恢复求解器状态。不要执行包内 run 入口来读取结果。

## 结果和证据边界

- OFF 和 ON 各使用原 300 秒方法总预算；分别现场生成同一物理初解。向量维数为 29,599 和 21,411，两侧不能互换向量。
- 入口状态为 VALID_PAIR，仅表示初解身份守卫、原生进入和清理证据齐全，不表示优化成功或最优。
- 两侧方法计时均约 300.016 秒；清理另计约 20.5 秒，非额外搜索预算。
- OFF 无预算内 solver SAFE、界或 gap；其晚到 response 只作诊断。
- ON 在方法 291.469 秒完成 solver 候选的独立完整 SAFE 验收，但该物理候选与现场初解相同，上界均约 1.6324648165573186 J，没有能量改善。
- ON 预算内 callback 报告下界 0.7438443586267873、relativegap 33.75621403717943%，为 R2023b 的 100*(U-L)/(abs(U)+1)，仅是求解器报告。
- ON 最终 response 未形成，最终 exitflag、完整原生调用耗时和内部 x0 接纳仍未独立观测。
- 固定 OFF→ON 单对，可能受缓存和机器负载影响，不能给出统计加速结论。
- 本机 24 项 mock 检查有 23 项通过，1 项因 Windows 无创建 symlink 的权限而未能建立人工夹具；未修改权限或测试，不冒充 24 项全过。

本目录是此次明确发布的单一 ZIP 例外，不扩大仓库对本机环境、许可证、凭据或其他原始二进制的跟踪范围。
