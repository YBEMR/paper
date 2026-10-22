# K163期限组终态只读核查

本目录工具不属于冻结的240份科学/执行源，不修改任何执行工件。默认入口先要求`deadline_execution01/process_terminal.json`已经存在；没有监督终态时立即拒绝，不读取运行中的大结果或账本。

`audit_terminal.py`继承K161的终态存档核对，原始出处、SHA和适配内容见`DERIVATION.json`。仅修改新批身份/准备绑定、240源、原H/50°C及beta1.0输入检查，并增加当前期限审计门、正常无U/无种子结果的显式保存。正常无U不能写0能耗；完成槽的post必须为NOT_APPLICABLE且不存在额外post文件。无种子不作模型无解/最优证明。已有完整U仍需原完整SAFE回执、预算内形成、逐请求精确合法性和一次既定post；工具不重新做任何热积分。

核查可处理技术中断的最后一个部分槽，保留已消费次数与原证据，不把未完成当可排名能量。独立上下界/求解器报告范围沿原记录解释；不新增独立最优或无解证明。

预检：

- `test_no_U_records.py`九项手写记录夹具通过，核无U/零值/缺失标记/额外post/回填/停止部分槽，以及缺监督终态即拒绝；不读取当前运行结果。
- `test_stopped_fixtures.py`对旧P1的0/1消费合成停止视图核对26/27项通过，原P1保持，11类科学/原生/模型/热/子进程禁止门为0。只复制旧输入/源码/元数据，没有读取旧40份大方法结果，不计算新方案或热轨迹。

上述是工具预检，不是期限组真实终态核查。期限组停止后执行：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/deadline_audit_tools01/audit_terminal.py --out deadline_terminal_review01.json
```

输出以独占创建保存，每次用新名字，不覆盖已存报告。`--fixture-p1`仅用于已有旧档案验证，不计作本批真实结果或新科研调用。终态核查仍是当前执行端内部审查，非外部ChatGPT批准或重新复现MATLAB求解。
