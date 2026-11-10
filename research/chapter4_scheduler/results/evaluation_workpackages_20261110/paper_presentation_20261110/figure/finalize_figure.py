"""Read saved evidence and seal figure delivery. No numerical thermal call."""
from datetime import datetime, timezone
from fractions import Fraction as F
import csv
import hashlib
import json
from pathlib import Path
from run_figure_points import verify

OUT = Path(__file__).resolve().parent
C = OUT.parent.parent / 'workpackage_C'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def save(name, value):
    with (OUT / name).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

plan = read(OUT / 'plan.json')
identity = read(OUT / 'plan_identity.json')['sha256']
verify(plan, identity)
old_manifest = read(OUT / 'figure_manifest.json')
v1_snapshot_differences = {p: {'snapshot_sha256': h, 'final_sha256': sha(OUT / p)} for p, h in old_manifest['files_sha256'].items() if sha(OUT / p) != h}
assert set(v1_snapshot_differences) == {'render_stdout.log'}
assert v1_snapshot_differences['render_stdout.log']['snapshot_sha256'] == hashlib.sha256(b'').hexdigest()
c_manifest = read(C / 'C_final_manifest.json')
assert all(sha(C / p) == h for p, h in c_manifest['files_sha256'].items())
summary = read(OUT / 'point_run01/summary.json')
audit = read(OUT / 'figure_audit.json')
refs = read(OUT / 'frozen/C_reference_data.json')
assert summary['actual_original_kernel_calls'] == 10
assert summary['complete_all_calls'] and audit['passed']
assert summary['new_scheduling_search_calls'] == 0
with (OUT / 'display_curves_AB_NPU0.csv').open() as f:
    display_rows = list(csv.DictReader(f))
assert len(display_rows) == audit['display_point_rows']
for version in ['v2', 'v3']:
    record = read(OUT / ('layout_' + version + '_record.json'))
    assert record['input_CSV_sha256'] == sha(OUT / 'display_curves_AB_NPU0.csv')
    assert record['new_original_kernel_calls'] == 0
    assert all(sha(OUT / ('AB_NPU0_startup_and_periodic_' + version + '.' + ext)) == h
               for ext, h in record[version + '_sha256'].items())

new_witnesses = []
for period, expected_time, cycle in [(75, F(393, 250), 21), (80, F(231, 100), 29)]:
    receipt = read(OUT / f'point_run01/startup_P{period}_receipt.json')
    witness = receipt['violations'][0]
    assert F(witness['time_s']) == expected_time
    assert witness['node'] == 'NPU0'
    assert F(witness['temperature_degC'][0]) > 80
    assert int(expected_time / (F(period) / 1000)) + 1 == cycle
    old_witness = refs[f'startup_P{period}']['C_result']['violation_witness']
    assert F(old_witness['global_time_s']) > expected_time
    new_witnesses.append({
        'period_ms': period, 'scene': 'AB', 'node': 'NPU0',
        'new_earlier_point_witness': witness,
        'original_C_point_kept_in_figure': old_witness,
        'cycle_number_one_based_for_both_witnesses': cycle,
        'interpretation': 'Earlier certified sampled-point violation, not exact first crossing; original C remains unchanged',
    })
save('figure_evidence_addendum.json', {
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Read-only examination of the ten already saved plotting receipts',
    'additional_original_kernel_calls': 0,
    'earlier_point_witnesses': new_witnesses,
    'C_original_manifest_sha256': sha(C / 'C_final_manifest.json'),
    'C_original_manifest_all_304_entries_unchanged': True,
    'original_C_call_count_unchanged': 242,
    'figure_new_original_kernel_calls_separately_counted': 10,
    'original_model_domain_all_four_nodes_all_ten_calls': '20..100 degC certified by original receipt minimum/maximum enclosures',
    'unsafe_continuation': 'Fixed-period model diagnostic without thermal protection or shutdown; not safe execution advice',
    'sample_connection': 'At most 2 ms gaps; midpoint display and straight lines do not certify extrema between samples',
    'independent_implementation_certificate': False,
})

caption = ('固定调度下AB场景NPU0的温度变化。左图将原全H模板按75、80、85和90 ms周期重复，'
           '从50°C初温连续传播至3 s，轮间继承末温；标记为既有连续热评价确证的两个越限点。'
           '右图比较90 ms周期下全H模板、增强HEFT终解和MILP终解的周期稳态轨迹，采用已包围的周期入口状态，'
           '不从50°C重新启动。HEFT与MILP曲线近乎重合，未人为偏移温度。'
           '曲线连接最大间隔2 ms的区间采样点中值，连线及图形最大点不替代连续峰温包围或安全证明。'
           '越限后的延续为未实施热保护或关停策略的模型诊断轨迹，四节点整条轨迹均在原20–100°C有效域内。')
