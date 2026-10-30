# 构模瓶颈只读取证

`readonly_audit.py`只读取K.187/C01归档、比较源码hash及统计已保存的模式时长、进度和计时。仅使用标准库，不导入模型、算法、求解器或电热模块，不生成选项对象、矩阵、系数或候选。

复算须另用新目录，原取证结果不覆盖：

```text
F:/Anaconda3/python.exe -B research/chapter3_construction_audit/readonly_audit.py --output research/chapter3_construction_audit/<新目录>
```

C01原始工作目录不在检出中时，从已提交`raw_artifacts.tar.gz`仅读对应日志成员，并验证逐文件SHA；不解压执行。`readonly01/evidence.json`保存完整/部分计数区别、源码差异及原始计时；`formal_entry_diff.json`原样保存唯一已核入口的unified diff文本。

这些是既有运行的归因数据，不是新构模或性能测试。结论见上级《完整MILP构模瓶颈归因审查_K187与C01_20261030.md》，仅推荐一项后续路线，实施与实验均未启动。
