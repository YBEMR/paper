# 来源与检索边界

日期：2026-11-14，Asia/Shanghai。问题限定为 B 的同平台参数、字段语义和效应可辨性，不扩展新方向文献筛选。

1. 继承上一阶段的 Loudaros 2025、BatchDVFS 2022、IceEdge 2026 与 NVIDIA 线索；按作者与仓库检索定位 `iloudaros/LoudVA`，README Publications 明确链接 DOI 10.1145/3721889.3721925。GitHub recursive tree 1663 条目、未截断；选择规则见 AUDIT_PROTOCOL.md。不是全库所有日志复算。
2. 读取 LoudVA 配置、采集、能量生成和汇总代码；定位 AGX Representative 表与一个完整场景的9种调度器日志。固定 SHA 2b4b15efa5231d445b85d500ea5ef51d381a64c3。附加读取 configure_triton 与 sync_time 脚本用于解释语义/同步边界。
3. BatchDVFS 固定 SHA f05286df4b228ac18d5e83c0e3d8a153d5a5c5fc。查询词包括 `Coordinated Batching and DVFS P40`、`Coordinated Batching and DVFS pdf arxiv`。作者站点 PDF 搜索索引提供 §4.1 硬件平台原文片段；WPI 直接下载 HTTP403、KTH 入口未成功读取，故只标“索引片段”，不标全文读完。主结果 ZIP 完整读取；未读 Clipper、DVFS 对照 ZIP。
4. NVIDIA Triton 官方 Inference Load Modes 的 concurrency 定义核查；其当前网页只作概念说明，不证明原作者具体软件版本。Jetson Linux R35.6.0 官方 AGX/NX 功耗文档核查电源轨、活动/挂起状态区别，不能替代部署日志。
5. Shalavi 等 Accurate Calibration of Power Measurements from Internal Power Sensors on NVIDIA Jetson Devices，arXiv:2306.13107v1：HTML 原文定向阅读实验平台、校准表 I；不含 AGX Xavier，不移植其系数或误差。
6. IceEdge 沿用前一阶段本地作者稿与表2核查；本轮核查作者主页和公开仓库检索未定位可验证的对应原始日志。只表示本次范围内未找到，不声称作者没有工件。

关键链接在 REPORT.md 中；仓库文件的固定路径、SHA-256 与 Git blob SHA 在两个 manifest 中。LoudVA 全文论文仍未取得；新增工件审计补充了此前“未读结果”的状态，但不覆盖旧报告和旧阅读记录。

判断类型：源代码/数据字段为事实；“无法直接校准 B”是基于这些事实的审计判断；下一步参数区间分析为助手建议，未声称用户已选定最终论文主线。
