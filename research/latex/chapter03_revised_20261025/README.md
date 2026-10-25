# 第三章（依旧稿结构修订）LaTeX 阅读工程

本目录依据用户提供的旧版第三章（3.1—3.8及原小节设置）进行局部修改，不采用此前独立稿重新安排的章节结构。**正文与章末推导、符号索引均可在此目录直接修改和编译**；仓库已有的 `research/latex/chapter03.tex` 和 `research/latex/chapter03_standalone/` 均不覆盖。

## 文件

- `chapter03.tex`：第三章正文，严格保留用户旧稿的8个一级小节和22个二级小节标题。
- `chapter03_formal_details.tex`：原章末数学补充推导，并同步修正空闲档位假设。
- `chapter03_symbols.tex`：符号索引，采用最低档 `L_h`，移除旧版末次工作点保持所需变量。
- `main.tex`：独立编译入口，设置第三章章节号并列出已用的五篇学术参考文献。
- `build.bat`：Windows PowerShell / CMD 双轮 XeLaTeX 编译脚本，脚本文字为纯ASCII。
- `build.sh`：Linux / macOS 双轮 XeLaTeX 编译脚本。
- `build/`：输出PDF、目录、日志的路径，Git不跟踪编译产物。
- `EVIDENCE.md`：与正文数值相对应的已归档材料定位，非论文正文。

## 编译

需要 **XeLaTeX** 和 TeX Live/MiKTeX 的 `ctex`、`amsmath`、`booktabs`、`tikz`、`hyperref` 等组件。中文字体优先用 Noto CJK；不具备时回退至 Windows 常见字体或 TeX Live Fandol。**不分发字体文件**。

在本目录中打开PowerShell：

```powershell
.\build.bat
```

在Linux/macOS终端：

```bash
bash build.sh
```

生成 `build/chapter03_revised.pdf`。如编译失败请查看 `build/chapter03_revised.compile.log`。原始LaTeX不需要先转Markdown。

## 修订范围和阅读重点

- **3.1—3.5**：保留旧稿的叙述链条、公式及小节顺序；仅更正正式模型使用的 `auto_low_immediate_v1` 空闲最低档策略，连带修改域工作点轨迹、基准功率和3.5.4的状态控制约束。CPU1/CPU2仍共享频率域，但可分占不同执行单元。
- **3.6**：保留旧稿“方法概述—连续热反馈的引入—具体求解流程”，修正安全检查及已完成研究所采用的数值证据口径。
- **3.7**：保持旧稿原四小节，补齐P0/P1/P2、同真实H的H02响应规划对照、C19同模式异时序数学见证、P0/P2同调度温度项、K.127热拒绝、120次正式方法调用和预算内质量/耗时分析。
- **3.8**：依据已观察到的模型作用和正式实验，重写章末小结及与第四章的衔接。

## 使用边界

这是**有完整编译结果的论文讨论稿**，并非新科学实验。正式实验仅涉及已知AB/AC两场景、三Stage链、抽象CPU/GPU/NPU平台、5ms启动网格、400ms评价窗口与每次300s离线方法预算。三批的MILP外层连续热反馈新增行数为0，不得称其已得到独立节能收益；已得到安全方案也不等于完整连续起点问题的全局最优证明。参考文献编号待与全文统一。
