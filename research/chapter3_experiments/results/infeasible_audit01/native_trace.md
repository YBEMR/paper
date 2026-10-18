# 原生处理链只读审查

日期：2026-10-18。范围：`formal_comparison02/response_R__R2__milp`、当前及冻结MATLAB包装、本机R2023b可读源码和官方文档。未运行任何求解、热评价或正式案例；未修改原产物、活跃源码或Git。

## 结论

异常发生在原生求解返回，不能由现有日志进一步定位到某一内部算法。现有证据不支持“参数传错”“超时”“严格改进子问题无解”，也不足以断定MATLAB存在某个具体缺陷。一个明确的观察缺口是：关闭整数预处理并不关闭独立的LP预处理；归档公共属性表也没有保留后者。

## 可定位事实

| 检查项 | 结果与定位 |
| --- | --- |
| 实际版本与许可 | `matlab/ready.json`：`23.2.0.2365128 (R2023b)`，Optimization Toolbox checkout true，入口为安装目录 `toolbox/optim/optim/intlinprog.m`。 |
| x0的传递 | `solve_model.m:30–43,83–84`：从本请求MAT文件加载`p.x0(:)`，原样作为第九参数传给`intlinprog`，无舍入、修复或自动重启。原生JSON记77347维、目标1.6266675298897528 J。 |
| Python接纳 | `matlab/request_000001.initial.json`：不等式最大正残差2.1316282072803006e-14；等式、上下界及整数残差均0；1e-9/1e-6容差下接纳。这是数值接纳，不是精确有理可行性证书。 |
| 最终原生返回 | `matlab/request_000001.response.json`：`status=SOLVED`、`exitflag=-2`、x和fval空、`output.numnodes=0`、`output.numfeaspoints=0`、上下界与gap空。警告消息及标识均空。 |
| 回调不一致 | 同一JSON和原事件文件：init的`numfeaspoints=0`；done为1，但x、fval和lowerbound仍空。不能据计数1推断提供过一个可读取的新合法候选。 |
| 不属于超时 | 原生MaxTime=258.57254819995904 s，`intlinprog_call=189.8330028 s`，method内收到done约231.281 s，整体约233.047 s；没有预算停止退出码。 |
| 不属于显式改善子问题 | `ObjectiveCutOff=Inf`、`ObjectiveImprovementThreshold=0`；没有热反馈行；此前档案已核x0与请求、原生initialPoint一致。 |
| 本地入口检查 | 安装目录`optim/optim/intlinprog.m:129–139`依次`createAlgorithm`、`checkRun`、`run`；本次没有入口异常。官方说明x0不满足约束时应报错，因此可说没有在入口拒绝x0；不能提升为内部每阶段均保留该点。 |
| 不能定位内部阶段 | 实际算法`+optim/+algorithm/IntlinprogBranchAndCut.p`及`checkInitialPoint.p`等为P-code。日志Display off、phase空、没有迭代LP行。零节点仅说明未进入分支树，不能区分LP预处理、根LP、整数预处理和初始割阶段。 |

## LP预处理是单独的设置

本地`+optim/+options/Intlinprog.m:128–150`将`LPPreprocess`列为Hidden、Dependent属性，:376–377有setter，:527–528有getter，:711默认`basic`，:773允许`none/basic`。当前`solve_model.m:47–51`仅设置`IntegerPreprocess='none'`；:61用`properties(opts)`归档公开属性，原JSON不包含`LPPreprocess`。不能据公开JSON认定全部预处理已关闭，也不能仅凭默认值把实际内部故障归因于LP预处理。

R2023b官方选项表明确区分两者：`IntegerPreprocess='none'`仍执行少量整数预处理；`LPPreprocess='none'`才关闭LP预处理。官方算法顺序是LP预处理、根LP、整数预处理、割、启发式、分支树。[intlinprog接口](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html)、[算法说明](https://www.mathworks.com/help/releases/R2023b/optim/ug/mixed-integer-linear-programming-algorithms.html)。

本项属于诊断接口缺项，不是已证明的根因。`native.mat`保存了opts对象，可在后续授权的MATLAB只读提取中显式读取`opts.LPPreprocess`，不需要重构模型或调用求解器。

## 历史预检不能替代本异常定位

`milp_numeric_diagnostic04/diagnostic_manifest.json`记录单Stage六选项小域，唯一改变整数预处理basic→none；原矩阵未变，未注入已知点。`summary.json`显示exit1、5节点、目标0.7227105065740314 J，与独立物理评价吻合。这支持采用当时工程兼容设置，但既不是当前77347维实例的证明，也没有证明所有LP预处理和根LP数值问题消失。前三项等价缩放失败记录仍保留。

## 最小后续建议

1. 先在Python和MATLAB对同一归档矩阵、x0逐项计算原始及归一残差，并核查近消去行、系数跨度、固定零列/界；先排除表示与传输错误。保留数值可行与精确可行的区别。
2. 若需原生定位，预先声明独立诊断限额，使用原MAT、不构造新候选，开启Display iter并显式归档LPPreprocess及所有关键参数。首先要求可观测，不将诊断产物补入原300秒正式结果。
3. 只有日志把范围收窄到预处理/根LP后，才作单因素`LPPreprocess='none'`诊断。它不改变数学域，但改变求解设置；未实际验证前不能称修复成功，也不应同时改容差、算法和缩放掩盖归因。
4. 包装层应保留独立SAFE及U，并把“已接纳x0/安全见证与原生无解冲突”单独列为数值一致性异常；不能升级为模型不可行或最优证明。

原生数值细节、日志和矩阵定位足以支持上述有限诊断；不需要另开MILP认证或换求解器路线。
