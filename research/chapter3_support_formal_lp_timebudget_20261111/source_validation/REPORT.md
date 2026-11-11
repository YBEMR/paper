# 正式传播源码及独立结构测试整理

已完成；传播算法和 MILP 开关保持原样，新增正式纯结构回归入口。原 `option_support.py`、`milp.py`、`test_option_support.py` 本来就位于正式目录，因此未以归档副本覆盖它们。三者已逐字节对照固定提交 `37c9b12efb29f5970dfab1b8922d12ccbedaae75` 的 archive/frozen 版本；结果见 `start.json`。当前根工作区 HEAD 较旧，故基于固定提交的内容哈希确认身份，不以根 HEAD 冒充本轮源码版本。

## 正式路径与版本

- `research/chapter3_experiments/option_support.py`：不变，SHA256 `fe33351662dcdc7f50136c3601af022bd831ce8a41ae6e92810b46b09f5efbf8`。
- `research/chapter3_experiments/milp.py`：不变，SHA256 `f34809ad6d8e15d4639af8cdcfb62b3ebb4603772e513289280ccdefa783fefb`。
- 旧物理集成测试 `test_option_support.py`：完整保留，不变，SHA256 `59e62b15f8a325ddc69fdac291169cdfeccfd92a111e1a05551fd90461abd557`；本轮没有运行其中的热评价或模型构建。
- 新增 `option_support_test_oracle.py`：从上一轮独立 oracle 提取纯 helper，`instance`、`opt`、`legal_reason`、`fixtures` 四函数 AST 与冻结源完全相同。`enumerate_all` 改为接受可选计时回调，移除旧实验脚本的导入时计时及结果文件写入。
- 新增 `test_option_support_structural.py`：标准 unittest 及显式 `--output` 证据入口，使用正式传播模块而非归档模块。

各正式文件的冻结哈希见 `plan.json`，本轮源快照见 `frozen/`。修改前的既有三文件见 `before/`；历史目录未改动。

## 执行结果

8 项 unittest 全部通过，无失败/错误。266 个有限选项目录逐目录比较传播前后所有完整结构合法调度集合；累计合法集合项数 186→186，Cartesian 完整组合 342→221，512 条删除证据重放通过。186 是各目录累计项数，不是 186 个独立真实研究实例或 SAFE 调度。全部 266 个输入目录和完整候选身份/结构合法性/保留项与上轮冻结证据逐项一致（`verification.json`）。

覆盖依赖等号、分数非整数结束、5ms 起点边界、多轮依赖—共享映射交互、跨场景仅设备共享且频档/起点可不同、空域传递、同场景共享副本、并发资源和 CPU 共享频域，以及支持非空仍资源不可行。补充错误证明、畸形输入和预算中断不修改输入的拒绝检查。

开关检查采用源级 AST 合同及从正式源码抽取的 bool guard 执行：默认 `propagate_support=False`，严格接受 bool，传播调用受开关控制且位于 mode 变量构建之前。**本轮没有构建完整模型，因此这不是 OFF/ON 物理行或完整生命周期的新动态回归。** 不把源级检查说成完整端到端验证。

独立合法性 oracle 不调用生产传播模块的合法性 helper、生产 schedules 校验器或热核；删除证据的重放仍用正式生产 replay 函数，需与独立集合比对分别理解。测试保留原算法和原合法选择语义，未增加资源两两传播。0 LP、0 MILP、0 模型构建、0 电热评价；直接测试进程也未导入 `milp` 或 `thermal`。

## 真实命令、时间及日志

工作目录 `/workspace/paper`。测试前冻结 `plan.json` 并校验全部哈希，以 70 秒外部 watchdog 和 60 秒纯结构枚举检查执行一次：

```sh
python3 -B research/chapter3_experiments/test_option_support_structural.py --output research/chapter3_support_formal_lp_timebudget_20261111/source_validation/execution
```

外层命令执行 UTC 2026-11-11 06:53:54.582432–06:53:55.266655，即北京时间 14:53:54.582432–14:53:55.266655；外层 0.684244 秒，测试及证据归档 0.471183 秒，unittest 报告 0.368 秒。退出码 0，没有超时或重试。核查固定版本时实际使用 `git show 37c9b12efb29f5970dfab1b8922d12ccbedaae75:<冻结路径>`（仓库 `/workspace/paper_publish_autol_lp_20261111`），准确路径在 `start.json`。

- `command_receipt.json`：实际 argv/cwd/起止/退出码/计划哈希。
- `stdout.log`、`stderr.log`：完整运行输出和逐测试日志。
- `execution/results.json`：测试数量、耗时、环境、统计、源码哈希。
- `execution/declared_fixture_inputs.json`、`execution/complete_schedule_sets_and_proofs.json`：完整输入、候选集合及证据。
- `verification.json`：与上一轮目录和完整候选比对。

Python 3.12.14 / Linux；没有安装依赖。小域一致性支持实现正确性，但不是所有输入的经验性普遍证明，也没有新增连续热安全证书。正式算法文件保持原验证版本；本步骤未提交或推送。
