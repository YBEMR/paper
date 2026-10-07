# 50号证据快照

日期2026-09-25。只读论文、仓库代码和静态模型；未运行模型、delegate、Android构建或MATLAB。

## 版本与来源

- 论文归档：[v0.0.0](https://github.com/mrsnu/band/releases/tag/v0.0.0)，提交`f5e1655b3ace9417f1fbb70d5adc7867987b197d`。`archive_tree.json`保存递归API树（6976项，未截断），`archive/`为定向选读文件，不是完整checkout。
- 补充快照：提交`8600d4960ccb6f121221f6d252da8dbef2db160b`，`current_commit.json`和`current_tree.json`保存提交及目录（330项，未截断），`current/`为选读文件及Lite0模型。
- `source_manifest.json`逐文件记录原始URL、提交、SHA256、Git blob和目录匹配检查；目录元数据不是性能数据。
- `lite0_metadata.json`为静态FlatBuffer字段读取结果：只读Model、SubGraph和Tensor表；依据schema字段偏移读取输入形状、类型及量化参数，未调用推理runtime。Git blob检查独立确认文件与当前固定提交一致。

## 阅读范围

论文使用已有`papers/2022_Jeong_Band.pdf`和`research/extracted/2022_Jeong_Band.txt`；原页复用`research/evidence_20260923/band_crown/band_p5.png`、`band_p9.png`、`research/evidence_20260924/result_scope/band-11.png`，不重复存储。

归档重点：README、config、interpreter、worker、cpu、profiling util、benchmark配置、workspace.bzl直接模型链接。当前版仅补查模型文件、model_analyzer、model_executor、latency_estimator、benchmark文档和配置，不能冒称论文代码／数据。

## 访问限制

- GitHub release网页可读，但Assets动态列表加载失败；没有认定两项资产具体内容或排除附件。
- 部分web raw／blob读取失败，转用GitHub API和Python原始文件读取，已取得文件均保留并可核对blob。
- 并行下载中当前Lite0与schema已落盘；MobileNetV1 quant压缩包未完成，停止等待。随后curl返回本机TLS错误`SEC_E_NO_CREDENTIALS`。未保留未经校验的模型压缩包，未宣称下载成功。
- [官方quant包](https://storage.googleapis.com/download.tensorflow.org/models/mobilenet_v1_2018_08_02/mobilenet_v1_1.0_224_quant.tgz)的预期SHA来自归档workspace.bzl，不是本次实测哈希。即使包可得，也缺图6绑定及Pixel 4分区记录。
- 在已取得树及选读文件中没有找到目标模型的匹配profile；不据此声称作者没有任何私有数据或从未公开其他工件。

## 完整性

`protected_before.json`是开始时记录的旧源码／冻结设计／41–49号报告哈希，`audit.json`记录结束时逐项复核与本地链接检查。它们是文件完整性校验，不是新研究实验。50号正文、BRIEF和03证据记录是本轮新增／同步交付。
