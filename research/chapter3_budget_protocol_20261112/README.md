# 完整 R1：预算入口与科学验收协议

基于 `143629e86cfa5a3951ab23da218ca9c8f260a277`，复核 `7b723b1` 与 `63ad11f`。本轮只读历史证据、静态审查及纯控制测试；没有新增 MATLAB 会话、MILP/LP 调用、完整热评价或大规模构模。

- [研究报告](REPORT.txt)：上次 ON 尚未进入求解；启动根因未知；固定／动态预算比较与唯一下一步建议。
- [正式 A/B/C 协议候选](ABC_PROTOCOL.txt)：完整 12 次 Stage、66 模式、独立构模初始化、统一 600 秒动态预算、分层验收和错误作用范围。正式生命周期尚未接线，不具备立即执行条件。
- [历史复核](history_review.json)、[来源绑定](history_bindings.json)、[静态代码摘录](static_source_excerpts.txt)：旧记录与模型不改，读取原始时间账本及启动流程。
- [预算情景](budget_scenarios.json)：固定240秒与共同动态函数；均为算术情景，不是性能数据。
- [下一次单独 ON 候选](candidate_on/README.md)：原生240秒、方法总窗420秒、响应截止370秒、完整评价截止420秒，最多一次请求，无重试。独立计划与批准模板，不复用已消费授权。
- [冻结回执](candidate_on/freeze_receipt.json)、[控制测试](candidate_on/checks/control_tests.json)、[模拟回执](candidate_on/checks/simulated_receipts.json)：不证明 MILP 求解收益。

**唯一建议申请的新科研动作是一次保存 ON 的 420／240 秒诊断。当前未批准、未运行。** 即使将来通过，也不能把它与历史 OFF 拼成剪枝加速对照；正式 A/B/C 必须重新付出三组全部准备成本并另行冻结批准。

`review_and_freeze.py` 仅处理 JSON／文本／文件 SHA 和纯测试；禁止启动子进程、导入原科学模块，不运行旧数组预检。文件 SHA 依赖原始字节；勿自动转换行尾。`package_delivery.py` 只归档本轮成果。
