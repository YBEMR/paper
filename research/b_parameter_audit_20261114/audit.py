"""Read-only audit of fixed public LoudVA artifacts; never executes author code."""
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'
OUT.mkdir(exist_ok=True)
MANIFEST = json.loads((ROOT / 'source_manifest.json').read_text(encoding='utf-8'))
BY_PATH = {e['path']: e for e in MANIFEST}

def source(path):
    e = BY_PATH[path]
    raw = (ROOT / e['local_path']).read_bytes()
    sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    assert sha == e['git_blob_sha'], path
    assert hashlib.sha256(raw).hexdigest() == e['sha256'], path
    return raw.decode('utf-8')

def rows(path, delimiter=','):
    return [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(source(path)), delimiter=delimiter)]

def write_csv(name, records):
    assert records
    with (OUT / name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)

def numeric(v):
    return float(v.replace(',', '.'))

# Exact same-device/frequency joins; concurrency remains concurrency.
prefix = 'measurements/archive/Representative/agx-xavier-00/measurements/'
profile = []
residuals = []
for path in sorted(p for p in BY_PATH if p.startswith(prefix + 'energy/freqs/')):
    freq = int(re.search(r'freq_(\d+)', path).group(1))
    perf_path = prefix + f'performance/freqs/performance_measurements_freq_{freq}.csv'
    power_path = prefix + f'power/freqs/power_measurement_stats_freq_{freq}.csv'
    energy, perf = rows(path), rows(perf_path)
    power = [float(x.split(':')[1]) / 1000 for x in source(power_path).splitlines() if x.strip()]
    assert len(energy) == len(perf) == len(power), freq
    for e, p, w in zip(energy, perf, power):
        energy_label = int(e['Concurrency'])
        c = int(p['Concurrency'])
        latency = sum(float(p[k]) for k in ['Server Queue', 'Server Compute Input', 'Server Compute Infer', 'Server Compute Output']) * 1e-6
        q = float(p['Inferences/Second'])
        reported_e = float(e['Energy (J)'])
        residuals.append({'frequency_Hz': freq, 'concurrency': c, 'power_residual_W': float(e['Mean Power (W)']) - w, 'latency_residual_s': float(e['Avg Latency (s)']) - latency, 'energy_residual_J': reported_e - w * latency, 'throughput_residual_per_s': float(e['Throughput (Inference/sec)']) - q})
        profile.append({'frequency_Hz': freq, 'concurrency_NOT_batch': c, 'energy_table_enumerated_label': energy_label, 'label_matches_performance': energy_label == c, 'power_alignment': 'positional_only_no_configuration_ID_in_power_file', 'rail_sum_mean_W': w, 'server_latency_including_queue_s': latency, 'server_queue_s': float(p['Server Queue']) * 1e-6, 'server_infer_s': float(p['Server Compute Infer']) * 1e-6, 'throughput_inferences_per_s': q, 'reported_P_times_L_J': reported_e, 'steady_state_P_over_throughput_J_per_inference_PROXY': w / q, 'P_L_to_P_Q_ratio': latency * q, 'source_energy_path': path})
write_csv('agx_profile_audited.csv', profile)
write_csv('formula_residuals.csv', residuals)
index = {(r['frequency_Hz'], r['concurrency_NOT_batch']): r for r in profile}
pairs = []
for freq in sorted({r['frequency_Hz'] for r in profile}):
    a, b = index[(freq, 1)], index[(freq, 2)]
    pairs.append({'frequency_Hz': freq, 'c1_server_latency_ms': a['server_latency_including_queue_s'] * 1000, 'c2_server_latency_ms': b['server_latency_including_queue_s'] * 1000, 'c1_power_W': a['rail_sum_mean_W'], 'c2_power_W': b['rail_sum_mean_W'], 'c1_reported_energy_J': a['reported_P_times_L_J'], 'c2_reported_energy_J': b['reported_P_times_L_J'], 'c1_steady_state_proxy_J_per_inference': a['steady_state_P_over_throughput_J_per_inference_PROXY'], 'c2_steady_state_proxy_J_per_inference': b['steady_state_P_over_throughput_J_per_inference_PROXY'], 'c2_vs_c1_proxy_change_pct': 100 * (b['steady_state_P_over_throughput_J_per_inference_PROXY'] / a['steady_state_P_over_throughput_J_per_inference_PROXY'] - 1), 'NOT_valid_single_batch_pair': True})
