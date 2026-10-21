"""Record the user-confirmed scope and analysis proposal; preserve legacy bytes."""
from pathlib import Path
import json

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
assert json.loads((OUT/'audit.json').read_text(encoding='utf-8'))['passed']
assert json.loads((OUT/'dependency_audit.json').read_text(encoding='utf-8'))['passed']

p = REPO/'RESEARCH_BRIEF.md'
b = p.read_bytes()
assert '**K.149／D174'.encode('utf-8') not in b
intro = '''**K.149／D174：保留4开2闭；完成根LP／整数候选瓶颈分析，唯一提出固定锚约束预消元（E594）。** 用户明确保持原参数及热安全、不补跑；本轮仅读K148日志、原生矩阵身份、选项目录和源码，0构模／LP／MILP／热／研究调用，167生产与调用源保持。[分析与提案](research/chapter3_experiments/results/root_candidate_analysis01/summary.md)、[原生指标](research/chapter3_experiments/results/root_candidate_analysis01/native_metrics.json)、[静态计数](research/chapter3_experiments/results/root_candidate_analysis01/direct_dependency_analysis01/anchor_dependency_note.json)保存。

**定位与唯一改进：** 求解等待／响应读取占84.82%／86.89%；8个请求均自报0分支节点，但旧4第二遍AB有warm外3个安排，直到请求约60秒才发布。主要问题不是热核／数值门，也无“大分支树”的证据。原生最终维数须计补集列：旧AB／AC为6738／7810，新为8060／15314，区别于构模摘要。建议只把闭main/post锚所决定的同单元、同域异OPP和原直接依赖必零选项，在事件展开前一次排除；不加CDF、迭代或邻域。旧4 AB280→216、AC274→213选项，跨事件joint合计3077→2360、温度／能量条件等式组合计静态少23.30%，原完整warm均保留。证明限原4开2闭真实整数合法域；新系数包络不冒称旧浮点矩阵逐点相同。

**完成边界：** 内部独立资源及依赖核对通过，非外部ChatGPT审批；现有目录核对不替代完整小域穷举。预消元尚未接入生产，无新速度／能耗结果。下一项仅建议实现这一预消元并作小域合法集合、新事件、x0／增广映射及连续门预检，再单独讨论冻结质量配对；本轮不新增研究配额、不恢复115次或温度扫描。

'''.encode('utf-8')
key = '**K.148／D173：'.encode('utf-8')
assert b.count(key)==1
b=b.replace(key,intro+key,1)
key = '**D173（'.encode('utf-8')
assert b.count(key)==1
decision = '''**D174（2026-10-21，用户确认保留4开2闭并授权分析）：** 用户明确“先保留4开2闭，继续分析根LP和整数候选生成的瓶颈，提出一项针对性的改进”，原参数和热安全标准不变、先不补跑。助手本轮选用只读存档／源码分析与精确静态计数，提出固定锚约束预消元；实现、正确性预检与性能配对分别待后续安排，不能由本记录自行启动。D173两次旧配额已消费，不复用；自动外审仍按D172暂停。若改动需额外限制合法安排、改变部署／参数或安全门，先讨论。

'''.encode('utf-8')
b=b.replace(key,decision+key,1)
p.write_bytes(b)

p=REPO/'research/03_证据与检索记录.md'
b=p.read_bytes()
assert '### E594：'.encode('utf-8') not in b
b+='''
### E594：4开2闭根节点瓶颈与固定锚必零预消元提案（2026-10-21，K.149／D174）

用户确认保留4开2闭，授权只读分析并提出一项改进，不补跑。复用K148 b3f0798原始response／diagnostic／matrix_identities／labels和当前源码，原参数、167源与研究工件保持；无构模、LP/MILP、热评价或研究调用。两个内部只读子任务分别核原生进展和表达；非另一ChatGPT外审，reviews未动。

求解等待及响应读取为239.782／238.719秒，约占方法84.82%／86.89%；构模9.204／13.297秒，continuous_thermal_energy_evaluation分项5.671／4.173秒，另计初始化／原输入／视图复核，增广数值门0.045／0.079秒。全部8个native请求最终numnodes=0，但有整数点；旧4第二遍AB在请求墙钟60.073／60.104／60.123秒才产生3个warm外安排，新5两个scene只重报warm。根LP回调为累计时间，未细分全部根节点后段割／启发式成本，不断言树过大或唯一因果。K148所列5322／6149等是构模维数；实际原生旧AB／AC为6738／7810，新为8060／15314，含补集列和1416／1661／1759／5241条链接等式。该统计口径在本报告分列，不回写旧原始记录。

唯一提案为固定锚约束预消元：原邻域和期限过滤后、事件展开前，只将当前闭合main／post作必选锚。以精确半开区间排除同unit重叠、同domain异OPP重叠，及原直接边恰一端闭合的结束／启动冲突选项。closed y=1与原互斥／频点锁／依赖蕴含bad y=0，故原4开2闭真实完整合法安排集合不变；warm保留。直接依赖还可排除期望行允许的虚假分数混合，但局部代数例不当当前完整LP最优点证据。不扩open-open／CDF／传递闭包／迭代，不修改J、温度盒界或求解器参数；旧CDF／Cut配对不重新包装为新机制。

标准库只解析已存labels及原模式时长，资源alone删除28／5项；并入直接依赖后AB280→216、事件173→145、joint1416→1029，AC274→213、201→156、1661→1331。合125项必零、温度／能量条件等式组合计15385→11800（静态少23.30%）。每项删除证据与原warm保留已存，两套内部独立精确核对复现；未构造新矩阵、完整小域穷举或测性能。第一版只读脚本因CSV BOM表头KeyError失败，记录保留，改utf-8-sig后计数完成，不涉及科研补跑。

材料见[提案](chapter3_experiments/results/root_candidate_analysis01/summary.md)、[原生事实](chapter3_experiments/results/root_candidate_analysis01/native_metrics.json)、[可复跑目录分析](chapter3_experiments/results/root_candidate_analysis01/analyze_direct_dependencies.py)、[最终静态计数](chapter3_experiments/results/root_candidate_analysis01/direct_dependency_analysis01/anchor_dependency_note.json)及同目录audit／dependency_audit。建议下一项仅接入该预消元并核独立小域完整合法集合、新事件覆盖、原warm、重建x0／增广数值门和完整连续热接纳；物理合法域等价与旧数值外包逐点等价分开。最终效果仍看预算内完整安全能耗，模型变小不自动成立节能收益。本轮到提案结束，不改生产、不增加研究配额或运行115次。
'''.encode('utf-8')
p.write_bytes(b)

