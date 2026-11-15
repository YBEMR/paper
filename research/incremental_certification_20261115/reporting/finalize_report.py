"""Append transparent limits/resources to the generated report; no simulation."""
import json,sys
from pathlib import Path
def main(root):
    read=lambda p:json.loads((root/p).read_text(encoding='utf-8'))
    d=read('formal_v2/analysis.json');audit=read('results/post_audit.json');s=read('results/summary.json')
    assert not d['failures'] and audit['status']=='PASS' and len(d['runs'])==16
    text=(root/'REPORT.md').read_text(encoding='utf-8')
    if d['common_SAFE_candidates']==855:
        text=text.replace('全进程/全根总耗时包含各臂实际完成的不同工作量，不能直接代替共同前缀节省。','本次三臂均完成全部855候选，实际全根与共同前缀工作量相同。若复现遇到截断，必须重新取共同前缀，不能直接比较不同工作量。')
    a,b,c=[d['totals'][x] for x in 'ABC']
    zero=[r['call'] for r in d['runs'] if r['arms']['B']['cache_common']['scene_hits']==0]
    neg=[(r['call'],r['saving_vs_A']['B']) for r in d['runs'] if r['saving_vs_A']['B']<=0]
    env=read('formal_v2/01_U07__n24_HEFT_I1__A/summary.json')['environment']
    lines=['','## 6. 反例、测量限制与后续决策','',
      f"B在{d['positive_runs']['B']}/16条、C在{d['positive_runs']['C']}/16条序列上降低完整计费。B负收益："+'；'.join(f'{name}（{value*100:.2f}%）' for name,value in neg)+'。整场景零命中：'+', '.join(zero)+'；该序列B/A差异不能归因于复用收益。',
      '',f"总面板减少：B {100*(1-b['new_panels_common']/a['new_panels_common']):.2f}%，C {100*(1-c['new_panels_common']/a['new_panels_common']):.2f}%。C额外前缀覆盖{c['cache_common']['avoided_prefix_panels']}个面板，整场景覆盖{c['cache_common']['avoided_scene_panels']}个面板。面板覆盖是确定性运算计数，墙钟差包含直接成本、间接内存成本及运行波动，二者不能互换。",
      '', 'C将各事件边界的完整前缀状态（含累计trace）保存在进程内；当前实现可能随边界数产生二次累计存储。正式最大工作集与B相比增加'+f"{(c['peak_rss_max_bytes']-b['peak_rss_max_bytes'])/2**20:.2f} MiB"+'，这是各臂最大进程工作集之差，不是精确缓存独占量或逐对象剖析。本轮未优化存储、未开发后缀支配。',
      '', '本批运行环境：'+env['platform']+'；'+env['processor']+'；Python '+env['python']+'。没有固定核心或隔离整机背景活动；所有臂同机串行，臂序预先轮换。对无收益B组，已有直接维护计时不能解释全部差额，不能凭空断言只由操作系统调度造成。',
      '', '回放保留完整评价的300秒根截止、实际新增面板/细化上限和未决后根关闭；归档phase仅用于恢复原能量接纳规则。原180秒初始化准入属于搜索生成器，本轮不执行生成器，也不重新按新墙钟筛选归档候选。下一轮真实搜索必须同时保持该准入规则。',
      '', '结论：本批C的净耗时改善在16条冻结序列上方向一致，支持进入小规模同预算搜索验证；单次轮换不足以证明跨机器统计稳定性，也未证明更低调度能耗。'+('[下一轮受控协议草案](NEXT_SEARCH_PROTOCOL.md)仅建议12根，不执行。' if s['recommend_controlled_search_protocol'] else '未授权扩大实验。'),
      '', '## 7. 修正代价与归档核验','',
      '|阶段|完整回放进程|非零退出进程|进程墙钟合计s|用途|','|---|---:|---:|---:|---|']
    for row in audit['resources']:
        meaning={'pilot':'B准入，不混入正式结果','formal':'v1诊断；一次输入读取前控制停止；全部排除最终性能','formal_v2':'统一v2正式结果'}[row['stage']]
        lines.append(f"|{row['stage']}|{row['successful_replay_processes']}|{row['nonzero_exit_processes']}|{row['all_process_wall_s']:.3f}|{meaning}|")
    lines+=['','表中只计三个回放阶段的子进程墙钟，不含正确性测试、人工审查与资料整理。77个完整回放进程=8准入＋21旧版诊断＋48最终验证；没有选择较快的一次充当正式结果。',
      '',f"[归档后审计](results/post_audit.json)：{audit['frozen_sources_byte_identical']}份冻结来源逐字节一致，{audit['archived_candidate_payload_hashes']}份候选载荷哈希一致，48条使用相同v2源码身份，8份输入/配置原字节复制。历史状态{audit['historical_states']}保持原标签。测试中的超时、违规、损坏和根关闭反例与旧版失败日志保留；正式三臂本批违规/未决均为0，不能以此声称普遍无故障。",
      '', '数据复算入口为analyze.py；reporting/保存报告生成和只读审计脚本。它们不导入物理评价器、不新增科学计算。提交只增加本独立目录并前置更新RESEARCH_BRIEF，第三/四章原树和既有诊断不改。']
    (root/'REPORT.md').write_text(text+'\n'.join(lines)+'\n',encoding='utf-8')
    s.update(positive_runs=d['positive_runs'],all_candidates_complete=d['common_SAFE_candidates']==855,
      frozen_source_verification='post_audit.json',negative_scene_runs=[{'call':k,'saving':v} for k,v in neg],
      peak_rss_max_bytes={arm:d['totals'][arm]['peak_rss_max_bytes'] for arm in 'ABC'})
    (root/'results/summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if s['recommend_controlled_search_protocol']:assert (root/'NEXT_SEARCH_PROTOCOL.md').exists()
    print(json.dumps({'report_ready':True,'positive_runs':d['positive_runs'],'negative_scene_runs':neg},ensure_ascii=False))
if __name__=='__main__':main(Path(sys.argv[1]))