write_csv('concurrency_1_2_diagnostic_NOT_batch.csv', pairs)
merged = rows('measurements/archive/Representative/Profiling.csv')
agx_merged = [r for r in merged if r['Directory'] == 'AGX']
assert len(agx_merged) == len(profile)
label_index = {(r['frequency_Hz'], r['energy_table_enumerated_label']): r for r in profile}
for m in agx_merged:
    p = label_index[(int(m['Frequency']), int(m['Batch Size']))]
    assert math.isclose(float(m['Energy']), p['reported_P_times_L_J'], rel_tol=1e-12)
    assert math.isclose(float(m['Latency']), p['server_latency_including_queue_s'], rel_tol=1e-12)

# Summaries are not assumed to be independent repetitions.
report_summary, report_records = [], []
for path in sorted(p for p in BY_PATH if re.search(r'experiment_report(?:4)?\.csv$', p)):
    rr = rows(path, ';' if 'Experiment_5' in path else ',')
    for r in rr:
        report_records.append((path, r))
    report_summary.append({'path': path, 'rows': len(rr), 'devices': sorted({r.get('device', 'not_in_table') for r in rr}), 'batch_settings': sorted({r.get('batch_size', '') for r in rr}), 'scenario_ids': sorted({r.get('experiment_id', r.get('scenario_id')) for r in rr}), 'temperature_present': 'mean_temperature_c' in rr[0]})
exp1 = [(p, r) for p, r in report_records if 'Experiment_1' in p]
unique_records = {json.dumps(r, sort_keys=True) for _, r in exp1}
request_metric_mismatches = sum(not math.isclose(numeric(r['requests_per_joule']), numeric(r['num_requests']) / numeric(r['total_energy_j']), rel_tol=1e-9, abs_tol=1e-12) for _, r in exp1)
frame_metric_matches = sum(math.isclose(numeric(r['frames_per_joule']), numeric(r['num_frames']) / numeric(r['total_energy_j']), rel_tol=1e-9, abs_tol=1e-12) for _, r in exp1)
report00 = {r['experiment_type']: r for p, r in exp1 if '/experiment_results_00/' in p and r['experiment_id'] == '3'}

