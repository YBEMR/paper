# D281：完整 R1 替代求解器准入与无损接口准备

2026-11-13；基线 `5db2d8f369f84c15ba7d343aaa9d78b3ad4f0dfd`。

**结论：目前不具备申请下一次完整 C 科研求解的条件。** 两个可运行 Python 环境均未发现 Gurobi、CPLEX、DOcplex 或 highspy；没有核实可覆盖完整 R1 的商业授权。按本轮停止规则，商业原生后端的实施准备已停止。本交付完成后端无关的矩阵契约、模拟接线、31 项纯控制测试、保存矩阵离线回读及 Benders 数学分析；没有实现或伪装成可运行的 Gurobi/CPLEX 执行器。

**唯一首选为有条件的 Gurobi Python；唯一备用为原生 HiGHS/highspy。** 这是环境缺口补齐后的技术选择，不是现有软件可立即运行的结论。不安装软件，不申请或修改许可，不将限规模版本拆成多个违规子任务。历史授权均保持已消费。

## 1. 环境、授权与兼容性

证据：[环境清单](evidence/environment_inventory.json)、[Python/MATLAB 接口](evidence/python_interfaces.json)。核查仅访问安装元数据、目录/文件名、默认 MATLAB pathdef、相关环境变量名称及许可文件是否存在；没有读取、复制或哈希许可内容，没有请求许可服务器，没有导入商业求解器或创建原生环境。

| 对象 | 本机只读发现 | 完整 R1 可用性 |
|---|---|---|
| 主 Python | `F:/Anaconda3/python.exe`，实际 3.12.4；NumPy 1.26.4、SciPy 1.13.1 | 科学数据读取可用；注册表的 Python 3.11.7 标签过时，以实际解释器为准 |
| 次 Python | `F:/Python39/python.exe`，3.9.9；未发现目标求解器包 | 无可用替代后端 |
| MATLAB | R2023b/23.2；另有 R2022b/9.13 注册记录 | 没有启动会话；R2023b 文件名及默认路径检查未发现目标接口。HighSpeed 文件为无关命中 |
| Gurobi / gurobipy | PATH、常见安装位置、注册表及两套 Python 均未发现 | 未安装证据充分覆盖已查范围；实际版本、许可有效期、学术资格均未知 |
| CPLEX / cplex / docplex | 同上，均未发现 | 无法验证完整规模授权；DOcplex 即使存在也不等于具有 CPLEX 引擎及许可 |
| HiGHS | SciPy 的 `_highs_wrapper` 二进制存在；独立 highs/highspy 未发现 | 内嵌引擎精确版本未从只读元数据得到，保留未知，不能用 SciPy 版本冒充引擎版本 |

检查了 Windows 常见 C/D/E/F/H 根目录、Program Files、ProgramData、用户 Programs、已知 conda 环境、PATH、卸载注册表及 Gurobi 默认许可位置。相关许可环境变量未发现，三个常见许可文件不存在。**H 盘访问被拒；任意便携目录、WSL、用户自定义 MATLAB 路径及账户侧授权不在已证实范围内。** 不能据此断言机器任何位置绝对没有求解器，也不能假设用户拥有学术许可。新增核查脚本修正了 `Verilog` 被子串 `ilog` 误匹配的问题；没有把它计为 ILOG 安装。

