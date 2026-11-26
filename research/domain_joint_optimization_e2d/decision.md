# E2-d 核心算法结构筛选

**正式比较未决。** 已独立复核 2/9 个终点。停止状态为 FORMAL_INTERRUPTION。

Traceback (most recent call last):
  File "F:\by\11111\papers\文献分类补充包_20261119\P1_worktree\research\domain_joint_optimization_e2d\batch_d.py", line 114, in run
    wave(s,[v for v in m["runs"] if v["wave"]==n],False)
  File "F:\by\11111\papers\文献分类补充包_20261119\P1_worktree\research\domain_joint_optimization_e2d\batch_d.py", line 82, in wave
    r["status"]="INTERRUPTED";record(s);raise RuntimeError((r["tag"],code,elapsed))
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
RuntimeError: ('NoCore_101', 1, 809.3909929000074)


## 运行工程与预算

E2-c2 的种子 103 在最初两个联合阶段启动工作进程 14 次。原记录缺少导入与资产加载分项，底层原因未知。原辅助阶段 7.55 毫秒越界及退出观测延迟保留在冻结记录中。
本轮正式工作进程重启共 0 次，就绪超时 0 次。最长辅助阶段 8.2905 秒，最长局部子问题 17.3566 秒，最晚进程退出观测 893.8328 秒。

正式计费 2700.00/8100 秒。预检计费 443.44 秒，独立复核、归档及总额见预算回执。各时点能耗、分项、认证区间、末 180 秒收益及期限余量见 results.csv。
