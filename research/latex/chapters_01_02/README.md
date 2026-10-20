# 第一、二章独立 LaTeX 阅读工程

第一章 V3 与第二章 V2 的**可复编译源码**，和现有 `research/latex/main.tex` 第三章入口相互独立，不会覆盖已有章节。两章参考文献暂按各自讨论稿编号，正式整合时需要统一编号。

## 文件

- `main.tex`：第一、二章合并编译入口
- `chapter01.tex`、`chapter02.tex`：直接编辑的章节正文。第二章 V1/V2 保留于 `versions/`，V3 为当前版本；后者现为 **V2讨论稿**。
- `versions/chapter02_V1.tex`：上一版第二章的完整LaTeX备份。
- `preamble.tex`：字体及版式
- `chapter01_only.tex`、`chapter02_only.tex`：单章入口
- `build.sh`、`build.bat`：一键编译脚本
- `build/`：存放PDF、目录及LaTeX中间文件；仓库中仅跟踪 `.gitkeep`

## 编译

安装 **XeLaTeX**（TeX Live 或 MiKTeX）、`ctex`、`amsmath`、`hyperref`、`tikz`（PGF）等常用宏包。中文字体首选 Noto CJK，未安装时自动回退宋体/微软雅黑及 TeX Live Fandol 字体；不随仓库分发字体。

在此目录执行：

Windows PowerShell（在本工程目录中运行）：
```powershell
.\build.bat
```

Windows CMD：
```bat
build.bat
```

macOS / Linux：
```bash
bash build.sh
```

脚本默认分别进行两遍 XeLaTeX 编译，生成：

```
build/chapters_01_02_preview.pdf
build/chapter01_preview.pdf
build/chapter02_preview.pdf
```

PowerShell 只编译一章：`.\build.bat chapter01` 或 `.\build.bat chapter02`；只编译合并版：`.\build.bat combined`。Windows CMD 可以直接运行 `build.bat chapter01`；macOS/Linux 使用 `bash build.sh chapter01` 等。

不用脚本也可在该目录两次执行：
```bash
xelatex -interaction=nonstopmode -halt-on-error -jobname=chapters_01_02_preview -output-directory=build main.tex
```

**后续修改：** 保存 `chapter01.tex` 或 `chapter02.tex` → 运行 PowerShell 命令 `.\build.bat` 或 `bash build.sh` → 打开 `build/` 下的新PDF。整个构建流程只使用该子目录，不修改第三章项目。

Windows 脚本中的注释和提示使用纯 ASCII，避免不同系统代码页对 UTF-8 中文批处理文件的解析问题。

原仓库 `.gitignore` 不跟踪 PDF、`.aux`、`.log` 等编译产物。本工程延续该规则，`build/` 由 `.gitkeep` 保留目录，编译输出保存在本地，不需要额外提交。

原始讨论稿：[第一章 V3](../../第一章绪论_讨论稿_V3.md)、[第二章 V1（原始讨论稿）](../../第二章相关理论与技术基础_讨论稿_V1.md)。当前第二章 V3 侧重实时系统分类的自然引入、端侧应用例证与全章文字衔接，原目录、公式和示意图保持不变。

## 第二章 V2（2026-10-20）

本次按已讨论的七节结构重新撰写第二章，保留12个次小节；2.3.3标题为“面向深度学习推理的任务模型”，2.4.1为“功耗模型”。增补异构SoC、算子至计算阶段、A+B/A+C跨场景、DPM/DVFS、RC网络五幅TikZ示意图；正文包含19组编号公式。插图与公式均为LaTeX源码，不依赖外部图片文件。第二章参考文献暂采用章节独立编号，后续统一论文时再整合。若需回看V1，请打开`versions/chapter02_V1.tex`，不必回滚整个Git仓库。
