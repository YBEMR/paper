# R1 本机原生日志复核入口

当前完整结论见 [GitHub 原始包核验后的报告](github_verified_run01/REPORT.md)，对应 [实际命令](github_verified_run01/COMMANDS.md)、[规模与耗时表](github_verified_run01/comparison.csv)、[回调时间线](github_verified_run01/callback_timeline.csv) 和 [核验结果](github_verified_run01/verification_checks.json)。

根目录旧 REPORT.md、contract/、history/ 及 native_url_access_check/ 保留取得原始包之前的只读核查记录；其中“尚未取得 ZIP”等文字描述当时状态。当前报告已从固定提交读取并核验原始工件。

原始结果 ZIP 已发布于提交 `2fc52c63814d06b039e24a3bde887a2b411be298` 的 `research/r1_native_local_results_20261110/run01/`，SHA-256 为 `b0aab1f9d62df45634400a45b526fc5a8652eaa9d4ef594270df20f7998a79f1`。本次报告提交不重复上传下载副本和 raw/ 解压树，也不上传其他尚未提交的研究代码。

本目录的 manifest、protected_review_files 和完成记录保留当时本地审计范围，包含未重复上传的原始文件索引。需要逐字节复核时，从上述固定提交获取 ZIP，校验后在独立临时目录安全解压。核验脚本使用拒绝覆盖模式，复现应将两个脚本复制到新的空目录，依次运行 fetch_and_verify.py 与 analyze_records.py；不执行结果包内求解入口。空目录中的历史报告保护项数量与原工作区不同，但原始包、输入和执行工件的核验口径相同。

本次只提交已完成的读取、核验和报告。建议中的纯 LP 诊断尚未执行。
