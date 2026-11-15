# 只读统计与报告复算

本目录为回放结束后新增的统计工具，不进入物理评价与计时源码冻结。下列命令在实验目录运行；source_cache按上级README准备，须保持33份冻结来源原字节。

```powershell
python -X utf8 analyze.py formal_v2
python -X utf8 reporting/verify_artifacts.py . source_cache
python -X utf8 reporting/build_report.py . --recommend-controlled-search
python -X utf8 reporting/finalize_report.py .
```

这些命令读取已有回执并重写派生统计/报告，不执行热传播、搜索或MILP。verify_artifacts同时从原来源复制8份相同输入/配置；它逐字节检查来源、候选载荷和最终48条源码身份。finalize_report应紧接build_report使用，避免重复追加末尾说明。

`--recommend-controlled-search`记录本轮人工审查后的工程建议，不是自动产生的新统计门槛，也不是搜索执行开关。NEXT_SEARCH_PROTOCOL.md为下一轮草案；本轮未实施。

正式性能只读formal_v2。pilot用于历史B准入；formal为v1缺陷诊断，不能合并或择优代替正式结果。全部计时数据按单机、每序列单次、固定臂序解释。
