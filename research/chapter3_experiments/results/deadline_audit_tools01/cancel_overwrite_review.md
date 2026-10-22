# K163停止原因：预算取消标记被既有包装层覆盖

本批监督终态已停止，消费2/40槽，1槽COMPLETED，38槽未启动。只读终态核查[62项通过](deadline_terminal_review01.json)表示档案/停止/消费证据自洽，不表示40次完成或第二个方法正常结束。所有科学调用禁止门为0。

第二槽`beta_1.0__R1__anchor_linked4`原状态仍为BLOCKED/TECHNICAL_FAILURE_CONFIRMED，唯一硬错误为`MISSING_MATCHING_ROOT_CANCEL_FILE`。当前期限合法性审计通过；已形成的完整安全U为0.880088064994047038074332338796147624637570598002142665061662 J，时间255.15599999995902秒。原证据保留，但该槽未进入一次post，不能写作已有post验证的安全输出。

## 原因链

1. 根方法在300秒到期，最后一个原生请求为第4号、第二阶段AC场景第1轮。Python保存BUDGET_EXHAUSTED、budget_valid=false、accepted_for_evaluation=false、x=[]，允许响应后来出现但拒绝预算后新向量。
2. `matlab_bridge.py:663–675`的PublicationTimeout处理先写`.cancel`内容`budget`。
3. 既有`augmented_method.py:140–152`的`_Request.fail`随后记录回调未检查完及根预算原因，覆写同一文件为`augmented numerical admission unresolved`。相关原因链仅有CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED、BUDGET_BEFORE_FINAL_ADMISSION、BUDGET_DURING_ADMISSION_ARCHIVE；已有数值report均accepted=true。
4. 原cutoff适配已核根300秒、同一请求与绝对期限、拒绝晚向量、此前请求完整、无数值拒绝及进程树隔离；但`deadline_entry.py:151–157`的额外门只接受cancel内容严格为`budget`，因此在文件确实存在时仍报“缺少匹配根取消文件”。

这是现有取消记录内容审计过窄的具体问题。没有发现期限违规、无种子或新的数值拒绝证据。不能仅把通用字符串加入白名单：真正数值错误也会写同一字符串，仍须完整核对根预算、同一请求身份、失败原因集合、数值接纳和隔离链。

## 可重复小夹具与边界

[核查脚本](review_cancel_overwrite.py)及[15项结果](cancel_overwrite_review01.json)保存；12类科学/模型/热/子进程/种子生成禁止门全0。手写小对象直接调用既有`_Request.fail`文件记录方法，证明预算失败和真实数值失败均能把原`budget`标记覆写为同一通用字符串，没有调用构造器、MILP或热传播。

核查保留原方法结果、两份不可变回执、python/input/cancel/cleanup文件及源代码hash，检查前后均未改。旧底层cutoff适配在同一证据上给出的派生状态为NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST，U与原值完全相同；该派生视图只是定位额外内容门的差异，**不改写原始BLOCKED终态、不产生新安全U、不授权继续科研调用**。

建议仅考虑独立的存档适配修正：在完整现有因果链全部成立时解释覆盖标记，同时继续拒绝非预算原因、实际数值错误、身份/隔离缺口和缺文件。已消费两槽不重跑，38未启动槽是否续接及原安全结果的既定一次post由主代理按授权范围另行决定。本审查未启动任何后续调用，也未运行额外post。