# All nine schedulers in the protocol's selected id3 scene.
tegra_records, log_summary, request_summary = [], [], []
rails = ['GPU', 'CPU', 'SOC', 'CV', 'VDDRQ', 'SYS5V']
for path in sorted(p for p in BY_PATH if p.endswith('_tegrastats')):
    scheduler = path.split('/')[-2]
    lines = source(path).splitlines()
    run = []
    for i, line in enumerate(lines):
        wall = datetime.strptime(line[:19], '%m-%d-%Y %H:%M:%S')
        d = {'scheduler': scheduler, 'row_index': i, 'wall_time_no_timezone': wall.isoformat(), 'nominal_time_s_NOT_measured': i * 0.2}
        for rail in rails:
            match = re.search(r'\b' + rail + r' (\d+)mW/(\d+)mW', line)
            assert match, (path, i, rail)
            d[rail + '_W'] = int(match.group(1)) / 1000
        for sensor in ['CPU', 'GPU', 'thermal', 'Tboard']:
            match = re.search(r'\b' + sensor + r'@([\d.]+)C', line)
            assert match, (path, i, sensor)
            d[sensor + '_temperature_C'] = float(match.group(1))
        freq = re.search(r'GR3D_FREQ\s+(\d+)%@(\d+)', line)
        assert freq, (path, i)
        d['GPU_utilization_pct'], d['GPU_frequency_MHz'] = map(int, freq.groups())
        d['rail_sum_W'] = sum(d[k + '_W'] for k in rails)
        run.append(d)
    tegra_records.extend(run)
    times = [datetime.fromisoformat(r['wall_time_no_timezone']) for r in run]
    dt = [(b-a).total_seconds() for a,b in zip(times,times[1:])]
    assert all(t >= 0 for t in dt)
    calc_e = sum(r['rail_sum_W'] * 0.2 for r in run)
    reported_e = float(report00[scheduler]['total_energy_j'])
    rq_path = next(p for p in BY_PATH if p.startswith('/'.join(path.split('/')[:-1]) + '/') and p.endswith('_request_log.csv'))
    rq = rows(rq_path)
    arrival = [float(r['Arrival Time']) for r in rq]
    completion = [float(r['Completion Time']) for r in rq if r['Completion Time']]
    group = Counter(r['Queue Exit Time'] for r in rq if r['Queue Exit Time'])
    # Offsets that permit the request window to lie within the logging window.
    # These are candidate hour offsets, not a synchronization calibration.
    first_epoch = datetime.fromtimestamp(min(arrival), timezone.utc).replace(tzinfo=None)
    last_epoch = datetime.fromtimestamp(max(completion), timezone.utc).replace(tzinfo=None)
    offset_candidates = [h for h in range(-14, 15) if times[0] <= first_epoch + timedelta(hours=h) and last_epoch + timedelta(hours=h) <= times[-1] + timedelta(seconds=1)]
    log_summary.append({'scheduler': scheduler, 'samples': len(run), 'nominal_interval_s_UNVERIFIED': 0.2, 'recorded_span_s': (times[-1]-times[0]).total_seconds(), 'mean_interval_from_endpoints_s': (times[-1]-times[0]).total_seconds() / (len(run)-1), 'zero_timestamp_steps': sum(d == 0 for d in dt), 'one_second_steps': sum(d == 1 for d in dt), 'larger_steps': sum(d > 1 for d in dt), 'GPU_T_min_C': min(r['GPU_temperature_C'] for r in run), 'GPU_T_max_C': max(r['GPU_temperature_C'] for r in run), 'CPU_T_min_C': min(r['CPU_temperature_C'] for r in run), 'CPU_T_max_C': max(r['CPU_temperature_C'] for r in run), 'rail_sum_min_W': min(r['rail_sum_W'] for r in run), 'rail_sum_max_W': max(r['rail_sum_W'] for r in run), 'GPU_zero_power_rows': sum(r['GPU_W'] == 0 for r in run), 'GPU_frequency_values_MHz': '|'.join(map(str, sorted({r['GPU_frequency_MHz'] for r in run}))), 'fixed_200ms_integral_J': calc_e, 'source_report_energy_J': reported_e, 'integral_residual_J': calc_e-reported_e, 'candidate_hour_offsets_NOT_verified': '|'.join(map(str, offset_candidates)), 'source_path': path})
    request_summary.append({'scheduler': scheduler, 'frame_rows': len(rq), 'unique_requests': len({r['Request ID'] for r in rq}), 'request_span_s': max(completion)-min(arrival), 'requested_latency_min_s': min(float(r['Requested Latency']) for r in rq), 'requested_latency_max_s': max(float(r['Requested Latency']) for r in rq), 'late_frames': sum(float(r['Latency']) > float(r['Requested Latency']) for r in rq), 'timed_out_frames': sum(r['Timed Out'].lower() == 'true' for r in rq), 'queue_exit_groups': len(group), 'group_size_min_PROXY_NOT_backend_batch': min(group.values()), 'group_size_max_PROXY_NOT_backend_batch': max(group.values()), 'frame_groups_size_1': sum(n == 1 for n in group.values()), 'frame_groups_size_2': sum(n == 2 for n in group.values()), 'source_path': rq_path})