Gurobi 限规模许可上限为 2000 变量/2000 线性约束；CPLEX Community 为 1000/1000，均容纳不了本 C 的 23780/101818。学术免费版本可能无规模限制，但资格及本机实际许可必须另行核实。[Gurobi 官方限制](https://support.gurobi.com/hc/en-us/articles/360051597492-How-do-I-resolve-a-Model-too-large-for-size-limited-Gurobi-license-error)、[IBM 官方许可说明](https://www.ibm.com/products/ilog-cplex-optimization-studio/pricing)。

候选版本 Gurobi **12.0.3** 的官方兼容表覆盖 Windows 11 x64、Python 3.9–3.13、MATLAB R2019a–R2025a，因此当前 Python 3.12.4、MATLAB R2023b 在声明范围内。这仅是文档兼容，未验证本机 Windows build、动态库加载或许可。采用 Python 直连保存数组，不依赖 MATLAB Engine；不是必须安装 MATLAB 接口。实际安装若选其他版本，应重新核对并冻结版本，不静默套用本候选。[版本化官方手册，平台表](https://docs.gurobi.com/_/downloads/optimizer/en/12.0/pdf/)。

CPLEX 从 20.1 起移除官方 MATLAB 连接器，最后包含版本为 12.10；如以后选择 CPLEX，应核对匹配实际 Python 的 `cplex` 低层 API，而非退装旧 MATLAB 连接器。本机未安装，故具体 Python/CPLEX 版本组合仍未验收。[IBM 官方兼容说明](https://www.ibm.com/support/pages/compatibility-matlab)。

HiGHS 为开放许可路线；现有 SciPy 1.13.1 `milp` 公共签名没有 `x0` 或回调入口，不能保留本轮完整初解及观测协议。不能用其私有包装器臆造热启动，也不能临时丢弃连续初解。独立 highspy 文档提供解和回调接口，适合作为备用，但本机不存在，具体版本、完整 start 接纳、精度及观测能力均待验证。本轮不安装它。[SciPy 1.13.1 API](https://docs.scipy.org/doc/scipy-1.13.1/reference/generated/scipy.optimize.milp.html)、[HiGHS 官方许可与项目说明](https://ergo-code.github.io/HiGHS/stable/)、[HiGHS 回调接口](https://ergo-code.github.io/HiGHS/dev/callbacks/)。

首选理由：Gurobi Python 的矩阵输入、矩阵回读、完整 Start 与原生 MIP 日志/回调，直接对应本任务接口和证据要求；**没有本机性能证据，不能断言它更快或必然找到节能方案。** CPLEX 同样可行但目前也没有环境/授权优势，不同时准备第三套执行器。

## 2. 保存矩阵与无损传输

来源为历史 `C_noheur/original_zero_based.mat` 与 `C_noheur/matlab/request_000001.mat`。`C_noheur` 是历史文件身份；新求解器不会继承同名 MATLAB 参数。没有调用构模器、转换生成器或评价器。

| 项目 | 原矩阵 | 互补门控保存矩阵 |
|---|---:|---:|
| 变量 | 16919 | 23780 |
| 整数变量 | 1125 | 1125 |
| 连续变量 | 15794 | 22655 |
| 不等式 / 等式 | 94958 / 0 | 94958 / 6860 |
| 总非零元素 | 990904 | 1004625 |
| 整数边界 | 全部 [0,1] | 全部 [0,1] |
| 变量边界 | 全部有限 | 全部有限 |

已有精确投影证书的九项检查均为 true，涵盖逆代换、整数调度/连续松弛投影、目标、界与初解扩展。本轮只核对已保存证书及绑定文件，**没有重新生成证明**。[逐数组哈希、回读及历史准入](evidence/saved_transport_audit.json)、[全部数组尺度](evidence/saved_matrix_inventory.json)、[历史冻结文件复核](evidence/history_integrity.json)。

两个矩阵的整数索引集合一致；转换矩阵前 16919 维 x0、c 与原矩阵逐位一致，新增目标系数为零。原始 `intcon` 显式按 0-based 读取，MATLAB request 显式按 1-based 读取，转换后规范为 0-based；不根据最小索引猜测。原列 ID 从 0 到 n−1，禁止变量重排。

`src/contract.py` 直接接入 `c,A,b,Aeq,beq,lb,ub,intcon,x0`，固定最小化和常数项 +0。数组必须原生 binary64；拒绝 float32 隐式升级、NaN、非法边界、重复整数列、重复稀疏坐标及显式稀疏零。只规范稀疏坐标排序和字节序，不合并重复坐标、不舍入系数、不删行。行列号、形状、全部系数位模式、右端、上下界、目标、完整 x0 和列身份分别哈希。无穷界只允许 `lb=-inf/ub=+inf`，不替换成大数；当前 R1 无此界，但微型控制用例覆盖了它。Gurobi 对绝对值达到 1e20 的对应变量界按无穷处理，真实接线必须拒绝把这样的有限界当作原界保真；本 R1 界的绝对值最大为 55，不触及此门槛。[官方变量界语义](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html)。

离线读两个保存矩阵并经 FakeBackend 深复制回读，用时 **1.588 秒**，全部哈希一致。它不是 Gurobi/CPLEX 对象，不能证明真实 API 保真，更不是求解时间估计。真实后端以后必须在原生 presolve/optimize 前完整回读矩阵、sense、RHS、目标、边界、整数域及完整 start；若 API 忽略小系数、改变有限界或丢弃初解分量，则阻断调用，不靠删改模型通过。

原/新矩阵 A 最小非零系数约 1.2499e−8，不触发 Gurobi 文档所述 1e−13 以下矩阵系数归零门槛；但原矩阵 RHS 最小非零约 1.3973e−63，新矩阵也必须按保存值核对。这个区别不支持“模型已数值稳定”的结论。区间窄、消去误差和求解器内部变换风险仍在。[Gurobi 数值说明](https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/tolerances_scaling.html)。

历史 x0 的最大不等式浮点残差分别约 1.4211e−14 / 5.6058e−15，按历史 1e−9 行容差、1e−6 整数容差通过，**不是本 x0 的严格有理可行证明**。历史精确可行见证也不能自动替代此处保存 x0。完整 Start 的提交、读回、原生接纳分三个状态；原生未明确接纳时记 UNKNOWN/REJECTED，不冒充已接纳，不改用整数-only、不手工补齐或修复调度。[Gurobi Start 接口说明](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#start)。

以后 Gurobi 接线的指定映射：按原列序创建变量，显式 `lb/ub/obj`；intcon 标整数，其余连续；两块稀疏矩阵分别以 `<=` 和 `=` 加入；`ModelSense=1, ObjCon=0`；完整 `Start=x0`。通过 `getA` 与变量/行属性重建同一传输包核对。使用内存 double/稀疏 API，不经文本 MPS、LP、MST 往返替代逐位验证。[Gurobi 矩阵 API](https://docs.gurobi.com/projects/optimizer/en/current/reference/python/model.html#Model.addMConstr)。**这些是真实后端的接口要求，当前没有调用上述 API。**

## 3. 控制验证与边界

[测试回执](evidence/control_results.json)：31 项测试全部通过，含子用例。覆盖逐位/行列/nnz/目标/整数索引漂移、极小 RHS、signed zero、无穷界、部分初解、启动缓慢及配额边界、规模授权不足、超时但有候选、空向量、矩阵/合法性拒绝、双场景 SAFE 未知、共同调度重返、精确区间严格比较、迟到回执/归档、下界冲突、身份漂移和清理异常。

模拟器只接受 `SIMULATION_ONLY`，拒绝真实回执；`native_execution` 无论传入什么批准标志均抛错。模拟 SAFE/身份标志仅用于控制反事实，不替代实际数值、调度与电热验证。没有测到原生初始化、求解器内存/时间、实际许可容量或真正退出行为；这些明确留作阻断项，不能由 31 项测试推断已解决。

运行纯控制测试：`python src/test_contract.py <新的回执路径>`。离线保存数组审计：`python src/audit_saved.py --workspace <原工作区根> --output <新的JSON>`；输入来自[历史机制实验归档](../chapter3_mechanism_trials_20261112/README.md)，缺失时停止，不重构。`python src/readonly_inventory.py --workspace <原工作区根> --output <新的目录>` 复核目录、注册表与数组尺度；`python src/capture_metadata.py <新的JSON>` 复核两套 Python 与 MATLAB 文件接口。环境脚本仅适用于本 Windows 路径配置。输出采用新建文件，拒绝覆盖已有回执。`release_manifest.json` 绑定候选计划、代码及证据；不含任何执行授权。

## 4. 下一次 C 诊断候选与准入决定

[候选计划](candidate_plan.json) **execution_authorized=false、ready_to_request=false**。本轮没有批准模板、科研 claim 或原生执行回路。计划是可审查的预案，环境和真实后端未具备，不能直接凭此计划启动。

推荐唯一下一步：**先补齐一个本机 Gurobi Python 环境及覆盖完整模型的合法许可证明，再完成该后端的真实无求解矩阵回读、完整 start 接线和计时/清理验收，重新冻结后申请一次保存 C 诊断。** 安装及许可操作另需用户授权；无需再改数值表达或扫 MATLAB 参数。若无法提供完整 Gurobi 许可，则结束商业路线，以 highspy 为唯一备用另行准备；不同时试多个求解器，不借拆分规避限规模条款。

候选科学目标：在原模型及完整共同初解不变的条件下，观察替代求解器能否形成可验证搜索进展；严格成功必须为**原生返回不同调度、合法、原矩阵及转换矩阵数值准入、完整 AB/AC SAFE，且新完整能耗区间上界 < 共同初解完整能耗区间下界**。约 1.0848863713 J 只是历史显示值，严格比较用完整端点，不用四舍五入小数。原生 `c^T x`、原生上下界和 gap 独立记录，不能替代完整物理能耗或全局最优性证明。

600 秒方法总窗，550 秒响应截止；在读取、版本/许可/身份检查、加载、原生装载/回读、初解准入和完整初解评价之后，以统一函数 `N(t)=floor(min(540,max(0,600−t−10−50)))` 分配原生时限；N<30 则不调用。最多一次 optimize，零重试，不另起 LP、IIS、feasRelax、调参或预求解调用。所有原生 presolve、内部根 LP 和节点 LP 均属于这一次调用。

响应须在 550 前由控制端实际收到完整最终向量与状态；600 前完成验证、完整能耗评价、日志读取、哈希、证据归档及正常清理。最迟 680 秒的安全监护仅强制清理，不延长科学窗口；超 600 的清理成本照实入总墙钟，不能宣称满足 600 秒方法预算。最终向量最多一次完整评价，加初解一次，合计最多两次；不因它失败而改验回调中的另一个候选。回调向量只作过程记录，若不能完成验证则不获 SAFE/节能信用。

普通超时、无向量、start 未接纳、没有改善或证据不足均终止这一调用，不补跑。模型/源码/选项/证书漂移、回读不一致、计时不完整、未知影响范围、清理失败为完整性停止；原生界与同一 MILP 目标的已验证可行向量发生冲突时撤销相关界结论并停止，不能用物理能耗与 MILP 界直接相减制造冲突。迟到文件保留为未获信用原始材料，不补热评价。

预计成本：已测离线双矩阵读取/复制/哈希约 1.588 秒，**没有测量新引擎启动、许可握手、原生装载、presolve、回调或新候选验证成本**；不能用历史 MATLAB 启动时间代入 Gurobi。t=65.844 时仅作为配额算例得到 474 秒，t>510 时不进入求解。50 秒验证预留不保证足够，600 秒也不保证能取得候选。完整 A/B/C 的重构、转换和认证成本不能由本保存矩阵审计估算或免费排除。

## 5. 后续公平 A/B/C 与 Benders

A 为期限过滤基线；B 增加 Stage 选项支持传播；C 再增加联合频率状态剪枝。保留 12 次 Stage、66 原模式、5ms 网格、400ms 窗、全部物理参数、目标及评价精度；三组仅改变两级无损约简开关。

只有新求解器诊断取得有意义证据后，才申请正式三组对照：同求解器/版本/许可条件、线程、种子、数值表达、初始化规则、容差和总预算；独立进程、各自重新构模、初始化、转换/认证和完整评价，不共享科学缓存。动态配额函数相同，但各自准备成本自然占预算。普通超时或无候选不阻断其他组；正确性异常按已证明范围停止，未知范围/身份或清理异常停止全部受影响组；累计停止范围不能被后来正常组清空。每组最多一次原生调用，不能自动重试。

分别公布输入身份、根 LP 进入/完成、有限原生界及来源、节点、原生向量及调度身份、两矩阵准入、独立合法性、双场景 SAFE、不同调度、严格能耗改善与独立最优性证明。单次保存 C 诊断不是重新构模端到端性能结果；**不得拿历史 intlinprog A/B 与新求解器 C 宣称剪枝加速**。

Benders 分析见 [BENDERS.md](BENDERS.md)：固定全部 1125 个整数变量后为具有 22655 个连续变量、有限界的 LP；不等于已经解决数值困难或保证完全追索。已给出对偶最优性割/可行性割的符号和验证条件，说明共享 DVFS、跨场景部署及电热目标限制。本轮没有分解算法、LP 调用或割生成实验。

本轮新增 MATLAB 会话、MILP/LP 调用、完整 R1 重构、热评价、软件安装、许可变更均为 **0**。D280 的 O0/O1、根 LP/有限界/共同 SAFE 初解证据保留，O2 未建立，仍不能定位受保护内核瓶颈；替代求解器路线不将这个未知项改写为已解决。
