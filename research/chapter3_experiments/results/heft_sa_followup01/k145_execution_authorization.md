# K145执行授权与边界

用户明确授权：按已冻结K144协议执行HEFT、SA101各一次300秒，保持原参数、合法调度域和热安全标准，不补跑、不延长预算，完成后统一复核和分析。

- 执行入口：`F:/Anaconda3/python.exe -B research/chapter3_experiments/run_heuristic_followup.py --run --execution-authorized --out research/chapter3_experiments/results/heft_sa_followup01`
- 顺序：HEFT后SA101；每种方法独立重新加载输入、计时、缓存和安全评价。
- 沿用本目录原declaration及165份源码、最终63项预检，不修改冻结条件或策略。
- 已检查：执行前账本DECLARED、消费0，新全局claim不存在；19项交付核查通过。
- 异常处理：按冻结协议停止尚未启动方法，不撤销claim、不重启；正常截止保留此前完整安全结果及末候选未决。
- 事后只核已有回执、身份、时钟及归档，不能补搜索、修复或预算外安全证据。
- 此批独立报告，不与K142拼成完整四方法同轮，不推断单种子随机稳定性。

本文件记录本轮授权，不替代机器规则、冻结输入或方法账本。实际是否执行及消费次数以随后生成的claim、账本和原始结果为准。
