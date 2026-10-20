# R2023b接口核对

核对日期：2026-10-20。仅用于解释已有状态，不据此调整选项或追加求解。

1. [R2023b intlinprog](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html)的Input Arguments／Options及Output Arguments：`x0`是初始可行点输入；`ConstraintTolerance`允许范围为1e-9至1e-3，衡量线性约束的数值偏差。它没有把Python浮点残差接纳变成独立精确证书。当前1e-9不变。
2. 同一版本退出语义中，−2为未找到可行点；−9另指可能因病态矩阵丢失可行性。当前实际是−2，不能引用−9的说明直接证明本次根因。空x／fval和缺失内部界按原记录保留。
3. [R2023b Tuning Integer Linear Programming](https://www.mathworks.com/help/releases/R2023b/optim/ug/tuning-integer-linear-programming.html)的Large Coefficients Disallowed讨论1e15以上系数的拒收及缩放。当前已存最大系数约60，不属于该阈值故障；“同行系数比很大”是本次存档算术结果，不能说官方已经确认它导致此次退出。

本机原版`F:/Matlab2023/Program_Files/MATLAB_R2023b/toolbox/optim/optim/intlinprog.m`的帮助头同样列出−2与−9的区别。仅阅读公开帮助及本机接口，未修改MATLAB或使用当前新版本的HiGHS算法说明代替R2023b语义。

本次定向检索词：`site.mathworks.com intlinprog numerical infeasibility scaling initial point ConstraintTolerance`；随后只读取上述两个固定R2023b官方页面。没有新增论文筛选或求解器路线。
