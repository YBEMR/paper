# 连续电热认证增量复用原型 ICR20261115

独立实验目录。冻结物理评价器及U07—U10候选来自`0de4d191966294dc673c21ed244616f1b5a6a85c`，前置诊断来自`b052cb004ae753e5d61b5b582561f9315739fde4`。不运行搜索、不更新第三/四章历史数据。

标准库实现；本轮环境为Windows 11、Anaconda Python 3.12.4。最终性能数据只取formal_v2/；formal/保留修复前21条完整回放及控制中断，不能混入最终加速。`CORRECTION.md`说明根停止缺口、复现、修复及完整重启；`REPORT.md`给最终结论。原始逐候选记录为receipts.jsonl，summary.json包含计费、计数、内存及源码身份；events.jsonl保留进程计时/退出码。

## 复现

先准备一个空的本地来源缓存。以下命令在本目录运行，目录名可自定；下载不启动科学计算。33个不可变源文件合计约332 MB，下载逐字节核对Git blob及SHA256。已有完整仓库可用独立的冻结检出作为`--cache`，注意Windows自动换行会导致字节核查失败；不要修改清单绕过核对。

```powershell
python -X utf8 fetch_sources.py --cache source_cache
python -X utf8 fetch_sources.py --cache source_cache --check-only
python -X utf8 test_scene.py --cache source_cache --out reproduced_tests/scene_correctness.json
python -X utf8 batch.py --cache source_cache --out reproduced/pilot --stage pilot
python -X utf8 analyze.py reproduced/pilot
```

准入必须先通过完整正确性和协议规定的耗时门槛。每条回放使用新进程、空缓存和300秒根预算；8条准入最多40分钟，另有启动/结束归档。目录已存在会拒绝覆盖，失败不自动重试。不要在计时过程中并行启动其他科学计算。

完整三臂正式回放仅在B准入与v2测试均成功后运行，48条×300秒。批处理检查准入、C及根停止回归。请在独立副本中复现以保留已交付原始测试。本轮没有后缀支配、跨根缓存或新调度算法。v1→v2因正确性修复重启一次，额外21条诊断回放和全部消耗保留，不是为提高收益重复择优。

```powershell
python -X utf8 test_scene.py --cache source_cache --out tests_v2/scene_correctness.json
python -X utf8 test_prefix.py --cache source_cache --out tests_v2/prefix_correctness_final.json
python -X utf8 test_root_stop.py --cache source_cache --out tests_v2/root_stop_final.json
python -X utf8 batch.py --cache source_cache --out reproduced/formal --stage formal
python -X utf8 analyze.py reproduced/formal
```

单条诊断命令如下；`--max-candidates`仅用于明确标记的正确性探针，不用于正式结果筛选：

```powershell
python -X utf8 replay.py --cache source_cache --call 01_U07__n24_HEFT_I1 --arm A --out one_run --seconds 300
```

## 输出与比较口径

共同完整SAFE前缀才能计算同工作量节省。总实际耗时、各臂多完成候选、UNRESOLVED和未开始候选另报。根内计费包括读入、合法性、缓存维护、认证与逐候选归档；进程启动/导入单列。日志压缩只移除温度trace正文，保留其精确摘要及全部能量/峰谷/积分/守恒字段；任何缓存续算均不使用这些压缩日志。

缓存的逻辑序列化字节不是实际占用；进程峰值内存包含源候选和记录。不同运行源候选量不同，跨根内存不可直接归因于缓存。单次配对计时不提供统计显著性或未来搜索节能收益。

## 已保留的异常

`tests/scene_correctness_attempt1.log`：预检断言误读原超限标志所在层级，后修正测试读取位置，原评价器不变。`tests/scene_correctness_attempt2.log`及对应JSON记录修正后15项通过。首次单候选A探针单列，不并入性能统计。全部历史预算未决标签保留在回放冻结清单和记录中。

v1根停止缺口不能忽略，见CORRECTION.md及tests_v2/root_stop_final.json。tests_v2/最终43项通过；versions/v1与versions/v2保存各次执行源码供核对，正式复现入口是本目录当前v2源码，不直接从快照目录运行。
