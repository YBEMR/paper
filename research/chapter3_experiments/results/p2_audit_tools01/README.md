# K161终态纯存档核查工具

`audit_terminal.py`默认读取P2；只有`process_terminal.json`已经存在才读取账本/方法记录。执行中不作大扫描。工具不修改批次文件，结果用`--out 文件名.json`独占写入本目录，已有文件不覆盖。

在仓库根目录运行：

```
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/p2_audit_tools01/audit_terminal.py --out p2_terminal_review01.json
```

核查来源/源码快照、预检与协议、旧P0/P1/准备文件、消费前缀/禁止重跑、300秒根预算与19200秒日历、原始分类复现、完整安全回执/精确合法性/现有post、原U与区间/首次安全截止、artifact哈希。构模/求解/热评价/子进程入口均加禁止门；只允许原只读回执分类和精确时间表合法性检查，不重新做post。

完整40槽与故障停止分开。停止的最后一个已消费槽可保留不完整证据，明确列入`unresolved_or_partial_evidence`、不排名；无U不填0。`passed`仅表示存档核查，须同时看`campaign_completed_40`，不能将“已核停止证据”写成40次完成。

热反馈按原始路径列出列表数量，重复嵌入不相加为独立次数；`any_nonempty_feedback_list`只表示存档出现非空反馈列表。独立证明状态原样登记，不把solver-reported无解或局部收敛改写为独立证书。

## 工具核验

- `--fixture-p1`只读P1既有终态，不写旧目录，不形成P2结果。
- 首轮P1结构核对706项中的5项失败，均为联动场景在`aggregation.scenes[sid].result`内嵌套热轨迹，而工具按直接轨迹检查。原分类重现、post、hash与预算检查均通过；`p1_fixture01.json`保留。
- 修正只读schema适配后，P1的706项全部通过，见`p1_fixture02.json`；当时准确源码保留于`audit_terminal_tested_p1_v02.py`。
- 当前版新增仅测试用停止快照入口和异常落盘。`test_stopped_fixtures.py`用P1元数据制作0消费/1消费后中断两份临时合成视图，分别26/27项通过；原P1未改，未读P2运行账本。见`stopped_fixture01.json`。
- 当前准确源码再核P1旧完整存档706/706通过，见`p1_fixture03.json`，脚本hash与停止夹具记录一致；没有额外物理计算。
- 所有测试均为纯记录核验，0新研究、0构模、0求解、0热评价、0post。内部工具不是外部审查批准。

缺失或格式损坏的记录可能使核查失败或保留未决；工具不会用重新评价填补证据。MAT工件本地核hash，遵守gitignore，不上传或自动重建缺失文件。
