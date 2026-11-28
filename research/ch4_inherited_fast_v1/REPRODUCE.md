# 证据复核与复算

直接使用仓库中的逐单元、逐层、配对和时间账本即可审阅本轮结果。原始文件按任务流、重复、生成器、预算分目录。N 对应 B，O 对应 C。不同单元多次交付同一排程时，物理文件按内容合并，交付时间和认证次数仍逐次保留。

| 项目 | 方法 |
|---|---|
| 核查单个结果 | 从 `tables/cells.csv` 取 case、final_plan、final_mapping_sha256，在 `results/<case>/physical/index.json` 查该计划。按 archive 读取 tar 内的 `<plan>/plan` 与 `<plan>/certificate`，再按 blocks 列表顺序从索引指定的 tar 读取 `blocks/<hash>`。每项独立 zlib 解压。事件为原生小端 float64、每行 31 列，shape 与整块 SHA-256 在索引中。 |
| 原始时间 | `search.jsonl.gz`、`refine.jsonl.gz` 中的 t 相对同一单元起钟。完整 JSON 行记录一次交付；超过 cap 的结果排除。receipt 中 charged 是预算内墙钟，wall 包含监督进程回收时间。 |
| 候选与耗时 | `layers.jsonl.gz` 的 width 是本次尝试的宽度，parents 是实际展开的父节点数，slots 是配额名额，legal 是当前不同合法前缀数。predict 计实际传播调用。未结束层按最后一条快照取下界。逐单元账本分开校准计算、试点时序、普通时序、温度传播、认证和其他耗时。 |
| 核对与恢复 | Linux、Python 3.12.3、C++17 编译器、Git，Python 依赖版本见 verification.json。使用包含登记版本对象的本地克隆。下面的命令均在研究目录执行，FAST_SCRATCH 指向新的本机目录，不能指向其他会话的试验目录。 |
| 物理门槛 | verify.py 逐项校验输入散列、全部已交付证书及获选结果，核对完整事件区间、温度接续、期限和能耗界。归档校验不会调用调度器。summarize.py 可直接从 CSV 重新生成决策统计。 |

仅离线核对已归档数据：

```sh
export FAST_SCRATCH=/path/to/fresh-local-scratch
python3 prepare.py
python3 -B verify.py
python3 -B ledger.py
python3 -B summarize.py
```

重现计时实验时在独立工作副本、独立本地磁盘和空的原始结果目录执行，先准备同版本解释器及依赖。prepare.py 优先复用已有冻结输入，也可从 sources.json 所列 Git 对象取回文件；用冻结的编译参数构建调频内核。原跑使用 Linux 本地磁盘进行计时，结束后复制证据到归档目录。run.py 预热源算法中性模板，完成固定工作量对照，再运行正式单元。collect.py 打包按时交付的证据；随后运行上述离线核对。历史 60 秒结果直接读取第三章归档。完整复算会重新花费研究预算；审阅本轮报告只需离线核对。

```sh
python3 -Bu run.py
python3 -Bu collect.py
python3 -B verify.py
python3 -B ledger.py
python3 -B summarize.py
```
