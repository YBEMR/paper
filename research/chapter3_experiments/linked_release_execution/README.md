# K176一次性执行入口

仅用于用户批准的P0/R3原C→K175条件性联合释放版两次调用，各300秒；每个正常完整SAFE唯一一次≤60秒独立复核，整批1200秒。

**本批已消费并结束，不可重跑或恢复。** 历史声明、单次claim及总claim均保留。结果见`../results/linked_release_execution01/summary.md`。

`registry.py`约束范围/配方/源hash；`freeze.py`绑定通过的纯检查并冻结；`batch.py`串行消费；`worker.py`独立计时调用原入口；`audit.py`核对原始证据；`post_worker.py`只复核原输出；`supervise.py`管理当前受控进程的停止与返回。生产算法不在本包实现。

必要预检由`test_batch.py`、`check_worker.py`、`test_audit.py`、`test_registry.py`完成，49项通过。纯测试采用临时目录、假时钟与假进程，不生成研究SAFE；旧失败记录不覆盖。

各方法独立加载输入、形成fresh S0/S1并使用独立会话与缓存；根时钟在方法相关导入和科学工作之前启动。300秒后不得形成新U；返回监督和清理不是附加研究预算。没有重试、补跑、跨方法初解或恢复其他批次的接口。
