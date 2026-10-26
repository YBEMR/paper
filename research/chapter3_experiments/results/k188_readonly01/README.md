# K188只读证据入口

- [报告](../../../完整MILP数值异常定向诊断_K188.md)：事实、归因边界及最小诊断方案。
- [最终静态核查](matrix_inspection_final02.json)：原K187二进制数值载荷，0新研究调用。
- [原生调用提案](protocol_proposal.json)：未获批准，两个执行开关均为false；此目录没有真实执行入口。
- [交付核对](delivery_checks.json)：原载荷、冻结源码、提案与报告的静态一致性。
- [内部交叉审查](internal_review.json)：代码／数学与提案审查，不是外部审批或研究调用授权。

`matrix_inspection.json`与`matrix_inspection_final.json`为补齐精确整数断言、全部纯整数行检查和浮点带宽标签前的开发记录，不能替代`matrix_inspection_final02.json`。最终代码与文件hash在交付核对中登记。原MAT遵守原.gitignore留在本地，SHA256与原K187记录相同。

纯静态脚本可复跑，必须指定不存在的输出文件：

```powershell
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/k188_readonly01/matrix_inspection.py --out research/chapter3_experiments/results/k188_readonly01/另一次静态核查.json
```

仅加载既有MAT并执行稀疏矩阵和有理数运算；不导入生产模型，不启动MATLAB，不调用优化器、热积分或完整候选评价。整数列的移除只用于统计矩阵剩余结构，不是拟执行载荷的消元。拟议原生诊断保持原行列与目标，仅固定原intcon界。

本轮停止于报告与协议。若用户批准，下一轮再建立一次性执行入口与模拟检查，不能把本目录的静态通过当作原生兼容已通过。
