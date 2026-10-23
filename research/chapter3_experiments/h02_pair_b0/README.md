# H02 B0：正式后端接线封版

**状态：接线、静态检查及mock回归完成；阶段B研究调用未授权、未执行。**

独立分支`codex/h02-b0`，从阶段A交付`6f622b3`继续。原`main`和`codex/h02-stage-a`分支均未修改或合并；历史A证据不改写。

首先阅读[evidence/B0_技术封版报告.md](evidence/B0_技术封版报告.md)，再看[未来四槽预算](evidence/four_slot_budget.json)、[回归结果](evidence/regression_tests.json)和[零研究调用账本](evidence/run_ledger.json)。

```powershell
python -B research/chapter3_experiments/h02_pair_b0/run_precheck.py
```

该命令只跑静态和mock。228项检查包含旧A回归、真实worker程序的mock／拒绝探针，以及原`execute_heuristic`生命周期接入mock搜索、合法性、热评价和下界的测试。禁止用它启动真实HEFT或真实热核。

`controller.py`的正式入口由`execution_gate.json`与`policy.json`双重关闭。没有唯一授权ID、批准引用、固定输出目录／消费账本就失败；worker还核对并一次消费相同启动claim。科学范围hash不可随授权开关更新而改变。

`runtime_freeze.json`固定运行源码和策略文件；任何源码／策略漂移均拒绝。当前授权开关的false是刻意冻结值，不是待自动修复的错误。未来只有用户批准阶段B并完成回审后，才可记录授权元数据、重新绑定仅授权字段的hash；不得改Python源、物理输入、槽位或预算。

进程边界是**受信固定Python代码＋独立进程＋文件访问白名单**，不是OS沙箱或抵御恶意本地代码的安全证明。正式HEFT／真H链尚未运行，不能把预检成功当作真实执行、热SAFE、节能或最优证明。
