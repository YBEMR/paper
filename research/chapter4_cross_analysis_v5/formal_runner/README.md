# 独立 C/D 运行器（执行准备版，尚未通过原环境 smoke）

本包包含固定的 24 单元清单、第四章 v1 构造器与 P1 资产、八份初解身份、调用原第三章运行器的外层脚本。**当前仅在容器内通过语法、包哈希、清单、四例 Q4 生成哈希检查；未安装原 OR-Tools 运行时，未验证原 E2-a 后处理和原环境完整执行。** 不能把这份代码视为正式实验完成回执。

在原第三章实验机器、原 Python/依赖环境、保留正式源码和归档的仓库工作树中，使用以下命令。替换 `<repo>` 为本地仓库真实路径，`<output>` 为仓库与本包之外的新目录。默认原 OR-Tools 路径沿用 G2 assets.py；若使用其他已冻结位置，先设置 `G1_ORTOOLS` 环境变量。需要原 200 份运行时文件逐一哈希匹配。

1. `python -B run_cross.py plan` 仅验证包锁及打印24单元清单，不启动实验。
2. `python -B run_cross.py check --repo "<repo>"` 核对第三章原执行锁、全部锁定源码/输入、正式验收与端点文件、原始 A/B 初解、运行时及软件版本。若 versions_match=false 不启动后续同环境比较，先解决环境问题。环境版本相等并不能证明硬件完全相同，执行人仍需确认实际机器和计算环境。
3. `python -B run_cross.py smoke --repo "<repo>" --out "<output>/smoke" --confirm-original-environment` 实际执行 D1 的 C/D 原配置和后处理各一轮，独立输出 smoke_gate.json。两臂必须均通过 SAFE、原初始化哈希、计时和阶段门控。烟雾测试预算各90秒，池预算180秒；只作接口核验，不纳入正式端点。
4. **只有 smoke_gate.json 返回 PASS，且正式执行者明确允许启动长批次后**，才执行 `python -B run_cross.py execute --repo "<repo>" --out "<output>/formal" --smoke-gate "<output>/smoke/smoke_gate.json" --confirm-original-environment`。此命令前台串行执行 24 个900秒登记单元，池独立重新生成并计时、每臂扣除对应共享构造成本、采用原 formal_batch.run_process/原 formal_worker/trial。相邻 C/D 同物理核，按配对轮换核心，不覆盖旧实验，不调用第三章165单元主函数。原运行日志、证书、回执均按原格式保存。6方法小时为登记预算，不是实际耗时预测。

若失败，保留完整日志和回执，不自动重新启动、不覆盖原目录。先审查异常及环境；任何补跑应另行冻结规则。原第三章 A/B 可用于质量参照；正式交互效应需结合实际环境、可比优化时间和机制记录。E 为确定性 v1 算法，正式效率比较仍需在同环境进行。此执行器只处理新增 C/D，未执行完整 A–E 分析。正式前需要按任务书补齐记录审计。
