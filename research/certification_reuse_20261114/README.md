# 完整电热认证增量复用诊断（CRD20261114）

[结论报告](REPORT.md) · [数学/接口审查](INTERFACE_AUDIT.md) · [冻结口径](PROTOCOL.md) · [全部统计](results/summary.json)

只读分析YBEMR/paper@0de4d191966294dc673c21ed244616f1b5a6a85c的U07—U10归档。855次评价全部保留，不运行任何搜索/电热传播，不改冻结代码。建议独立原型优先复用整场景与同路径前缀；面板覆盖不是实测提速。

复算只需Python标准库（本轮Python3.12）。可选先下载80份固定来源，共约341 MB；数据已有时只读缓存，不重复下载：

```text
python download_archive.py --cache ../work/cert_reuse_sources
python analyze_archive.py --cache ../work/cert_reuse_sources --out results
python verify_archive.py --cache ../work/cert_reuse_sources
```

下载器仅取固定commit并核对Git blob和SHA256；不执行来源代码。分析直接读取原legality功率段与trace，约16秒静态统计，绝不导入冻结评价器。复算的analysis_wall_s随环境变化，物理身份、配对顺序和统计量应相同。`scene_pairs.csv`两种reference是同一批候选的两个视角，不能混合当成独立样本。

包内只含本轮报告、脚本、派生CSV和来源身份，不重复复制约341 MB历史原始文件。四根同族、每臂一次，结论不外推所有DAG或紧热实例。后续原型与科学回放须另行授权，本轮未启动。
