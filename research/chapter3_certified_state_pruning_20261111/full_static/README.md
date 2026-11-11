# 完整R1静态配对执行器

本目录先准备代码，不自动冻结或执行。只有主代理写入 `acceptance.json`，明确 `enabled=true`、`evidence_passed=true`，绑定全部已验收源文件和数值/小域验收凭证的SHA-256后，才允许freeze。目录存在不代表验收通过。

验收合同：`source_sha256` 是仓库相对路径到SHA-256的字典（至少milp.py、joint_state_support.py）；`evidence_sha256` 是非空的已通过验收结果文件相对路径到SHA-256字典。验收文件本身的哈希也被plan绑定。

主代理明确放行后，按顺序仅执行一次，工作目录 `/workspace/paper`：

```sh
python3 research/chapter3_certified_state_pruning_20261111/full_static/run_pair.py freeze
python3 -u research/chapter3_certified_state_pruning_20261111/full_static/run_pair.py run
python3 research/chapter3_certified_state_pruning_20261111/full_static/compare_pair.py
```

OFF/ON均开启旧选项支持传播，其他flags和输入相同，只切换prune_joint_states。每组300秒worker方法窗口、380秒外部保护，一组失败即停、不补跑。禁止求解、子进程和候选热评价；保留原系数生成作为静态构模的一部分。

输出每组claim、阶段进度、模型/预处理报告、完整options/names/NPZ矩阵、row tag与物理gate-name、能量强化证书及逐状态exact box implication。构模后的证书复核/导出计入方法窗口，最终归档可能越过协作检查点，因此完整wall另记，不称严格实时截止。

比较器不构模：OFF必须与原归档全部数组字节相等；共同变量界/目标按名字重编号后字节相等，events/options不变；将OFF中被删w代0并去掉对应物理行后，其他非能量强化行按tag/名字/系数/右端精确binary64多重集相同。能量强化行另用原lower行和导出boxes上的Fraction最大差证明，绝不借求解容差。前置支持证明和gate0冗余为主代理验收门的一部分。完整LP松弛不要求相同，静态规模及构模耗时不是求解加速证据。

本次实际已由主代理验收并放行，freeze/run/compare各执行一次成功。最初草案状态保留在preparation.json，实际结果见REPORT.md和comparison.json。
