# 完整 auto-L R1：有证书状态剪枝 OFF/ON 静态配对

已在主代理绑定验收凭证后仅运行一次OFF/ON静态配对及一次比较。两组均成功；没有LP/MILP求解、候选热评价或初始化。实际减少2,938个联合状态、29,380条电热行，与此前预测完全一致。ON构模更慢，不能声称构模或求解加速。

## 实际规模与成本

|指标|OFF（旧选项支持传播开启）|ON（另开状态剪枝）|
|---|---:|---:|
|联合状态块|9,798|6,860|
|AB / AC状态块|4,861 / 4,937|3,397 / 3,463|
|变量|19,857|16,919|
|约束行|124,338|94,958|
|非零|1,311,146|990,904|
|模型构建/s|6.976845|17.185567|
|矩阵导出/s|0.479766|0.392544|
|能量强化证书复核/s|0.570011|0.441292|
|worker记录时长/s|9.420930|21.502668|
|父进程记录完整日历/s|9.747082|23.958376|

减少2,938个w、29,380行、320,242个非零；前两项与预测偏差均0。ON状态支持过滤的原计时区域1.430318s，包含构模中的必要证据查找；门关闭临时行生成及严格冗余审计区域10.764056s。该审计区域含相应系数准备，不能再与嵌套工作重复相加。保留状态电热条件行组装由4.250397s变为2.821374s，但新增认证成本使总构模更慢。单次顺序运行和阶段计时不能证明任何求解器性能变化，且本轮根本没有求解。

## 身份与验收

基于提交9d972848及7631a16d中的冻结auto-L原完整R1，AB/AC各6次Stage执行，输入/设备/频档/起点/非整数结束/场景/物理模型未变。双方旧propagate_support=True，rev02 baseline flags逐项保持，只切换prune_joint_states。默认关闭是正式接口行为，不能把OFF称旧的“选项传播关闭”。

计划SHA-256：`a7ab9d4af043d07ea4a29d562ae31201b3d929f7e3bc9a47956021202bd18929`。217份源快照冻结，既有文件仅milp.py发生本轮改动，另有新joint_state_support.py；两者SHA分别为 `43e259d03ce5c65e38a9fb1148fdd45acfecb3b4fb132e1f6d14ea34963e65b4` / `d4f7ee5916d5bb935f11852a5969d04379e11adde1e015b8e248cdb6f03c979c`。

acceptance.json绑定六份通过证据及验收后源码哈希，包括小域完整安排/物理比较、旧结构回归及独立原矩阵gate0/dependency/control检查。未先运行完整R1再补验收。

## 数值表示检查

1. OFF所有导出NPZ数组（含A数据/索引/指针/shape、b/c/lb/ub/intcon）与旧auto-L supportON归档逐字节一致，变量名也一致。
2. OFF/ON完整options和events一致。所有共同变量的lb/ub/c按名字重编号后逐字节一致，实际整数变量名字集合一致。因此既有全部数值盒和目标保留，没有以剪状态为名收紧能量上界。
3. 将OFF被删w代为0，删除其23,504温度行和5,876能量行，排除单独复核的能量强化行后，94,534个存活行实例按(tag、变量名字、系数binary64.hex、右端binary64.hex)的多重集与ON精确相同。它们包括正确重建的一热/频率边际及所有保留电热条件行。
4. 每侧424个energy_state_lower_bound证书分别复核：对每个保留整数一热状态，比较新cut与来源complete_energy/lower行的残差差值，在导出变量盒上取精确Fraction最大值，均≤0。不是只比较目标值，也没有运行LP检查这些cuts。
5. 生产ON对2,938个删除state的29,380个临时原电热行，严格检查门为0的导出binary64全盒上界。最小严格余量 `277/4722366482869645213696`，约5.86570315973603e−20，0失败，未用容差掩盖正残差。生产依赖证书最小正余量约0.0013333333333329733，全部大于其路径行数×1e−9参考容差。完整报告在execution/on/preprocessing.json；简明汇总见pruning_audit_summary.json。

原整数y及精确一热/控制行前提不可去掉。以上检查不声称近整数容差管道的所有点被保留，也不要求LP松弛多面体相同。只读核对现有preprocessing后确认：AB记录的1,074份依赖路径证书中，1,060份用于最终被删状态，14份未用于最终删状态；AC的1,344份中，1,332份使用、12份未用。因此最终使用数为2,392，另外26份不属于最终删状态的证书。实际被删状态的完整变量名字集合也与旧2,938个状态逐项相同；不能将全部证书对象数2,418与最终使用数或状态数混为一谈。核对依据见本轮根目录的 `prediction_identity_check.json`，不再对差异作未经证明的缓存分组归因。

## 实际时间、命令与日志

工作目录 `/workspace/paper`。Python3.12.14，NumPy2.3.5，SciPy1.17.0，Linux，无安装。批次UTC 2026-11-11 08:17:41.084003–08:18:14.790920，即北京时间16:17:41.084003–16:18:14.790920，共33.706917秒。OFF父进程UTC08:17:41.084148–08:17:50.831213；ON为08:17:50.831842–08:18:14.790182。

每侧300秒worker窗口和380秒外部看门狗，均正常退出码0，未触发外部保护。worker_elapsed_s在最终result.json写入/打印之前采样，完整父进程日历另包含这些归档及退出开销。方法从worker入口计入导入、身份核验、构模/导出和证书检查；最终归档允许在协作预算检查点后完成，不能把看门狗当额外科学预算或严格实时保证。

精确shell命令见commands.json。freeze.stdout/stderr、controller.stdout/stderr、off.stdout/stderr、on.stdout/stderr完整保留。各侧execution目录保存result、options、variable_names、row_tags、exported_model.npz、preprocessing、energy_bound_certificates、energy_certificate_checks及build_progress；父进程回执是off.command_receipt.json和on.command_receipt.json。

compare.stdout/stderr及comparison.json保存无新构模的数值比较。pruning_summary.stdout/stderr和pruning_audit_summary.json保存只读证书汇总。后者第一次临时heredoc在无删除区间缺少states字段时遇到KeyError；改为读取空列表后完成，未重复构模、比较、热评价或求解，问题说明保留于commands.json。

本次没有构模失败、超时或补跑。固定freeze/run/compare各一次，未覆盖历史、不推送、不合并。源码和历史保护由本轮主报告统一检查。