p=REPO/'research/第三章当前进展与正式实验推进计划_审查稿.md'
b=p.read_bytes()
replacements={
'| 日期与阶段 | 2026-10-17初稿；2026-10-18追加K.105—108；2026-10-19追加K.109—127；2026-10-20追加K.128—146分析、质量配对、独立两法执行与方案差异 |':'| 日期与阶段 | 2026-10-17初稿；保留K.105—146记录；2026-10-21追加K.148配对与K.149固定锚预消元提案 |',
'| 状态 | K.146完成联动—HEFT存档差异分析，下一项范围调整仅建议、未实施 |':'| 状态 | K.148五开未优于四开；用户保留4开2闭；K.149完成存档分析，预消元尚未实施 |',
'| 内部核对 | 本线程[K.146独审](chapter3_experiments/results/linked_heft_gap_analysis01/independent_review.md)，非主线⑥跨会话审查 |':'| 内部核对 | [K.148终审](chapter3_experiments/results/linked_five_open_pair01/independent_review.md)、K.149同目录audit及dependency_audit；均非主线⑥跨会话审批 |',
'| 本轮边界 | 仅既存方案／条件／日志及代码分析；0研究／构模／热重算，165源与原档案保持 |':'| 本轮边界 | K.149仅存档／源码分析和静态计数；0研究／构模／热重算，167源及既存研究工件保持 |'}
for old,new in replacements.items():
    a,z=old.encode('utf-8'),new.encode('utf-8')
    assert b.count(a)==1,old
    b=b.replace(a,z,1)
key='## K.146：'.encode('utf-8')
assert b.count(key)==1
section='''## K.149：保留4开2闭，下一项只建议固定锚约束预消元

用户明确保持参数与热安全、先不补跑。[本轮分析](chapter3_experiments/results/root_candidate_analysis01/summary.md)核清：K148约85%的方法时间在求解等待／响应读取，8个原生请求均未报告分支节点推进；新版只返回warm。原生最终矩阵应包含补集列，区别于构模摘要，不能把根LP累计时间当独占阶段时间。

唯一建议是将闭合main／post决定的资源、共享频点及原直接依赖必零选项，在事件展开前一次排除。按已存目录静态核对，AB280→216、AC274→213项，温度／能量条件等式组合计少23.30%，完整warm保留；真实4开2闭合法安排不变。未实现、未解LP或热重算，静态体积不冒称加速／节能。下一项先做该预消元实现及小域合法集合、事件、x0／增广映射与连续门预检，再单独冻结质量比较，不加CDF／迭代／新邻域，不启动115次。

## K.148：5开1闭未优于原4开2闭

原base__R1各一次300秒配对：旧U＝0.910239340728 J／282.703秒，新U＝0.962884840560 J／274.734秒；第二遍完整改善3／0次。[完整结果](chapter3_experiments/results/linked_five_open_pair01/summary.md)保存。原包装向外舍入误报保留并纠正，只执行未开始的新版，旧未补跑；两方完整连续SAFE成立，0热反馈、无全域最优证明。用户已确认先保留4开2闭。

'''.encode('utf-8')
b=b.replace(key,section+key,1)
p.write_bytes(b)
print('Recorded K149/E594/D174 and refreshed the existing chapter-three plan.')
