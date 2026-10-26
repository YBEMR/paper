# K192完整链小域预检

用户要求先核共同选择范围、完整热安全方案及穷举成本，再单独批准正式求解。本目录不修改生产算法，不运行优化器。

- `domain/core.py`：从K187原P0/R1输入取模式与起点子集，独立有理静态枚举，检查原C与HEFT结构构造。
- `domain/test_core.py`：13项纯检查，含生产选项逐项对照、SA计划回转及越界拒收。
- `precheck.py`：纯准备与一次性有界热预检分离；输入、单一见证和4个成本样本在评价前冻结。
- `test_precheck.py`：10项假回执检查，覆盖唯一消费、源码／输入／协议漂移、失败停止、共同截止、迟到SAFE与相对路径。
- `domain_tests.txt`、`lifecycle_tests.txt`：最终纯测试日志，全部通过；测试没有热或优化调用。

复跑纯检查（项目根目录，Python仅需标准库）：

```powershell
& 'F:/Anaconda3/python.exe' -B 'research/chapter3_experiments/small_domain_precheck/domain/test_core.py'
& 'F:/Anaconda3/python.exe' -B 'research/chapter3_experiments/small_domain_precheck/test_precheck.py'
```

实际结果保存在[small_full_chain_precheck02](../results/small_full_chain_precheck02/terminal.json)。01为纯准备路径异常，无执行声明或物理调用，保留不覆盖。02已消费唯一预检声明，禁止重复执行；原有初始化与样本不能用作后续方法的免费初解／缓存。

共同合法输入不等于算法覆盖一致：原C仍固定共享A部署并锁定部分设备／锚；HEFT／SA只作启发式访问。正式whole/C/HEFT/SA执行器身份与预算尚未验收，不可用旧批次入口直接启动。

只读重新核查现有凭据，不产生新评价：

```powershell
& 'F:/Anaconda3/python.exe' -B 'research/chapter3_experiments/results/small_full_chain_precheck02/analyze_readonly.py'
```

正式求解与完整1550条热覆盖均待另行批准。
