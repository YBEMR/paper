# 冷启动三臂静态性能执行器

当前仅准备代码及AST语法检查，**尚未freeze、构模、求解或热评价**。主代理必须先把实际通过的小域/完整数值身份验收证据及优化后源码SHA写入acceptance.json，明确GO后才可执行。

预先固定顺序为 `old_on → optimized_on → off`，每臂一次、300秒worker总预算、380秒外部回收保护，无失败重跑。old_on使用fe6216af中已归档217份原源码；optimized_on与off使用同一组本轮验收后源码，前两臂仅认证实现不同，第三臂关闭剪枝。三个进程均冷启动Model和认证缓存，不加载旧缓存。没有控制操作系统文件缓存，不能称机器级冷启动。

完整auto-L R1输入、12次Stage、5ms起点和非整数结束、场景、物理及所有baseline_flags保持。propagate_support始终True；old_on/optimized_on的prune_joint_states=True，off=False。模型构造中原区间系数生成允许，所有LP/MILP、候选/轨迹热评价及初始化禁止。

## 验收文件合同

```json
{
  "enabled": true,
  "evidence_passed": true,
  "source_sha256": {
    "research/chapter3_experiments/milp.py": "实际通过后源码hash",
    "research/chapter3_experiments/joint_state_support.py": "实际通过后源码hash"
  },
  "evidence_sha256": {
    "research/本轮实际验收结果路径.json": "该结果文件hash"
  }
}
```

freeze复核身份再复制两套217源及原输入。run再次核验并以独占batch claim防止复用启动；每worker输出矩阵、变量名、options/events、全部行元数据（Big-M/外包allowance/RHS区间）、能量cut证书及完整预处理/缓存报告。

```sh
python3 research/chapter3_pruning_audit_optimization_20261111/static_pair/run_pair.py freeze
python3 -u research/chapter3_pruning_audit_optimization_20261111/static_pair/run_pair.py run
python3 research/chapter3_pruning_audit_optimization_20261111/static_pair/compare_pair.py
```

每worker入口至构模导出、证书检查均计入300秒协作预算；归档时间另列，父进程墙钟还包括最终结果写入及退出。所有缓存准备成本包含在build中。阶段来自原BuildObserver与优化实现原始stats；没有仪表的项目标明缺失，不反推数值。

Linux峰值内存使用getrusage(RUSAGE_SELF).ru_maxrss，记录导入前、构模后、导出后、归档后快照。它是当前进程寿命峰值，含先前阶段，不是构模增量峰值，也不能用两个峰值相减得到某阶段真实峰值。

compare要求两个ON全部NPZ数组/变量名/行元数据字节相同，原版ON及新OFF分别与此前归档数组相同；两ON的2938个删除状态身份、29380条冗余证明结果、全部424能量cut证书相同。输入、事件、整数索引、界、目标、Big-M和外包表示都在此覆盖。原精确整数模型语义与求解器近整数容差/LP松弛行为仍区分，不宣称未运行的求解性能。
