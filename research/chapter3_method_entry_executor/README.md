# 小规模方法接入一次性执行器

本包承接e2ab155b冻结提案，仅读取已冻结的common_input.json。阶段二仅实现和模拟；真实运行必须另有绑定最终plan SHA的用户批准文件。当前模板authorized=false，未创建真实claims。

| 文件 | 职责 |
|---|---|
| common.py | 输入/源码/runtime与批准范围核对，完整及时SAFE证据核查和checkpoint保留 |
| worker.py | 新Python中的whole/HEFT/SA入口或独立post；授权及监控握手后才导入算法 |
| runner.py | 固定顺序、单次账本、子进程墙钟、内存采样及故障停批 |
| monitor.py | PID＋创建时间识别、1秒RSS采样、限定身份终止及宿主资源门 |
| freeze.py、run_checks.py | 绑定源码/数值依赖，复制同一输入，生成false批准模板并运行纯mock |

统一输入仍是C01前2场景、每场景6 Stage/2请求、共12次执行/8共享身份，原H/50—80°C/230ms/5ms/四节点/auto-L。原算法、物理模型、精度、合法域和历史实验不改。

方法根300秒沿用原MethodBudget，在处理输入前开始，包含初始化、构模、MATLAB启动、搜索和内部完整检查。进程墙钟另含解释器/导入、清理及归档，上限480秒，不增加搜索时间。每份正常最终SAFE最多一次独立post，启动post进程前起60秒，不修复、不择优。全批最多3次方法/900秒、3次post/180秒、1800秒日历，固定whole→HEFT→SA101。

仅读取本次common_input.json，不读旧参考表、SAFE或热缓存。保存输入/源码hash、首合法/首SAFE、初解与原生入口、最终SAFE/E、原始结果/日志及内存序列。故障与已有SAFE分别保留，缺末态时只能核已有checkpoint，不能补算。

Python/MATLAB按本次PID及创建时间每秒采样，记录同刻RSS和的采样峰，不相加不同时间的生命周期峰。采样树须结合原MATLAB严格清理回执；不是OS容器隔离。资源门：物理可用2GiB、可提交余量4GiB、磁盘2GiB、无遗留MATLAB、非AppContainer。缺测拒绝，不自动安装依赖或降低门槛。

真实CLI要求批准文件绑定plan/input SHA、次数和预算，有明确用户批准依据。全局claims/<plan_sha>.json排他消费，每slot另有票据/启动claim；未确认根身份不得放行算法。字段漂移、旧目录和重复claim拒绝。故障停批，禁止重试、续跑、自动换输入或延长预算。

阶段二复跑命令：

```text
F:/Anaconda3/python.exe -B -m research.chapter3_method_entry_executor.run_checks --output research/chapter3_method_entry_executor/results/<新目录>
```

测试入口禁止真实subprocess、算法、构模和热积分。manual_mock_artifacts全为模拟数据，不可作论文SAFE/能耗、实际进程或执行批准。源码改变后另存新预检，旧记录保留。

真实命令仅在下一轮获批后使用：

```text
python -B -m research.chapter3_method_entry_executor.runner --plan <最终冻结目录> --plan-sha256 <最终SHA> --authorization <另行批准文件> --output <本包新的results目录>
```

当前false模板会在新进程和方法调用前拒绝。此软件协议防止误操作，不宣称同账号具有不可绕过的权限隔离。OS资源读数、真实Python/MATLAB启动和原生求解本阶段均未实际验收。
