# K154：P0基准批入口与预检

状态：准备，不是执行授权。本轮0研究调用，不构造原规模MILP、不启动MATLAB、不计算新热轨迹。

- 范围仅base__R1—R5，每题整体MILP、预消元联动、HEFT各1槽，SA101—105各1槽，共40槽。沿K153四方法块轮转，SA种子顺序固定。
- 提案每槽独立300秒，方法总上限12000秒，日历预留19200秒。预留不是搜索延期；实际预算尚待用户确认。R1是拟预声明的新批复现，不并入K152先导，不补跑旧调用。
- 保持178份既有源码／输入；共享A部署CPU1／NPU0／CPU1、4开2闭及仅第二遍预消元不变。整体MILP不受这一局部邻域限制；HEFT／SA沿各自现有部署选择能力。
- 多问题接入只修改输入编号参数与回执中问题编号核对，未更改约束、时限、初温、温限、功耗、热误差或候选生成策略。派生函数逐项绑定原文及仅有的替换，见audit_lineage.json。
- 每次未来调用重新加载／展开输入并独立计时、计算自身L0；不得把准备阶段快照作为免费构模、候选、热缓存或安全见证。仅公用导入可事先完成，导入耗时另列；MATLAB启动仍在方法预算内。
- 保留K152截止核查：预算内完整U可保留；最后请求若因根时限未完成且能核对取消／隔离，可记正常截止末请求未决。技术故障、身份漂移、数值异常或隔离失败阻断后续，不能改记无解。预算后新方案不得接纳。
- 本轮测试40槽顺序／单次消费仅在TEST_ONLY内存账本；无真实claims。生产派发函数供下一次冻结的总控复用。CLI的run明确拒绝，授权样例approved=false；真实启动总控、一次性研究claim与总墙钟限额须在具体预算确认后另行冻结预检，不能只把false改成true。
- 回执适配属于存档结构核对，不是新的物理复核。正式批后仍需逐方案用同一连续热评价器事后复核；事后不得补搜索、更新预算内U。
- 本轮不处理CPU-only／CPU+GPU的联动适配，不扩场景／请求数，不新增反馈扫描或正式消融。

可复跑入口（从仓库根目录）：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/p0_batch/run_p0.py precheck --out research/chapter3_experiments/results/p0_precheck_新编号
F:/Anaconda3/python.exe -B research/chapter3_experiments/p0_batch/run_p0.py prepare --checks 上一步目录/checks.json --out research/chapter3_experiments/results/p0_准备_新编号
F:/Anaconda3/python.exe -B research/chapter3_experiments/p0_batch/run_p0.py inspect --out 上一步目录
```

每次预检／准备使用新目录，不覆盖旧失败。下一步只需审阅40槽预算与实际执行总控，不再扩算法。
