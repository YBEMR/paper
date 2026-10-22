# K167：整体MILP增广接口适配与纯夹具预检

**已实现可选whole增广入口，保持原模型和完整评价／反馈流程。本轮只验收数值接口，不判定R2原生数值冲突已修复。** 用户原参数、合法调度域、1e−9/1e−6容差及连续热安全标准未变；期限组仍16次已消费、24次未启动。

## 实现范围

- 新增`whole_augmented.py`：复用既有选择性精确变换，按当前whole模型的names/row_tags及数组hash建立每次请求的映射。新增连续补变量，不改原整数坐标、调度选择和目标；不可无损改写的行按既有规则保留。
- 原`formal_milp.py`只增加可选记录器／诊断函数注入口，默认路径不变。新入口`execute_whole_augmented`单独创建context；未注册或启动旧批次执行链。
- `_InitialSession`保持在增广session外，原x0只在首请求追加补数。callback/final均通过原矩阵、增广矩阵、link、整数和目标接纳，再把原坐标交给原whole Recorder。完整多场景评价、缓存和最终候选热反馈继续采用原流程。
- 原生`native_rounds`与派生`rounds`分别保存；新增只读身份审计，核请求编号、回调编号及非x内容、文件hash、原/新矩阵和映射。原`audit_whole`未放宽。MATLAB原代码会清空最终callback列表中的x，因此回调内容对照排除x，流中向量另走数值及完整评价门。
- 所有变换、接纳和日志仍使用同一MethodBudget。正常截止、数值异常、技术故障分列；取消文件独占创建，不覆盖已有budget标记。截止或档案写入异常保留已形成的完整见证，不接纳迟到新U，不自动重试。

原248份源中仅formal的最小hook被修改，其余247份、原配置／输入、旧实验档案和账本保持。原增广工具、模型、评价器、MATLAB桥接及原生求解代码未改。

## 纯夹具验收

可复跑入口：

```powershell
F:/Anaconda3/python.exe -B research/chapter3_experiments/precheck_whole_augmented.py --out research/chapter3_experiments/results/whole_augmented_precheck01/另一个全新目录
```

入口拒绝覆盖已存在目录。仅使用手写小稀疏矩阵、fake session、可控时钟和显式decoder/evaluator替身；替身SAFE/U不是研究结果。真实构模、MATLAB、优化器、子进程和热积分由属性替换与真实函数code-object调用守卫共同阻断，默认参数捕获的旧函数也不能绕过。

验收覆盖：连续投影及原整数前缀、混合保留行、双场景共享变量、link容差放大时原行拒绝；x0、回调、最终解、重复、近整数与非法候选；反馈后新身份及不复用x0；原生／派生篡改；正常截止、迟到拒绝、旧SAFE保留和技术错误；错请求编号与取消标记保护。原生内部界仍只作为solver-reported信息，不升级为独立界或最优证明。

**最终`run04`共26项通过、0失败、0错误，真实科学入口守卫计数全0，10份被核源码前后hash一致。** 有效凭据为`run04/checks.json`；增广模块绑定SHA256为`f913b927e7ef6e1c58e682442d4bfd94e137fa7dfbc6ecb834b5aaf5e49d98bc`。`run01`为初稿24项通过，`run02/03`为26项通过；三者对应历史源码，不作为最终版凭据。最后发现原formal会把预算内技术失败的budget_valid=false写成“预算后返回”；仅在新接口保留原reason并补正派生分类，按同一套26项重新绑定最终版本。root首次hook编辑因换行预期不符而在写入前停止，失败记录留存。

最终[内部审查](independent_review/final_review02.json)15项及3项AST核对通过，活动入口登记在`independent_review/review_manifest02.json`。真实保存层注入OSError的8项核对确认保留已成替身SAFE/U；先前替换整个archive方法的探测绕过异常契约，已标无效并保留纠正记录。同编号异内容回调的较早版本独立负例见`independent_review/callback_identity_probe01/`，不冒称最终版重跑。以上均为软件接口检查，不替代外部ChatGPT批准或真实物理验证。

## 尚未验证与下一步

本轮没有研究构模、原R2载荷转换、MATLAB/LP/MILP调用、热积分、post或新增研究U。实际whole可改写行覆盖率、维数和构造成本、真实MATLAB接纳行为及R2的−2根因仍未知。纯夹具通过不能写成故障已修、节能改善或热反馈收益。

本阶段到接口验收结束，不自动恢复24次或扩大实验。下一项若要确认原生兼容性，应另定一次有界技术诊断及预算、绑定新的代码版本；它与是否补齐期限组、是否优先机制实验分别决定。旧批次结果保持原版本归属，不因适配完成就拼成一次完整同版本比较。