technical = '''
技术说明：图中只显示AB场景NPU0，不代替其他场景或节点的检查。三个固定模板、时间表、频档、功率、泄漏系数和80°C温限均未改动。左图3 s是观测窗口，P=80/85/90 ms时最后一轮被窗口截断；此前任务段与空闲段均完整保留。右图由既有周期入口盒的下、上端各传播一次，逐点取下路径下界和上路径上界，图中画其中值。

图中1.575 s和2.315 s标记来自既有连续热评价记录，对应75 ms的第21轮、80 ms的第29轮。新增2 ms绘图点已在同两轮得到更早的确证点：1.572 s处温度下界80.028711872535°C、2.310 s处下界80.041475928262°C。四个时刻都不是精确首次穿越时刻；原周期表和证据未回写。完整区间见figure_evidence_addendum.json及point_run01原始收据。

连续安全、周期稳态峰温及无限轮保守界仍引用../../workpackage_C/中的固定方案证据，本图不提供独立实现证书，也不把采样最大值当连续峰值。新增10次原核调用仅用于固定方案后验绘图，原周期工作包的242次调用数不变。最终图为AB_NPU0_startup_and_periodic_v3.png/.svg/.pdf；v1/v2和v3排版初稿保留。
'''
(OUT / 'caption_v3.md').write_text(caption + '\n\n' + technical)
(OUT / 'caption_v3.tex').write_text('\\caption{' + caption.replace('°C', '$^\\circ$C') + '}\n')
wrapper = read(OUT / 'point_command_return.json')
started = read(OUT / 'point_command_started.json')
lines = [
    '最终论文图：AB_NPU0_startup_and_periodic_v3.png、.svg、.pdf；中文图注及技术说明见caption_v3.md，LaTeX图注见caption_v3.tex。',
    '数值计划SHA256：' + identity + '。最终v3、历史v1/v2及排版初稿均保留；冻结科学代码未改。',
    f"原核批次：{summary['started_utc']}至{summary['ended_utc']}；内部批次{summary['wall_s']:.9f} s，命令包装{wrapper.get('wall_s', wrapper.get('elapsed_s', 'see point_command_return.json'))} s。",
    '实际命令：' + ' '.join(started['argv']) + '；工作目录/workspace/paper。',
    '恰10次原核调用，4次启动全历史和6次稳态盒上下传播，均完整；8 SAFE、2 THERMAL_VIOLATION、0失败/重试；0调度搜索。原C 242次计数不变。',
    '原核逐时刻四节点向量6396个、全节点CSV行25584条、最终AB/NPU0显示点6254个。拆段与来源等630项自动断言通过；另以哈希核对原C清单304项未变；历史v1清单仅render_stdout.log在快照后的原程序收尾打印不同，科学数据、图与代码均未变。',
    '所有新增核轨迹四节点的连续最小/最大包围均在20..100°C；P75/P80越限后的3s延续只是未实施热保护/关停的固定模型诊断。',
    '两个新增更早点见证为P75的1.572s、P80的2.310s，仍在21/29轮。原图标记1.575/2.315s继续保留；均非精确首次穿越，详见figure_evidence_addendum.json。',
    '原始点与区间：raw_plot_points_all_nodes.csv；绘图曲线：display_curves_AB_NPU0.csv；细分时间表和原C入口盒：frozen/；原收据/逐调用时间：point_run01/。',
    '命令与日志：point_command_started/return.json、point_stdout/stderr.log；原630项审计figure_audit.json；v1绘图render_*、v2/v3独立CSV排版layout_v2/v3_*。',
    'v2/v3及v3初稿均仅重读相同CSV，0新核调用。右图例移开高温曲线；左标点文本移到空白区并换行。未偏移/缩放任何温度。根与数学审阅目视确认最终分行版无遮挡。',
    'v1 Matplotlib对默认缓存无写权限，自动使用临时缓存，图像成功输出；v2/v3显式使用可写临时缓存。没有依赖安装、推送或合并。',
    '共享原评价内核复核，不是独立实现证书；2ms采样连线不替代连续证据。原400ms输入上的合法固定时间表未重建，绘图周期是已有九配置中的选定子集。',
    '最终清单figure_final_manifest.json覆盖全部交付工件（排除自身及Python缓存）。figure_manifest.json保留为未改的v1历史快照；它在程序收尾打印前对render_stdout.log记录了空日志哈希，最终日志以本清单为准。',
]
(OUT / 'README_delivery.md').write_text('\n\n'.join(lines) + '\n')
save('figure_final_readonly_audit.json', {
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'frozen_figure_plan_and_sources_unchanged': True,
    'historical_v1_manifest_entries_examined': len(old_manifest['files_sha256']),
    'historical_v1_snapshot_difference': v1_snapshot_differences,
    'v1_difference_explanation': 'The original renderer wrote its manifest before final stdout printing. Only that formerly empty stdout log changed; scientific data, images and code all match the historical snapshot.',
    'C_manifest_entries_verified': len(c_manifest['files_sha256']),
    'original_automatic_assertions_passed': audit['assertion_count'],
    'new_kernel_calls_for_finalization': 0,
    'saved_CSV_unchanged_through_layouts': True,
    'final_artifacts': ['AB_NPU0_startup_and_periodic_v3.' + e for e in ['png', 'svg', 'pdf']],
    'caption_file': 'caption_v3.md',
    'initial_v3_draft_kept_separately': True,
})
files = sorted(p for p in OUT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'figure_final_manifest.json')
save('figure_final_manifest.json', {
    'completed_utc': datetime.now(timezone.utc).isoformat(),
    'plan_sha256': identity,
    'final_figure_version': 'v3, line-wrapped violation labels',
    'original_kernel_calls': 10, 'new_scheduling_search_calls': 0,
    'postprocessing_new_kernel_calls': 0,
    'independent_implementation_certificate': False,
    'files_sha256': {str(p.relative_to(OUT)): sha(p) for p in files},
    'exclusions': ['figure_final_manifest.json itself', '__pycache__ caches'],
    'pushed': False, 'merged': False,
})
print(json.dumps({'files_sealed': len(files), 'original_kernel_calls': 10, 'new_calls': 0, 'final_png_sha256': sha(OUT / 'AB_NPU0_startup_and_periodic_v3.png')}, indent=2))