write_csv('log_summary.csv', log_summary)
write_csv('request_summary.csv', request_summary)
write_csv('trace_excerpt_all_schedulers.csv', [r for r in tegra_records if r['row_index'] < 5])

summary = {
    'verification_scope': 'public_artifact_reanalysis_ONLY_no_hardware_no_thermal_calibration',
    'source_files_verified': len(MANIFEST),
    'profile': {'rows': len(profile), 'frequencies_Hz': sorted({r['frequency_Hz'] for r in profile}), 'concurrency_min': min(r['concurrency_NOT_batch'] for r in profile), 'concurrency_max': max(r['concurrency_NOT_batch'] for r in profile), 'merged_Batch_Size_equals_enumerated_energy_label_rows': len(agx_merged), 'energy_label_differs_from_raw_concurrency_rows': sum(not r['label_matches_performance'] for r in profile), 'mismatch_by_frequency_Hz': dict(Counter(str(r['frequency_Hz']) for r in profile if not r['label_matches_performance'])), 'max_abs_energy_formula_residual_J': max(abs(r['energy_residual_J']) for r in residuals), 'max_abs_latency_formula_residual_s': max(abs(r['latency_residual_s']) for r in residuals), 'max_abs_power_formula_residual_W': max(abs(r['power_residual_W']) for r in residuals), 'c1_c2_paired_frequencies': len(pairs), 'c1_server_latency_ms_range': [min(r['c1_server_latency_ms'] for r in pairs), max(r['c1_server_latency_ms'] for r in pairs)], 'c2_server_latency_ms_range': [min(r['c2_server_latency_ms'] for r in pairs), max(r['c2_server_latency_ms'] for r in pairs)], 'c1_c2_power_W_range': [min(min(r['c1_power_W'], r['c2_power_W']) for r in pairs), max(max(r['c1_power_W'], r['c2_power_W']) for r in pairs)], 'c2_vs_c1_proxy_change_pct_range': [min(r['c2_vs_c1_proxy_change_pct'] for r in pairs), max(r['c2_vs_c1_proxy_change_pct'] for r in pairs)]},
    'reports': report_summary,
    'exp1_total_rows': len(exp1), 'exp1_unique_full_records': len(unique_records), 'exp1_duplicate_full_records': len(exp1)-len(unique_records), 'exp1_requests_per_joule_mismatches': request_metric_mismatches, 'exp1_frames_per_joule_matches': frame_metric_matches,
    'logs': {'runs': len(log_summary), 'samples': len(tegra_records), 'GPU_T_range_C': [min(r['GPU_temperature_C'] for r in tegra_records), max(r['GPU_temperature_C'] for r in tegra_records)], 'timestamp_precision_s': 1, 'all_temperature_and_six_rail_fields_present': True, 'fixed_200ms_integration_max_abs_residual_J': max(abs(r['integral_residual_J']) for r in log_summary), 'clock_alignment_verified': False, 'power_gate_event_labels_present': False},
    'previous_synthetic_effect': {'cold_Q_minus_S_mJ': 1.2225585040675, 'warm_Q_minus_S_mJ': -1.1960717464395, 'ideal_two_state_gain_pct': 0.05949957224613, 'fixed_window_s': 0.4, 'warm_effect_equivalent_average_power_mW': 1.1960717464395 / 0.4, 'note': 'algebraic comparison only; not hardware detection limit'},
    'decision': {'performance_power_scale': 'CONDITIONAL_PROXY_ONLY', 'batch_1_2_table': 'NOT_IDENTIFIED_FROM_CONCURRENCY_PROFILE', 'thermal_RC_leakage_DPM_calibration': 'NOT_IDENTIFIED', 'temperature_dependent_policy_reversal': 'NOT_IDENTIFIED', 'next': 'simulation_parameter_identifiability_and_robustness_only_no_hardware_gate'}
}
(OUT / 'audit_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k != 'reports'}, ensure_ascii=False, indent=2))
