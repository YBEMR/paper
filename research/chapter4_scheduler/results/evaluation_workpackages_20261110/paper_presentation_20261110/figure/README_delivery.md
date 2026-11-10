最终论文图：AB_NPU0_startup_and_periodic_v3.png、.svg、.pdf；中文图注及技术说明见caption_v3.md，LaTeX图注见caption_v3.tex。

数值计划SHA256：3bc8d6e8ff5844c91c2a611a488e9e3760e0071a8328c0a60701bdb150c71982。最终v3、历史v1/v2及排版初稿均保留；冻结科学代码未改。

原核批次：2026-11-10T04:05:36.976831+00:00至2026-11-10T04:07:54.486932+00:00；内部批次137.510116749 s，命令包装137.57188202199995 s。

实际命令：/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python -B research/chapter4_scheduler/results/evaluation_workpackages_20261110/paper_presentation_20261110/figure/run_figure_points.py --approved-plan-sha256 3bc8d6e8ff5844c91c2a611a488e9e3760e0071a8328c0a60701bdb150c71982；工作目录/workspace/paper。

恰10次原核调用，4次启动全历史和6次稳态盒上下传播，均完整；8 SAFE、2 THERMAL_VIOLATION、0失败/重试；0调度搜索。原C 242次计数不变。

原核逐时刻四节点向量6396个、全节点CSV行25584条、最终AB/NPU0显示点6254个。拆段与来源等630项自动断言通过；另以哈希核对原C清单304项未变；历史v1清单仅render_stdout.log在快照后的原程序收尾打印不同，科学数据、图与代码均未变。

所有新增核轨迹四节点的连续最小/最大包围均在20..100°C；P75/P80越限后的3s延续只是未实施热保护/关停的固定模型诊断。

两个新增更早点见证为P75的1.572s、P80的2.310s，仍在21/29轮。原图标记1.575/2.315s继续保留；均非精确首次穿越，详见figure_evidence_addendum.json。

原始点与区间：raw_plot_points_all_nodes.csv；绘图曲线：display_curves_AB_NPU0.csv；细分时间表和原C入口盒：frozen/；原收据/逐调用时间：point_run01/。

命令与日志：point_command_started/return.json、point_stdout/stderr.log；原630项审计figure_audit.json；v1绘图render_*、v2/v3独立CSV排版layout_v2/v3_*。

v2/v3及v3初稿均仅重读相同CSV，0新核调用。右图例移开高温曲线；左标点文本移到空白区并换行。未偏移/缩放任何温度。根与数学审阅目视确认最终分行版无遮挡。

v1 Matplotlib对默认缓存无写权限，自动使用临时缓存，图像成功输出；v2/v3显式使用可写临时缓存。没有依赖安装、推送或合并。

共享原评价内核复核，不是独立实现证书；2ms采样连线不替代连续证据。原400ms输入上的合法固定时间表未重建，绘图周期是已有九配置中的选定子集。

最终清单figure_final_manifest.json覆盖全部交付工件（排除自身及Python缓存）。figure_manifest.json保留为未改的v1历史快照；它在程序收尾打印前对render_stdout.log记录了空日志哈希，最终日志以本清单为准。
