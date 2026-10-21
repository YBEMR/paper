"""Finalize the completed K148 stage; preserve unrelated/legacy Markdown bytes."""
from pathlib import Path
import json

REPO = Path(__file__).resolve().parents[4]
ROOT = REPO/'research/chapter3_experiments/results/linked_five_open_pair01'
audit = json.loads((ROOT/'independent_audit.json').read_text(encoding='utf-8'))
assert audit['state'] == 'PASS_WITH_DISCLOSED_RECOVERY'
assert audit['checks_passed'] == audit['checks_total'] == 43
assert (ROOT/'independent_review.md').is_file()
facts = json.loads((ROOT/'analysis01/facts.json').read_text(encoding='utf-8'))
assert facts['comparison']['valid_quality_pair'] and not facts['comparison']['strict_new_improvement']
assert facts['consumed_calls'] == 2

p = REPO/'RESEARCH_BRIEF.md'
b = p.read_bytes()
start = b.index('**协作方式更新（2026-10-21，D172）'.encode('utf-8'))
middle = b.index('**K.148／D173进行中：'.encode('utf-8'))
end = b.index('**K.147／D171：'.encode('utf-8'))
assert start < middle < end
collaboration = b[start:middle]
old = '科学进度仍为K146差异分析，5开1闭尚未实施，115次正式批量未启动。本轮仅汇报进展，不运行实验。'.encode('utf-8')
new = 'D172时仅汇报K146进展；后续用户D173另行授权K148配对，结果见上。自动审查仍未恢复，115次正式批量未启动。'.encode('utf-8')
assert old in collaboration
collaboration = collaboration.replace(old, new, 1)
intro = '''**K.148／D173：5开1闭质量配对完成，未优于旧4开2闭（E593）。** 原base__R1、完整AB／AC三Stage、400 ms／5 ms、auto-L与50°C／80°C保持，两方法各一次独立300秒。旧U＝0.910239340728 J／282.703秒，新U＝0.962884840560 J／274.734秒，新高5.783699%。旧第二遍3次完整改善，新第二遍0次；两方法最终SAFE均已完整连续复核。[阶段结论](research/chapter3_experiments/results/linked_five_open_pair01/summary.md)、[存档分析](research/chapter3_experiments/results/linked_five_open_pair01/analysis01/facts.json)、[内部独审43项](research/chapter3_experiments/results/linked_five_open_pair01/independent_review.md)保存，非主线⑥跨会话审批。

**方法线索：** 新第二遍只开放本地main，设备及闭post仍取自身完整锚；模型扩大，AB／AC根LP原生自报4.317／8.256→15.913／45.067秒，新只重新得到warm。两次第一遍B.post为145／150 ms，不能作固定warm单因素归因；新有更多二遍剩余预算仍无新增改善。0热违规／0反馈，L0约0.738286 J未闭合，无全域最优／无解证明。建议暂保留4开2闭，停止直接扩大开放数量，下一项仅据已有模型／根LP记录确定一项整数候选生成结构修订；未授权新调用、温度扫描或115次批量。

**实现故障与恢复：** 原包装将60位向外舍入上端多5×10⁻⁶¹ J误判加权不等，保守阻断后续。24项包装＋504项小域预检未覆盖此边界；另补7项回归与独立存档核对后，只执行尚未开始的新方法，旧未重跑、旧BLOCKED／claim保持。167冻结源／165继承源与301历史工件不变；额外修复适配器只纠正事后审计，绑定SHA另存。累计2次／600研究秒配额已消费；活动进程576.422秒、诊断暂停388.623秒，完整日历约965.037秒，不称无中断900秒内完成。临时目录失败、审计首轮类型错误、绑定分析版及图例修订均保留。

'''.encode('utf-8')
b = b[:start]+intro+collaboration+b[end:]
key = '**D172（'.encode('utf-8')
note = '**D173执行结果附记：** K148两次配额已消费，旧版更低；发生一次包装误报，按有据恢复记录只执行未开始的新方法。算法、参数、合法域与安全门未改，原误报与旧claim保留。当前保留4开2闭及下一项结构分析均为助手建议，不冒充用户再次选型或新增求解授权。\n\n'.encode('utf-8')
assert b.count(key) == 1
b = b.replace(key, note+key, 1)
p.write_bytes(b)

