# K195：同域整体MILP的一次性执行准备

本轮只准备和纯预检。没有创建真实批准文件，没有启动MATLAB、构模、求解或热积分。

目标是让原whole独立使用K193／K194同一受限输入，之后与有限域ε最优参照比较。保留原H、AB／AC共享部署、完整三Stage链、400 ms／5 ms、四节点、auto-L、温度漏电、期限及原生数值选项。Stage选项78→72仅因原期限必非法过滤；不固定共享A设备，不使用局部／分解／增广表达。

| 文件 | 职责 |
|---|---|
| `run_once.py` | 冻结197份科学来源、原输入／配置和执行适配层；一次性监督、共同300秒根、最多一次60秒post、480秒日历 |
| `domain_contract.py` | 静态1550清单覆盖；实际构模后的72个Stage整数变量、选项目录、物理变量及完整场景检查；候选受限域合法性 |
| `native_contract.py` | 核已有ready／request／response：R2023b、许可、原生选项逐项一致，只有MaxTime随同根剩余变化 |
| `admission.py` | 复用原300秒whole审计；技术异常后保留已成SAFE证据，但禁止正常排名或post；post只核固定旧候选，不改原U |

方法根由原`MethodBudget`在病例读取前建立，输入hash、独立L0、构模、原初始化、MATLAB启动、求解及内部连续复核共同计费。Python启动／科学模块导入和末尾纯归档／进程清理另列，均计480秒日历。420秒方法监督上限只是清理余量，不是延长300秒证据域；post剩余不足完整60秒及返回余量时不启动，另为日历末尾预留15秒清理。阻塞导致实际超限时明确标为日历超限，不报告正常完成。

实际执行前需用户独立批准1次300秒方法、正常完整SAFE最多1次60秒post、480秒日历。冻结`plan.json`始终保持`authorized=false/execution_enabled=false`；未来批准写在另一份绑定计划SHA、固定新输出目录与准确次数／预算的`approval.json`，不修改旧计划或K194结果。没有该文件，入口在创建进程前拒绝；同一输出只消费一次。直接调用method／post还须有匹配的监督器阶段请求。

当前计划与纯证据在`../results/small_whole_preparation01/`。模拟回执／模拟进程不产生真实授权、SAFE或最优性结论。内部审查不冒充外部批准；这是一套防止误用的软件约定，不宣称能阻止有写权限者蓄意绕过。

```powershell
& 'F:/Anaconda3/python.exe' -B -m unittest discover -s 'research/chapter3_experiments/small_whole_execution' -p 'test_*.py' -v
```

上述只运行纯夹具。真实小域数值构造是否成功、总变量／行／非零数、原生启动和优化质量仍须获批后的唯一方法调用验证。K194最佳方案、轨迹缓存和历史SAFE不能进入初始化；它们只由后续只读结果比较读取。
