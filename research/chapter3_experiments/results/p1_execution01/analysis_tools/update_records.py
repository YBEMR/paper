"""Append verified P1 completion without normalising historical file newlines."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPO=next(p for p in ROOT.parents if (p/'AGENTS.md').is_file())


def insert_before(path, marker, text):
    data=path.read_bytes();token=marker.encode('utf-8')
    assert data.count(token)==1, marker
    path.write_bytes(data.replace(token, text.encode('utf-8')+token, 1))


def main():
    facts=json.loads((ROOT/'analysis01/facts.json').read_text(encoding='utf-8'))
    m=json.loads((ROOT/'analysis01/report_metrics.json').read_text(encoding='utf-8'))
    review=json.loads((ROOT/'record_review01.json').read_text(encoding='utf-8'))
    assert review['passed'] and facts['observed_rows']==40 and facts['process_terminal']['state']=='COMPLETED'
    percentages='／'.join(f"{100*c['linked_vs_HEFT_reduction_fraction']:.6f}%" for c in facts['cohorts'])
    linked=[r for r in facts['rows'] if r['method']=='anchor_linked4']
    energies='／'.join(f"{r['safe_U_J']:.12f}" for r in linked)
    count=review['count']
    core=(f"联动R1—R5的U为{energies} J，相对HEFT降低{percentages}；"
          f"{m['linked_strictly_lower_than_HEFT_count']}/5题严格更低，负值为更差。"
          f"HEFT在{m['HEFT_faster_than_linked_count']}/5题更快；"
          f"第二阶段{m['linked_second_phase_strictly_improved_count']}/5题有严格改善。")
    bounds=(f"保存热违规{m['thermal_violation_saved_rows']}／反馈{m['thermal_feedback_saved_rows']}；"
            f"独立全域最优{m['independent_optimal_count']}／无解{m['independent_infeasible_count']}，"
            f"L0高于U异常{m['independent_bound_anomalies']}。"
            'solver-reported和局部状态不升级为全域证明，未新增扫描或认证工作。')
    budget=(f"预留12000方法秒，实际根时钟合{m['root_time_sum_s']:.3f}秒；"
            f"从本批启动至终态日历{m['calendar_from_P1_launch_s']:.3f}秒＜19200秒。"
            '启动／构模／求解／内部连续复核全部计费，停止延迟与各一次post另列；'
            '预算后新U未接纳，不补跑／延时。')
    brief=(f"**K.158完成／D183：P1 response_R共40/40次完成，40份最终方案均SAFE（E603执行补充）。** "
           f"185项必要预检、14项冻结核对及{count}项终态存档核查通过；211源／输入保持，"
           '无技术故障、无补跑，worker／process均COMPLETED。'
           '[结果与图](research/chapter3_experiments/results/p1_execution01/summary.md)、'
           '[40次CSV](research/chapter3_experiments/results/p1_execution01/analysis01/results40.csv)、'
           '[存档核查](research/chapter3_experiments/results/p1_execution01/record_review01.json)已存。\n\n'
           +core+'\n\n'+bounds+budget+'\n\n'
           'P1是共同真实响应输入α=1的对照条件；与P0不同问题，不把两批能量差称为共同评价下的建模节能收益。'
           'SA101—105逐次及分布保留，不作五取一等预算排名；固定五变体及单次确定性运行不外推稳定性。'
           '本阶段结束，下一项先审阅本组正反结果，再确认后续既定条件及预算；不自动启动其他批。\n\n')
    p=REPO/'RESEARCH_BRIEF.md'
    insert_before(p, '**K.158／D183：', brief)
    data=p.read_bytes();data=data.replace('更新：2026-10-21。'.encode(), '更新：2026-10-22。'.encode(), 1)
    data=data.replace('**K.158／D183：P1统一'.encode(), '**K.158冻结历史／D183：P1统一'.encode(), 1)
    data=data.replace('**D183：用户已单独批准'.encode(), '**D183授权历史：用户已单独批准'.encode(), 1)
    p.write_bytes(data)
    evidence=(f"\n\n**E603执行补充（2026-10-22，K.158完成）：** 冻结提交324e04b后按用户已确认预算，"
              f"40槽全部完成、各一次300秒接纳窗口、各最终SAFE一次60秒post；40份最终输出全部SAFE。"
              f"{count}项纯存档核查全部通过，211源／五输入及P0关键工件保持，claims一次消费，"
              '无方法重跑、后改参数、技术故障或预算外新U。外部自动审查仍暂停，当前为本会话已存证据核查。\n\n'
              +core+'\n\n'+budget+bounds+'\n\n'
              '完整[结论与图](chapter3_experiments/results/p1_execution01/summary.md)、'
              '[40次CSV](chapter3_experiments/results/p1_execution01/analysis01/results40.csv)、'
              '[终态核查](chapter3_experiments/results/p1_execution01/record_review01.json)、'
              '阶段／启动／首次SAFE与严格改善、SA五次分布及原始安排／界／回执归档。'
              'P0/P1分别是真实输入H/R，不把跨条件差异当共同评价模型下的响应误差损失；'
              '不据一次运行作统计稳定性或普遍优势判断。MAT本地保留哈希，不强制上传。'
              '本批结束，其他条件／新增调用尚未授权。\n')
    p=REPO/'research/03_证据与检索记录.md'
    with p.open('ab') as stream:stream.write(evidence.encode('utf-8'))
    section=(f"## K.158完成：P1响应组40次及正反结果\n\n"
             f"40/40次完成，最终40份SAFE；185项预检、14项冻结核对及{count}项终态存档核查通过。"
             '211源／输入保持，无补跑、故障或范围变更。'
             '[结果与图](chapter3_experiments/results/p1_execution01/summary.md)、'
             '[CSV](chapter3_experiments/results/p1_execution01/analysis01/results40.csv)已存。\n\n'
             +core+'\n\n'+budget+bounds+'\n\n'
             'P1只改变各方法共同使用的真实响应输入，不直接验证统一1/f误用带来的损失。'
             'SA逐次与五种子分布完整保留，五次最优不是一次同预算竞争者。'
             '下一批未授权，先审阅本组结果，再确认既定条件及预算；不新增算法／温度扫描或恢复115次。\n\n')
    p=REPO/'research/第三章当前进展与正式实验推进计划_审查稿.md'
    insert_before(p, '## K.158：P1响应组已授权并完成执行准备', section)
    data=p.read_bytes()
    old='| 状态 | K.156完成P0；K.157完成R3只读归因与四类条件草案，下一批未授权或执行 |'
    new='| 状态 | K.156完成P0；K.157完成R3只读归因；K.158完成已单独授权的P1 40次，其他批未授权 |'
    assert old.encode() in data;data=data.replace(old.encode(),new.encode(),1)
    old='| 本轮边界 | 仅原剩余37次，各300秒；前三次不重跑，原模型／参数／安全不变；后续批未启动，两档无NPU联动仍后置 |'
    new='| 本轮边界 | P1 response_R R1—R5共40次，各300秒，已完成；原方法／功热及安全保持，后续批未启动，两档无NPU联动仍后置 |'
    assert old.encode() in data;data=data.replace(old.encode(),new.encode(),1)
    p.write_bytes(data)
    print({'updated':3,'new_research_calls':0,'new_thermal_evaluations':0})


if __name__=='__main__':main()
