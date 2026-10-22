# K165：R2整体MILP请求传输与原生证据核对

**未定位到x0传输或参数位置错误。24项只读核对通过，MATLAB、LP、MILP及热评价均未执行。** 不一致已经存在于原生MAT和原生JSON中；具体内部数值原因仍未确定。继续保留未决停批，不恢复24次调用。

## 已核清的传输链

| 环节 | 原始证据及结论 |
|---|---|
| Python首请求注入 | `initial_point.py:175-193`的包装器只在第一次请求注入本次x0；`matlab_bridge.py:599-656`写出MAT后才发布request JSON。 |
| 请求MAT | x0为23464×1的double，整数索引是MATLAB的一基1—1131；x0目标值1.0781873036868874。 |
| MATLAB收到的点 | 原生MAT保存的`initialPoint`与请求MAT的x0逐元素、逐字节相同；向量SHA256为`3614164448fbc4cdc8e2372e35e2677e246bffba8b097af40b78cf001983b214`。 |
| 实际函数调用 | `solve_model.m:149-150`把`initialPoint`放在第9参，opts在第10参。本地R2023b `intlinprog.m:1、184`使用同一签名并将其赋给`problem.x0`。 |
| 原生返回与JSON | 原生MAT、response JSON和Python归档均为空x、空fval、exitflag=-2；不存在Python将有效向量删空或把其他退出码改成-2的证据。 |
| 回调事件 | 独立event、native MAT与response中的回调一致：只有init/done，没有rootlp/cutgen/branching事件。done计数1，但x、fval均空；最终output计数0。 |

R2023b接口确实将第9参解释为x0、第10参解释为options；文档要求x0满足约束。退出码-2、0、-1分别对应未找到可行点、提前停止、由回调或绘图函数停止。[R2023b官方接口](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html)

回调x只有发现新整数可行解时才非空；done只表示结束，time从init起算。因此done计数1不能补出一个新安全解，也不能独立证明求解器接纳了x0。[R2023b回调说明](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog-output-functions-and-plot-functions.html)

## 时间与状态不能扩大解释

| 时钟 | 记录 |
|---|---|
| Python方法总时间 | 298.391秒；budget_valid=true、budget_exhausted=false。可以排除本次响应因越过Python 300秒根截止而被丢弃。 |
| 原生请求分配 | 271.406秒；扣除读取和准备后，MaxTime=270.103秒。 |
| 原生intlinprog调用 | 268.002秒，距MaxTime约2.10秒；不能据此排除内部LP时限或其他内部停止路径。 |
| done事件 | 请求时钟269.306秒，optimValues.time=267.227秒；两个计时起点不同。 |
| worker时钟 | 274.192秒，guard=286.344秒。未归档每次callback返回的stop值，不能将源码条件检查写成stop始终为false的实证。 |

没有详细原生日志，Display为off，没有阶段事件，警告及callback错误字段为空。**当前不能定位为根LP数值失败、割平面故障、内部时限问题或求解器缺陷。** `IntegerPreprocess='none'`也不表示内部完全不做预处理；官方说明它仍保留少量整数预处理。[R2023b选项说明](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html)

## 已定位的报告口径问题

`p0_batch/audit_whole.py:97-100`把状态一致性诊断也计入`observed_numerical_rejection=True`；`execution_status.py:144-147`随后给出通用原因`ACTUAL_NUMERICAL_REPORT_REJECTED`。本槽x0残差报告实际上全部接纳通过，因此该原因字面过强。

准确表述应是：**同一请求的显式初始点通过Python数值接纳，但原生报告未找到可行点，二者关系尚未分辨。** 保留数值未决并停止是合理的；本轮不改冻结分类、不清除旧U，也不将其改成正常截止。

## 可复核工件

| 工件 | SHA256 |
|---|---|
| request_000001.mat | `9a18a3fa0735c810082b6af895938feebb0be97c787d04f39469bbbedd2f0f91` |
| request_000001.native.mat | `1f6246a1108e7250af3ca9305ad5b40c99ae66d59cd52866a6f3bacbfb766c3a` |
| request_000001.python.json | `0c5182a9816b89d3924ecafe1bc077772ce9066845d32f0cb9064e72416d4b11` |

`transport_review.json`保存完整证据hash、248源hash、本地R2023b入口hash、时间值和24项检查。只选择读取native MAT中的数值及结构字段，没有执行或解包其中的MATLAB对象，也没有复制MathWorks完整源码。第一版报告序列化遇到NumPy布尔类型问题，失败记录与源码已保留；后续修正仅涉及新诊断文件及定位文字，原研究调用未重复。
