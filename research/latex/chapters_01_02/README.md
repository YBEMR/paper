# 第一、二章独立 LaTeX 阅读工程

本工程提供可以反复编译的第一章 V3 和第二章 V4 阅读稿，不修改 `research/latex/main.tex` 的第三章主入口。`chapter01.tex`、`chapter02.tex` 分别是当前两章的正文。两章的参考文献暂按各自讨论稿编号，正式整合全文时需要统一整理。

## 文件与历史版本

- `main.tex`：第一、二章合并编译入口。
- `chapter01_only.tex`、`chapter02_only.tex`：单章编译入口。
- `preamble.tex`：中文字体、TikZ插图、公式编号及页面排版。
- `chapter01.tex`：第一章 V3。
- `chapter02.tex`：第二章 V4，按读者从第一章进入第二章的阅读顺序重新组织。
- `versions/chapter02_V1.tex`、`versions/chapter02_V2.tex`：旧版存档。
- `versions/chapter02_V3.tex`：未带行内批注的 V3 源码存档。
- `versions/chapter02_V3_user_comments.tex`：**2026-10-20 用户行内批注原样存档**。其括号内批注是审稿意见，不是可编译正文；请勿将此存档直接作为章节输入。
- `build.bat`、`build.sh`：Windows 和 macOS/Linux 编译脚本。
- `build/`：编译输出及中间文件；仓库中只跟踪目录占位文件，不跟踪生成的 PDF。

## 一键编译

安装 XeLaTeX（TeX Live / MiKTeX）、CTeX、TikZ、`amsmath` 和 `hyperref` 等常用宏包。若没有 Noto CJK 字体，`preamble.tex` 会尝试 Windows 字体或 TeX Live Fandol 字体；仓库不包含字体文件。

在 `research/latex/chapters_01_02/` 目录运行：

Windows PowerShell：
```powershell
.\build.bat
```

macOS / Linux：
```bash
bash build.sh
```

默认分别编译两轮并生成三份预览文件：
```text
build/chapters_01_02_preview.pdf   # 第一、二章合并
build/chapter01_preview.pdf        # 第一章
build/chapter02_preview.pdf        # 第二章
```

只重编第二章可运行 `.\build.bat chapter02`（PowerShell）或 `bash build.sh chapter02`。只编译合并版可运行 `.\build.bat combined` 或 `bash build.sh combined`。

后续修改 `chapter02.tex` 后，直接执行上述命令就会重新输出PDF。PDF 和 `.aux`、`.log` 等中间产物放在 `build/`，按仓库忽略规则不纳入版本控制。第三章工程完全不受影响。

原始讨论稿：[第一章V3](../../第一章绪论_讨论稿_V3.md)、[第二章V1](../../第二章相关理论与技术基础_讨论稿_V1.md)。