# 第三章 LaTeX 独立编译工程

本目录是第三章《多场景端侧推理的热约束节能联合规划》的**自包含阅读工程**。参考 [367cd6e 第三章正文写作意见](https://github.com/YBEMR/paper/commit/367cd6e370a423c5b526c20b4357c332b8fc9752) 和研究归档中的 P0/P1/P2、H02、C19、K.127 结果整理。正文以此前 `research/latex/chapter03_draft_20261024.tex` 为基础，补充了跨场景部署与同模式时序比较两幅说明图。

**请直接编辑本目录的 `chapter03.tex`。** 本目录的 `main.tex` 是独立编译入口，不修改 `research/latex/main.tex` 或既有的 `research/latex/chapter03.tex`。

## 文件组织

- `chapter03.tex`：第三章完整正文（模型、MILP、连续热评价与已有实验分析）。
- `main.tex`：XeLaTeX 编译入口、中文排版设置和本章参考文献；使用 `\setcounter{chapter}{2}`，使公式和图表编号从第3章开始。
- `build.bat`：Windows PowerShell/CMD 下双轮编译脚本，纯 ASCII，避免中文批处理编码报错。
- `build.sh`：Linux/macOS 下双轮编译脚本。
- `build/`：编译生成的 PDF、辅助文件和日志；仓库保留 `.gitkeep`，默认不跟踪衍生文件。
- `EVIDENCE.md`：本章主要实验数据及其仓库来源，不作为论文正文。

## 编译

需先安装 XeLaTeX、CTeX、amsmath、booktabs、TikZ、hyperref 等 TeX Live/MiKTeX 常见组件。中文字体优先尝试 Noto Serif CJK SC，不存在时回退至 Windows 宋体或 TeX Live 的 Fandol，**不附带任何字体文件**。

从本目录执行：

**Windows PowerShell：**
```powershell
.\build.bat
```

**Windows CMD：**
```bat
build.bat
```

**macOS/Linux：**
```bash
bash build.sh
```

输出路径：`build/chapter03_preview.pdf`。两轮编译用于更新目录、章节页码和交叉引用。如果编译失败，请查看 `build/chapter03_preview.compile.log`。

新提交的 PDF 也会由仓库的 **Chapter 3 PDF** GitHub Actions 工作流进行云端编译，并在相应运行记录的 Artifacts 中提供下载。修改 `chapter03.tex` 后只需再次运行构建脚本，不需要修改原第三章项目。

## 学术使用说明

- 本章面向 **已知有限请求的离线部署/运行计划**，不是运行时在线调度器。
- 默认控制策略为域空闲立即降至最低档 L（auto_low_immediate_v1），不沿用历史的 hold-last。
- 400 ms 是每场景能量评价窗口；300 s 是算法运行计算预算，不能混为一项实时期限。
- P0/P1/P2 在5种负载与3种条件下共有120次方法调用；实验是抽象仿真，不是实机测量。
- 现有证据支持热安全对候选接纳的作用；**MILP外层连续热反馈新增行数为0**，不能据此声称反馈节能。
- 第一、二章参考文献与第三章独立阅读稿的编号暂未统一；最终合入正式学校模板时再整合。

