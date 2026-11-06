# R2023b 单 AB 初解空返回诊断

2026-11-06。**同一 29.453 秒原生时限下，等价改写矩阵后，`intlinprog` 从空返回变为返回与原 `x0` 逐字节相同的向量。** 改写只将 4,346 对严格相反的不等式移入 `Aeq`。返回向量通过原矩阵准入和原场景完整 400 ms 电热复核，能耗仍为原初解的 **1.046120846870405671 J**。这是求解器交付修复，优化增益为零。

本次对象是 β=1.3、AB/AC 共 12 次 Stage 执行的原始输入，只取 AB 条件子模型的六次执行。共享映射为 A.pre=CPU1、A.main=NPU0、A.post=CPU1。固定交接包、AB 审计、计时取消对照与 MATLAB worker 源码见下列证据。  
[固定交接](https://github.com/YBEMR/paper/blob/23ebc780e8374ded66651ce25423b7a9b8933af1/research/chapter3_experiments/results/shared_mapping_handoff_20261106/HANDOFF_ZH.md) · [AB 审计](https://github.com/YBEMR/paper/blob/23ebc780e8374ded66651ce25423b7a9b8933af1/research/chapter3_experiments/results/shared_mapping_handoff_20261106/evidence/ab_probe/RESULT_AUDIT.json) · [取消对照](https://github.com/YBEMR/paper/blob/23ebc780e8374ded66651ce25423b7a9b8933af1/research/chapter3_experiments/results/shared_mapping_handoff_20261106/evidence/CONTROL_RESULT.json) · [原调用](https://github.com/YBEMR/paper/blob/23ebc780e8374ded66651ce25423b7a9b8933af1/research/chapter3_experiments/results/shared_mapping_handoff_20261106/sources/solve_model_probe.m.txt#L163)

## 输入身份

在原 Windows 任务目录找回请求 MAT 与原生输出 MAT，两份字节哈希与交接清单一致。原任务冻结的 440 个文件逐一核对无漂移。对 MAT 重新读取并按原约定检查，`initialPoint` 与请求中的 `x0` 位级一致，原生返回的 `x/fval` 均为空。按冻结科学输入重新导出 AB 模型得到相同 payload 哈希，按桥接规则序列化后，九组数组与原 MAT 对应数组一致。项目 payload 和 MAT 文件字节采用不同哈希口径。  
[输入检查](evidence/input_identity.json) · [九组数组比对](evidence/matrix_identity.json)

| 对象 | SHA-256 |
|---|---|
| 原配置 JSON | `132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2` |
| 原完整实例 JSON | `01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89` |
| AB 项目模型 payload | `affa9501fc75d8ee6ccc314b3b3043dce88a704f0c63d50691df9ebda7d27001` |
| 原请求 MAT | `dd8ce3fe40d8d641d755e211eea0649642fcc689d4a0b4a6547c7b65686867d1` |
| 原生输出 MAT | `2f2a7cbdd57585b8c25877420c954910733c81f2b0c40d945015bc7920edbc72` |
| `x0` 数组身份 | `47d009fd41f8d0281ee347709c8d9a346a4f20ffab3af7c73025986fa5b61333` |

原 AB 有 8,738 变量、654 个 `intcon`、40,078 条不等式和 414,681 个稀疏非零项。MATLAB 23.2.0.2365128 与 Optimization Toolbox 23.2 实际完成全部调用。原 `x0` 最大不等式残差为 `2.13e-14`，等式、界及整数残差均为零。源快照和原 MATLAB 调用均确认初解是第九参数，选项是第十参数。

## 原生对照与定位

每臂 `MaxTime=29.45299999997951` 秒。LP 用 R2023b `linprog` 双单纯形、关闭 LP 预处理、原约束容差 `1e-9`、最优性容差 `1e-7`。固定臂只令 654 个整数坐标的下界和上界等于原初解值，放松臂保留原目标、行和界。三项 MILP 保留原探针参数（`MaxFeasiblePoints=1`、双单纯形根 LP、两项预处理设置 `none`、整数容差 `1e-6`、零 gap 容差），使用独立脚本直接调用原生函数。观测回调只记录内存数据，返回 `false`，无文件发布或取消逻辑。  
[LP 记录](evidence/lp01/) · [MILP 记录](evidence/milp01/) · [R2023b linprog 选项](https://www.mathworks.com/help/releases/R2023b/optim/ug/linprog.html) · [R2023b intlinprog 选项](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html)

| 诊断臂 | 调用壁钟 / 秒 | 状态 | 原矩阵结果 |
|---|---:|---|---|
| 固定整数 LP | 3.664 | exit=1，5,546 次迭代 | 8,738 维，目标 1.046120846870399 J，不等式残差 2.84e-14，其余为零 |
| 自由 LP 松弛 | 29.698 | exit=0，19,924 次迭代，MaxTime | `x/fval` 空，无法测返回点残差 |
| 原 MILP + x0 + 观测 | 30.375 | exit=0，MaxTime | `x/fval` 空，只有 init/done |
| 原 MILP + x0，关闭回调 | 29.654 | exit=0，MaxTime | `x/fval` 空 |
| 原 MILP 无 x0 + 观测 | 29.673 | exit=0，MaxTime | `x/fval` 空，只有 init/done |
| 等价等式 MILP + x0 + 观测 | 30.084 | exit=2，MaxTime | 返回原 x0，原行残差 2.13e-14，其余为零 |

**证据指向根 LP 阶段的时限瓶颈。** 原矩阵即使取消所有整数约束，双单纯形也耗尽同一时限。原 MILP 没有报告根 LP 完成。只换等价表示后，27.827 秒出现明确的 `rootlp` 事件，松弛目标约 0.724038468 J，随后原初解成为可返回的整数解。这表明当前 AB 表示和预算下，向量已满足原行并不足以确保求解器在早停前交付它。独立 LP 与求解器内部根 LP 的实现可能不同，原 MATLAB 内部登记和计数路径位于受保护代码中，无法由日志确定具体的初解登记指令、是否曾暂存该点，或把原调用每一秒都归到某个内部阶段。  
[原 LP 松弛](evidence/lp01/free_lp_relaxation.json) · [改写后根 LP 事件](evidence/repair01/exact_equality_repair.json) · [R2023b 算法阶段](https://www.mathworks.com/help/releases/R2023b/optim/ug/mixed-integer-linear-programming-algorithms.html)

普通场景计时取消、桥接丢弃和自定义回调都已排除为本例空返回的必要条件。即使完全省略 `x0`，`done.numfeaspoints` 也为 1，且该事件无向量、目标为空，最终 `output.numfeaspoints=0`。这排除了用该计数证明原初解已被接纳的解释。固定整数 LP 的原行可行解也排除了“当前整数安排无法补成连续可行点”。原自由 LP 没有报数值失败或不可行，现有证据只支持表示影响限时路径，无法把矩阵系数跨度直接定为条件数或某个 MathWorks 缺陷。  
[无 x0 对照](evidence/milp01/no_x0_callback.json) · [关闭回调对照](evidence/milp01/x0_no_callback.json) · [R2023b 回调字段](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog-output-functions-and-plot-functions.html)

## 修复差异与复核

将 `aᵀx ≤ b` 和 `−aᵀx ≤ −b` 改写为 `aᵀx = b`，逐对按保存的 binary64 系数和右端精确匹配。原 40,078 条不等式变为 31,386 条不等式和 4,346 条等式。逐行证书覆盖全部原行，保留目标、变量、上下界、`intcon`、`x0` 和所有其他约束。近似反向行、非零宽度热区间及条件约束仍按原式处理。  
[逐行等价证书](evidence/equivalence_certificate.json)

改写后原生状态为限时且有整数可行点，最终返回向量与原 `x0` 的最大逐元素差为零，MAT 字节比对一致。使用原模型解码和验证六次 Stage 安排，按原完整输入、原共享映射和原精度重做 AB 电热评价。覆盖 0.4 秒全窗口，峰温约 53.127°C，零违规，完整能耗区间上界 1.046120846870405671 J。该证据限于本 AB，原生求解器未给出全局最优证明。  
[完整电热后验](evidence/repair_post.json) · [结果及原始文件哈希](evidence/manifest.json)

## 原 Windows 最小复现

从仓库根目录运行，使用安装 SciPy 和 psutil 的原项目 Python 及 MATLAB R2023b。将原任务 `inputs/input_config.json`、`inputs/input_instance.json` 和固定交接中的 `protocol/BASELINE_MANIFEST.json` 放入同一只读输入目录。也可复用本轮保存的 `tmp/ab_diag_20261106` 中这三个文件。原请求和返回 MAT 位于原任务的 `ab_x0_probe_20261106T113559Z/runs/native_once/condition/matlab/`。三阶段分别有 120、155、145 秒进程保护上限，包含启动和退出。每臂单次调用，输出目录必须是新目录。  
[冻结来源清单](https://github.com/YBEMR/paper/blob/23ebc780e8374ded66651ce25423b7a9b8933af1/research/chapter3_experiments/results/shared_mapping_handoff_20261106/protocol/BASELINE_MANIFEST.json) · [诊断入口](run_ab.py) · [MATLAB 调用](diagnose_ab.m)

```powershell
$entry = 'research/chapter3_experiments/ab_native_diagnostic/run_ab.py'
$python = 'F:/Anaconda3/python.exe'
$matlab = 'F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe'
$inputs = 'tmp/ab_diag_20261106'
$historical = '<原任务绝对路径>/runs/native_once/condition/matlab'
$new = 'tmp/ab_diag_reproduce01'
& $python -B $entry prepare --source $inputs --out "$new/original" --original-mat "$historical/request_000001.mat" --native-mat "$historical/request_000001.native.mat"
& $python -B $entry run --phase lp --prepared "$new/original" --out "$new/lp" --matlab $matlab
& $python -B $entry run --phase milp --prepared "$new/original" --out "$new/milp" --matlab $matlab
& $python -B $entry prepare-repair --prepared "$new/original" --out "$new/derived"
& $python -B $entry run --phase repair --prepared "$new/original" --repair-dir "$new/derived" --out "$new/repair" --matlab $matlab
& $python -B $entry post --source $inputs --result "$new/repair/exact_equality_repair.mat" --out "$new/repair_post.json"
```

本轮共 2 次 LP、3 次 MILP 对照、1 次等价表示 MILP、1 次返回向量的完整 AB 后验。原始 MAT 发现前曾尝试从冻结输入重建，首次在初解哈希口径检查处停止，未启动原生求解。正式诊断使用经哈希校验的原始请求 MAT。等价修复已通过同限时验证，因此结束本轮诊断。历史实验结果及第三章正式模型文件保留原样。
