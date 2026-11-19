# 源码与证据索引

所有科学源码引用固定在结果提交 `babfc5edccfd036ed21a90c7484fb1ed2bcd9276`。本轮只读清单核对通过，完整SHA见input_hashes.json。

| 审查点 | 固定源码/归档 | 关键位置 |
|---|---|---|
| 前缀复用、无目标剪枝、热失败仍续算 | [run.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_scene_dvfs_admission/run.py#L129) | joint_search；combine L75 |
| 包络筛查、块编译、回退 | [joint_thermal.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_scene_dvfs_admission/joint_thermal.py#L29) | _screen L29；参考积分L64；块积分L87；batch L106；回退L120 |
| 逐部署重编译与noheat晚提取 | [experiment.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_multidnn_expansion/experiment.py#L248) | 调度/编译L248–278；搜索后noheat L324；完整重放L212 |
| 边界排空、尾窗、完整SAFE | [scene_events.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_scene_dvfs_admission/scene_events.py) | partition_requests/time_scene/replay_sequence |
| 活跃应用确定性资源竞争 | [events.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_synthetic_platform_v1/events.py) | PRIORITY、simulate；固定纳秒和资源排队 |
| DNN物理链、频档/功热参数依赖 | [profiles.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_synthetic_platform_v1/profiles.py) | build_chains/thermal_kwargs |
| 非负漏电、被动导热、完整连续检查 | [thermal.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_synthetic_platform_v1/thermal.py) | evaluate_thermal/_replay/_tighten_peak |
| 稳定模态及已有lru_cache | [physics.py](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_thermal_v1/physics.py#L57) | modes；本实验只借用该模态函数 |
| 成本、既有完整策略复核 | [raw/expanded](https://github.com/YBEMR/paper/tree/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_multidnn_expansion/raw/expanded) | 各工况result/deployments/local及196份space_*.npz |
| 冻结约束与服务 | [design.json](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_safety_repair_audit/design.json) | 25°C四实例、帧数、30°C初温、80°C上限 |
| 部署及活跃网络 | [expanded_input.json](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_multidnn_expansion/expanded_input.json) | deployments/stages、fsm/active_apps |
| 预注册身份 | [freeze_manifest.json](https://github.com/YBEMR/paper/blob/033cf34547bb5cb6041e940c80895cced758002a/research/kim_multidnn_expansion/freeze_manifest.json) | 远程blob与29文件SHA逐项核对 |
| 结果身份 | [delivery_manifest.json](https://github.com/YBEMR/paper/blob/babfc5edccfd036ed21a90c7484fb1ed2bcd9276/research/kim_multidnn_expansion/delivery_manifest.json) | 远程blob与479交付文件SHA逐项核对 |

## 本轮新增证据

- audit_archive.py / audit_archive.log：只读归档一致性、196个NPZ最低值、SAFE完整回执、成本汇总。
- audit_structure.py / audit_structure.log：保守精确场景等价类、矩阵单调性检查、8次时序E0及3次单场景热积分E0。E0结果仅用于机制核查，不作为新增科学工况结果。
- audit_prefix_reuse.py / audit_prefix_reuse.log：从固定部署及已归档期限合法动作数计算完全相同历史输入的前缀重复数。
- baseline_witnesses.json：四组最低候选的原始完整复核以及逐部署无温限最低值；未复制整个原档。
- equivalence_classes.json.gz：完整成员表的无损压缩副本，解压为UTF-8 JSON；原JSON为可再生成中间件，未作为第二份远程材料重复上传。
- monotonicity_e0.json：432个矩阵核查、4对事件相等、一次温度偏序检查及归档前缀证据缺失的计数。
- RUN_RECEIPT.json / budget.jsonl / SHA256SUMS.json：运行量、预算、输入及交付hash，原科学文件在封存时再次核对。

所有重复数量是本轮静态证据；原档计时保持原测量属性，新方法未实现、未运行，没有新方法加速数字。