e = REPO/'research/03_证据与检索记录.md'
b = e.read_bytes()
start = b.index('### E593：'.encode('utf-8'))
after = b.find(b'\n### ', start+1)
after = len(b) if after < 0 else after
entry = '''### E593：5开1闭实施、冻结质量配对与包装舍入修复（2026-10-21，K.148／D173）

用户D172暂停自动审查后直接授权必要实现／预检与本配对。新增独立包装与测试，165份已有研究源码不变；两者同linked入口，第二遍只多放开本地main的OPP／起点。冻结原base__R1、完整AB／AC三Stage、400 ms／5 ms、auto-L、50°C／80°C、原参数与数值／连续安全门，固定旧→新各一次300秒。原输入三hash、167源及快照、预算与单次claim绑定；24/24零研究包装预检及504项小域组合通过。attempt01为Windows临时目录权限失败，改工作区临时目录后02通过；小域开发rows字段修正亦保留。

旧原方法正常完成，U＝0.9102393407277644 J，但新增包装要求加权端点完全相等，误将60位向外舍入的5e-61 J上端余量记为WEIGHTED_ENERGY_MISMATCH并停止未启动新版。两个内部只读核对均证实原区间包容精确加权结果且逐字复现原向外端点；7/7补充回归通过，修复只作事后审计、无任意容差。原协议／167源／旧结果／BLOCKED claim不改，保存恢复前账本及修订hash，不重置global／旧消费，只执行原定尚未开始的new一次；没有重跑或扩大调用。恢复分析绑定版另存，最终分析版增计时与L0展示，路径变化如实披露。

最终旧U＝0.910239340728 J、282.703秒；新U＝0.962884840560 J、274.734秒，新高5.783699%。第一遍旧／新分别0.962885037941／0.962884840560 J；第二遍旧新增3次完整U下降，新0次。新二遍含准备135.563秒，旧132.875秒；根LP自报AB 4.317→15.913秒、AC 8.256→45.067秒，新仅返回warm。模型规模扩大与较慢根LP是直接线索，不把全部差异唯一归因于main；第一遍post锚145／150 ms不同，域包含只对同一warm成立。完整能量差约0.052645500 J，活动／基准／温度修正差分别约0.037364520／0.012250000／0.003030980 J，公共项0。

两方法独立预算token／MATLAB／候选／缓存，均完成AB／AC、400 ms及空闲尾段，连续峰温上端最高约51.178°C。热违规和反馈均0；本次自身独立L0约0.738286 J未闭合，无全域最优／无解证明。总2次研究调用、8个原生请求，配额600秒已消费；实际方法合557.437秒、活跃进程576.422秒，诊断暂停388.623秒，完整日历965.037秒，不拼为原连续900秒内首轮无故障流程。恢复实际600秒监督严于遗留607秒注释，不构成延时。

存档分析与内部独立43项核对通过；原165源、167快照、原输入及K142原301工件保持。独审首轮window字符串误比较保留，改精确Fraction类型核对后通过；旧绑定分析版与最终分析版分别保存。初版图例颜色错误另存修订图，数值facts不变。MAT依ignore本地保留哈希，不强制上传。证据见[阶段结论](chapter3_experiments/results/linked_five_open_pair01/summary.md)、[分析](chapter3_experiments/results/linked_five_open_pair01/analysis01/facts.json)、[内部独审](chapter3_experiments/results/linked_five_open_pair01/independent_review.md)、[恢复协议](chapter3_experiments/results/five_open_preparation01/recovery_protocol.md)。未创建外部reviews，内部核对不冒充主线⑥审批。

本次不采用5开1闭替代旧版；建议暂保留4开2闭，停止直接扩大开放数量，先依据已有模型／根LP记录确定一项整数候选生成结构修订。没有追加调用、热扫描、调参或115次正式批量；以上下一项为建议，尚非新增科研授权。
'''.encode('utf-8')
e.write_bytes(b[:start]+entry+b[after:])

p = Path(__file__).with_name('failure_history.md')
with p.open('ab') as stream:
    stream.write('''
- 研究配对执行后：旧原方法正常完成，事后包装误将合法向外舍入端点判为加权不等；保留原BLOCKED。另存精确修复、7项回归及恢复协议后仅消费未开始的新版，无研究补跑。原167源码保持，错误修复在有SHA绑定的事后适配器中。
- 独立终审attempt01：window字符串与整数的审计谓词误比较，以及分析路径版本变化未先识别保留快照。首轮记录保留；按Fraction及已绑定原分析版SHA重核后43/43通过，不涉及科研数据修正。
- 初版能量分项图两方法颜色映射不一致；另存v2及修订脚本，原图与数值facts不变。
'''.encode('utf-8'))
print('Finalized K148/E593 with completed evidence and disclosed recovery.')
