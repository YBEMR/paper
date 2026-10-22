# 原生计时语义的补充边界

R2保存的native MaxTime=270.102973100 s，intlinprog_call=268.0019913 s，差2.100981800 s；done values.time=267.226997 s。Python根时钟298.391 s小于300 s、budget_exhausted=false，只排除了已记录的Python根预算截止，不能据此排除原生内部MaxTime或LP停止语义有关。

当前原生exitflag为−2，未保存可定位的根LP退出轨迹。报告不认定“发生在根LP”，也不认定“与计时完全无关”。两份当前回执均done计数1、final计数0；其中R1是时间退出0，该现象不能单独证明x0被solver接纳。

这是对summary.md计时解释范围的补充；没有改变任何原始状态、SAFE/U、容差、预算或研究输入。来源见facts.json的targeted_receipts[1]及其绑定native response；新增求解/模型/热/post均0。
