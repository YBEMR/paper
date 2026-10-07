# 51号证据索引

日期2026-09-25；用途仅模型身份与分区证据核查。未构建或运行推理／MATLAB。

- `release_v0.json`、`releases.json`：作者公开release API；v0 assets为空，v1列编译库。未下载或执行库。
- `branches.json`、`branches_p2.json`：118分支名及提交。只进一步检查benchmark-configs、print-fallback-ops、mobisys22三个直接相关分支树；不是所有分支内容审查。
- `issues.json`、`issues_p2.json`至`issues_p4.json`：319条唯一issue／PR的标题与正文检索，不等于逐条全文评论核查。
- `tree_benchmark-configs.json`、`tree_print-fallback-ops.json`、`tree_mobisys22.json`：定向目录树，均未截断。benchmark-configs固定caff495b3406e78a0fe03a98151d4107d1c16887；print-fallback-ops固定4ecc1cd9efc3923c99c0f940080ebbeda8860113；mobisys22即50号归档f5e1655b3ace9417f1fbb70d5adc7867987b197d。
- `benchmark_configs/`：8个原始JSON配置；是输入示例，不是测量表。
- [PR #226](https://github.com/mrsnu/band/pull/226)：`pr226.json`、`pr226_comments.json`保存正文、元数据及2条评论。作者报告分区测试，不当成完整推理实测。
- `tree_pr226.json`：头提交5af78b1644f77069b5f128bcc14f896cc65d8f5f，16459项未截断。Lite0模型blob与50号本地文件一致，避免重复存储二进制。
- `pr226_source/`：该头提交实际读取的测试配置、分区测试和common.h；猜测的model_executor.cc路径404，未引用不存在的文件。源码的线程数是固定测试配置，不是性能测量。
- `stage_graph_static.json`：只读50号现有模型，用FlatBuffer表读取算子输入／输出，按作者四组边界计算张量跨段边。记录唯一生产者、拓扑先后、算子覆盖、常量与输入边界；未执行算子或测时长。
- `fetch_log*.json`：来源URL、取得范围及异常；`source_manifest.json`补充本轮源文件哈希、Git blob匹配和API快照摘要。
- `protected_before.json`、`audit.json`：旧源码、冻结设计、41–50号报告共80份的前后完整性检查；无新研究案例。

网页工具对部分GitHub API／PR入口返回不可访问或cache miss，之后通过公开API取得正文；没有据网页失败否定材料存在。初次本地JSON读取使用GBK失败，改为显式UTF-8后完成；未写入旧文件。全部工作在本地和公开只读入口完成，未发送作者消息。
