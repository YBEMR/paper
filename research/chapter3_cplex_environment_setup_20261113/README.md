# D281 环境补充：学术版 CPLEX Python 接入完成

2026-11-13。用户提供 `F:/CPLEX/CPLEX_Studio222`，明确说明来自 IBM 学术授权，并授权“直接帮我弄好”。本次只安装接口、绑定现有运行时和进行无求解的微型接口核验。D281 原报告及 Gurobi 候选不修改，不复用任何科研求解批准。

**环境接入通过。** 当前 `F:/Anaconda3/python.exe`（Python 3.12.4）已安装 `cplex==22.2.0.0`、`docplex==2.32.264`；原生引擎报告 22.2.0.0。Windows 加载器确认 Python 实际加载 `F:/Anaconda3/Lib/site-packages/cplex/_internal/cplex2220.dll`，其 SHA256 与现有学术来源 Developer Edition Studio 的 DLL 相同：

`7ae98eaf3bc4935718cdd702152841f48704187145c47990a060359e2566d0ee`。

默认 PyPI 社区版 DLL 的旧 SHA256 为 `8d742ace170d1f75f22c1d746b494c647d4148b43c8217446e11f9e89f7c6538`，绑定后已不再加载它。用户的学术资格说明、安装产品标签与运行时来源分别记录；未读取密钥或许可文件内容，未变更许可文件，未查询账户。**没有通过大规模求解测试授权容量，也没有运行完整 R1。**

## 实际配置

```powershell
& "F:\Anaconda3\python.exe" -m pip install --disable-pip-version-check "cplex==22.2.0.0" "docplex==2.32.264"
& "F:\Anaconda3\Scripts\docplex.exe" config --upgrade "F:\CPLEX\CPLEX_Studio222"
```

安装使用已有 pip 镜像配置，不改系统 PATH、不更换 Python、不升级 NumPy/SciPy。DOcplex 的官方配置命令将 Studio 的 CPLEX DLL 复制到该 Python 的 `_internal` 与 `Scripts`，并将配套 CP Optimizer 可执行文件复制到 Scripts；该官方工具重复列出 `_internal` 目标一次，最终文件身份一致。没有运行 CP Optimizer。DOcplex 只用于运行时配置，后续模型仍从原矩阵通过低层 `cplex` API 接入，不改写为 DOcplex 或 YALMIP 模型。

本机安装说明 `F:/CPLEX/CPLEX_Studio222/cplex/readmeWindows.html` 的 Python interfaces 节明确给出上述安装/绑定方式。版本匹配依据为 Studio 头文件 `CPX_VERSION=22020000` 和[IBM 发布的 Python 3.12 Windows 安装包](https://pypi.org/project/cplex/22.2.0.0/)；[DOcplex 官方包说明](https://pypi.org/project/docplex/2.32.264/)说明配置工具及版本。

## 验证结果

[verification_v2.json](verification_v2.json) 的 **20/20** 检查通过。`verify_no_solve.py` 只创建一个 4 列、3 行的合成模型，未读取或构建 R1；核验下列内容：

- 包版本、原生版本、学术来源 DLL 哈希及实际加载路径；
- 列顺序、1-based 到 0-based 整数索引、目标方向及常数；
- 不等式/等式、稀疏坐标与全部 binary64 系数、约 1e−63 的 RHS；
- 变量类型、有限界及 CPLEX 无穷界哨兵；
- 全部 4 维 MIP start 的原样存入/读回、资源句柄关闭。

**MIP start 存储通过不等于原生搜索接纳。** 没有执行 optimize，因此初解接纳、根 LP、节点搜索、数值稳定性、完整模型性能、SAFE 与节能均未测试。脚本将 solve、populate、feasopt、调参及冲突分析入口替换为拒绝函数，避免该微型检查意外进入算法。

第一次微型检查的 [verification.json](verification.json) 保留：19/20 通过，唯一失败是 psutil 返回 `\Anaconda3\...`，缺少 F: 盘符，导致路径身份比较失败。修正观测方式为 Windows `GetModuleHandleW/GetModuleFileNameW` 后重做微型检查通过，未修改任何矩阵、容差、搜索设置。两次均正常释放句柄；这两次是有限接口控制检查，**MILP/LP/完整 R1/热评价调用均为 0**。官方绑定工具另在子进程导入包读取版本，没有调用求解。

## 对下一步的影响

以实际环境为依据，后续首选改为现有 **CPLEX 22.2 Python**，不再优先安装 Gurobi。此次解决了“没有后端安装/接口”和“Python 仍绑定社区版运行时”的环境阻断。

**仍不能直接执行旧 Gurobi 冻结候选或申请完整 R1 科研调用。** 下一步范围应限于 CPLEX 的保存 C 无损适配、原生选项/观测/完整初解协议与独立计时清理验收，再生成新的 CPLEX 冻结方案；完整矩阵回读、运行中的初解接纳和实际求解收益未由本次四列检查证明。已有完整模型、两级约简、物理精度和“不同调度＋完整 SAFE＋严格能耗改善”的目标保持不变。
