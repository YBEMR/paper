"""Append the user-confirmed stage without normalizing legacy Markdown bytes."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
p = REPO/'RESEARCH_BRIEF.md'
b = p.read_bytes()
intro = '''**K.148／D173进行中：旧联动4开2闭—5开1闭冻结质量配对（E593）。** 用户在D172恢复人工交接后明确授权“按照你说的开始做实验”。新授权限原base__R1、原参数／auto-L／热安全标准，旧联动与新5开1闭各一次300秒，顺序固定、不补跑／延时；两者第一遍相同，第二遍只增加本地main的OPP与起点，具体设备及post仍固定各自fresh seed／最后第一遍完整SAFE。协议、输入、167源、一次性消费与900秒外层监督已冻结；24/24零研究包装预检和504项小域核对通过，165旧源保持，attempt01临时目录权限失败保留。已开始执行；尚无配对结论。自动审查开关保持关闭，不复用过期夜间配额、不代写reviews，不启动115次。 [冻结协议](research/chapter3_experiments/results/five_open_preparation01/protocol.md)；[凭据](research/chapter3_experiments/results/five_open_precheck01/attempt02/checks.json)。

'''.encode('utf-8')
assert '**K.148／D173'.encode('utf-8') not in b
key = '**K.147／D171'.encode('utf-8')
assert b.count(key) == 1
b = b.replace(key, intro+key, 1)
choice = '''**D173（2026-10-21，用户直接授权5开1闭配对）：** 用户“可以，你就按照你说的开始做实验吧”确认此前唯一建议。范围为最小包装／预检及原完整基准旧联动→5开1闭各一次独立300秒；5开只释放第二遍本地main，不动设备、物理参数、合法起点或安全门。每方从自身fresh seed开始，闭post取自身第一遍最后完整SAFE，禁止历史／跨方免费候选。一次配对后结束，无改善也保留。D172人工交接继续有效，D171旧夜间预算及自动闸门未重新启用；后续若改变物理模型、部署域或增加调用需另讨论。

'''.encode('utf-8')
key = '**D172（'.encode('utf-8')
assert b.count(key) == 1
b = b.replace(key, choice+key, 1)
p.write_bytes(b)

e = REPO/'research/03_证据与检索记录.md'
raw = e.read_bytes()
assert '### E593：'.encode('utf-8') not in raw
raw += '''
### E593：5开1闭实施、零研究预检与冻结配对（2026-10-21，K.148／D173，进行中）

用户暂停自动审查后直接授权本配对。沿K146已定位接口，只新增调用包装与测试，165份已有源码逐项不变；两者同一linked入口，第二遍新版只多放开本地main的工作点／起点。先存冻结协议、双方法独立300秒和单次claim，24项包装mock／数据检查与504项小域笛卡尔积通过；attempt01 Windows临时目录权限失败完整保留，预检改用工作区临时目录后02通过，没有借此运行原规模构模、优化器或热评价。小域开发时rows字段修正另记失败历史。

原输入、167份源码及快照、通过凭据、环境、顺序和安全接纳契约冻结后，执行原base__R1旧联动4开2闭→5开1闭各一次；900秒外层监督只清理所属进程树，方法内300秒覆盖输入、初始化、MATLAB、构模、求解、缓存与完整连续复核。独立内部技术审查不冒充原ChatGPT外审。当前执行中，无结果预判；主指标为新完整安全能量上端严格低于旧下端，另分列两遍贡献、截止状态和仍未证明的全域最优性。冻结与预检入口在results/five_open_preparation01及five_open_precheck01，自动reviews和过期夜间预算不动。
'''.encode('utf-8')
e.write_bytes(raw)
print('Recorded D173 and K148 in progress; legacy bytes preserved.')
