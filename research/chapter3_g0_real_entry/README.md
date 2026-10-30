# G0真实后端接线：模拟验收版

依据575788ee限定接线协议。当前只能创建SIMULATION许可；未批准真实科研预算，没有可用REAL许可或实际OS进程工厂。代码中的原生函数绑定是懒接线，不能通过字符串改名或翻全局开关启用。

| 文件 | 已接接口 |
|---|---|
| gating.py | SIMULATION能力与真实研究授权分离 |
| model_backend.py | 原Model/expand_options/RC入口、模型视图、x0与严格反馈；模拟必须显式假依赖 |
| receipts.py | 复用完整U校验，分开人工/SIMULATION/未来REAL来源，补control_policy源hash |
| session.py | 根会话寿命、当前scope启动等待与每请求上限；原solve/close函数不改 |
| numeric_transport.py | 原C第二阶段增广数学接口，普通截止与真实数值冲突分开 |
| backend.py | 同次HEFT、共享G0协调器、两阶段原生请求、清理与SAFE保留 |
| worker.py | 共同输入核hash、方法归档、独立post处理；原热回执不被伪造模型视图字段 |
| runner.py | 单次方法/至多单次post模拟监督，身份及能量区间相容门 |

同时只对原G0的method、receipts、local_model增加profile/依赖接缝。旧chapter3_experiments、物理模型、正式输入、历史结果不改；原构模数值后缀238行仍逐字保护。

模拟复跑（输出目录必须是新的）：

```powershell
& 'F:/Anaconda3/python.exe' -B -m research.chapter3_g0_real_entry.tests.run_checks --out research/chapter3_g0_real_entry/results/wiring_next
```

最终[wiring04](results/wiring04/checks.json)：49/49项；原[32项人工回归](../chapter3_g0/results/manual07_wiring_regression/checks.json)：32/32、180断言。两套分进程运行，避免旧A32模块重载影响类身份。

全部进程、HEFT、选项/系数、视图评价和求解依赖均为明确假后端；仅复用原PARTIAL结构检查/聚合及手给数值行导出。模拟夹具保存在各次scratch目录，不递归删除。wiring01的临时目录权限失败、wiring02的夹具根断言失败及wiring03版本均留档；本地不可读临时目录被精确忽略，其失败回执保留。

真实新Python进程、MATLAB启动/响应/清理和调度质量均未验证。待用户明确批准预算后，还须冻结一次性真实启动入口、授权消费与当前资源门；不能把本模拟runner称为已验证的实际OS监督器。预算提案仍为C01一次300秒、正常完整SAFE最多一次60秒post、进程480秒/整批720秒，无补跑。
