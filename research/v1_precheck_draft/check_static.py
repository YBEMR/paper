"""V1草案的静态/闭式代数检查；不是调度器或热仿真器。仅使用Python标准库。"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import hashlib
import json
from pathlib import Path
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(package):
    inputs = package / 'inputs.json'
    expected = package / 'expected.json'
    x = json.loads(inputs.read_text(encoding='utf-8'), parse_float=D)
    y = json.loads(expected.read_text(encoding='utf-8'), parse_float=D)
    plans = x['fixed_plans']
    traces = {t['id']: t for t in x['traces']}
    platform = x['platform']
    results = []

    def check(name, predicate):
        try:
            passed = bool(predicate())
            detail = '' if passed else '条件不成立；检查输入／预期或本检查的适用范围。'
        except Exception as exc:
            passed, detail = False, f'{type(exc).__name__}: {exc}'
        results.append({'name': name, 'passed': passed, 'detail': detail})

    def releases(tid):
        # 本夹具的单次转换已显式给定；只展开算术数列，不安排任何工作。
        t = traces[tid]
        if len(t['switch_requests']) != 1:
            raise ValueError('此预检的释放核对只适用单次转换。')
        sw = t['switch_requests'][0]
        old, new = t['initial_mode'], sw['to_mode']
        return ([(old, r) for r in range(t['initial_release_us'], sw['time_us'], plans[old]['period_us'])]
                + [(new, r) for r in range(sw['time_us'], t['window_us'], plans[new]['period_us'])])

    def spec(row):
        return next(s for s in plans[row['mode']]['stages'] if s['id'] == row['stage'])

    def schedule_ok(tid):
        rows = y['traces'][tid]['schedule_rows']
        groups = {}
        for r in rows:
            st = spec(r)
            if not (r['end_us'] - r['start_us'] == st['duration_us']
                    and r['start_us'] >= r['release_us']
                    and r['deadline_us'] == r['release_us'] + plans[r['mode']]['relative_deadline_us']
                    and (r['unit'], r['opp']) == (st['unit'], st['opp'])):
                return False
            groups.setdefault((r['mode'], r['release_us']), []).append(r)
        for (mode, release), rr in groups.items():
            if sorted(r['stage'] for r in rr) != sorted(s['id'] for s in plans[mode]['stages']):
                return False
            if len({r['start_us'] - spec(r)['offset_us'] for r in rr}) != 1:
                return False
            by_id = {r['stage']: r for r in rr}
            if any(by_id[p]['end_us'] > r['start_us'] for r in rr for p in spec(r)['predecessors']):
                return False
        for unit in platform['units']:
            rr = sorted((r for r in rows if r['unit'] == unit), key=lambda r: r['start_us'])
            if any(a['end_us'] > b['start_us'] for a, b in zip(rr, rr[1:])):
                return False
        wanted = releases(tid)
        if tid == 'F3':
            wanted = wanted[:wanted.index(('B', traces[tid]['switch_requests'][0]['time_us'])) + 1]
        return set(groups) == set(wanted)

    def energy_ok(tid):
        e = y['traces'][tid]
        rows = e['schedule_rows']
        activity = sum(D(spec(r)['activity_increment_W']) * (r['end_us'] - r['start_us']) / 1000000 for r in rows)
        base = {}
        for unit in platform['units']:
            last, opp, energy = 0, traces[tid]['initial_opps'][unit], D(0)
            for r in sorted((r for r in rows if r['unit'] == unit), key=lambda r: r['start_us']):
                energy += platform['opps'][unit][opp]['base_W'] * (r['start_us'] - last) / 1000000
                last, opp = r['start_us'], r['opp']
            energy += platform['opps'][unit][opp]['base_W'] * (traces[tid]['window_us'] - last) / 1000000
            base[unit] = energy
        ext = platform['external_power_W'] * traces[tid]['window_us'] / 1000000
        return (activity == e['activity_energy_J'] and base['C0'] == e['CPU_base_energy_J']
                and base['N0'] == e['NPU_base_energy_J'] and ext == e['external_energy_J']
                and activity + sum(base.values()) + ext == e['nonleak_energy_J']
                and e['CPU_opp_switch_us'] == min(r['start_us'] for r in rows if r['unit'] == 'C0' and r['opp'] == 'L'))

    def bound_ok():
        g = platform['G_W_per_K']
        if platform['ambient_C'] != 25 or platform['leak_reference_C'] != 25:
            return False  # 下面是已声明的[25,59]矩形特例，不默默扩展公式。
        for n, node in enumerate(platform['nodes']):
            unit = next(u for u, v in platform['units'].items() if v['node'] == node)
            # 此夹具每热节点只有一个互斥执行单元。
            if sum(v['node'] == node for v in platform['units'].values()) != 1:
                return False
            q = max(D(s['activity_increment_W']) for plan in plans.values() for s in plan['stages'] if s['unit'] == unit)
            for v in platform['opps'][unit].values():
                if v['base_W'] + q + v['leak_W_per_K'] * 34 - sum(g[n]) * 34 > 0:
                    return False
        return all(all(25 <= t <= 59 for t in tr['initial_temperature_C']) for tr in traces.values())

    def leakage_bound(tid):
        return sum(max(v['leak_W_per_K'] for v in opps.values()) for opps in platform['opps'].values()) * 34 * traces[tid]['window_us'] / 1000000

    check('01 JSON版本和固定预检范围', lambda: x['version'] == y['version'] == 'V1-precheck-draft-1')
    check('02 权重及正向路径集合', lambda: sum(x['usage_aggregation_probe']['weights']) == 1
          and all(w >= 0 for w in x['usage_aggregation_probe']['weights'])
          and x['usage_aggregation_probe']['trace_ids'] == ['F1', 'F2'])
    for mode in ['A', 'B']:
        p = plans[mode]
        check(mode + ' 周期／期限／间隔', lambda p=p: 0 < p['relative_deadline_us'] <= p['period_us'] <= p['minimum_switch_interval_us'])
        check(mode + ' 固定偏移／依赖／模式', lambda p=p: all(
            s['duration_us'] > 0 and s['offset_us'] >= 0 and s['opp'] in platform['opps'][s['unit']]
            and all(next(t for t in p['stages'] if t['id'] == pred)['offset_us']
                    + next(t for t in p['stages'] if t['id'] == pred)['duration_us'] <= s['offset_us'] for pred in s['predecessors'])
            for s in p['stages']))
    for tid in ['F1', 'F2', 'F3']:
        check(tid + ' 手写时间表／释放／依赖／资源', lambda tid=tid: schedule_ok(tid))
        e = y['traces'][tid]
        if tid != 'F3':
            check(tid + ' 期限／窗口', lambda tid=tid, e=e: all(r['end_us'] <= r['deadline_us'] <= traces[tid]['window_us'] for r in e['schedule_rows']))
            check(tid + ' 分项能量及空闲工作点', lambda tid=tid: energy_ok(tid))
            check(tid + ' 漏电粗界', lambda tid=tid, e=e: bound_ok()
                  and e['total_energy_algebraic_enclosure_J'] == [e['nonleak_energy_J'], e['nonleak_energy_J'] + leakage_bound(tid)])
        else:
            check('F3 原期限真实违规', lambda e=e: e['predicted_finish_us'] == max(r['end_us'] for r in e['schedule_rows'] if r['mode'] == 'B')
                  and e['failed_deadline_us'] == e['failed_release_us'] + plans['B']['relative_deadline_us']
                  and e['predicted_finish_us'] - e['failed_deadline_us'] == e['lateness_us'] == 1000
                  and not e['rankable_energy'])
    check('F4 W1不相容', lambda: y['traces']['F4']['input_status'] == 'W1_incompatible'
          and any(r < traces['F4']['window_us'] < r + plans[m]['relative_deadline_us'] for m, r in releases('F4')))
    check('窗内释放和同刻转换', lambda: all(r + plans[m]['relative_deadline_us'] <= traces[t]['window_us'] for t in ['F1', 'F2', 'F3'] for m, r in releases(t))
          and ('A', traces['F2']['switch_requests'][0]['time_us']) not in releases('F2'))
    check('加权非漏电能量及粗界', lambda: sum(y['traces'][t]['nonleak_energy_J'] * w for t, w in zip(x['usage_aggregation_probe']['trace_ids'], x['usage_aggregation_probe']['weights'])) == y['weighted_nonleak_energy_J']
          and all(sum(y['traces'][t]['total_energy_algebraic_enclosure_J'][k] * w for t, w in zip(x['usage_aggregation_probe']['trace_ids'], x['usage_aggregation_probe']['weights'])) == y['weighted_total_energy_algebraic_enclosure_J'][k] for k in [0, 1]))
    g = platform['G_W_per_K']
    check('被动RC／稳定性／有效温区功率', lambda: all(c > 0 for c in platform['C_J_per_K'])
          and g[0][1] == g[1][0] <= 0
          and all(g[n][n] - v['leak_W_per_K'] > abs(g[n][1-n])
                  and v['leak_W_per_K'] >= 0
                  and v['base_W'] + v['leak_W_per_K'] * (platform['valid_temperature_C'][0] - platform['leak_reference_C']) >= 0
                  for n, u in enumerate(['C0', 'N0']) for v in platform['opps'][u].values()))
    check('共同矩形温度充分界', bound_ok)

    def scalar_ok(v, ref):
        c, g, lam = v['C_J_per_K'], v['ambient_conductance_W_per_K'], v['leak_W_per_K']
        if not c > 0 or not g > lam >= 0:
            return False
        h = D(v['duration_us']) / 1000000
        a = (g - lam) / c
        eq = (g * v['ambient_C'] + v['base_W'] + v['activity_increment_W'] - lam * v['leak_reference_C']) / (g - lam)
        decay = (-a * h).exp()
        end = eq + (v['initial_temperature_C'] - eq) * decay
        energy = (v['base_W'] + v['activity_increment_W']) * h + lam * ((eq - v['leak_reference_C']) * h + (v['initial_temperature_C'] - eq) * (1-decay) / a)
        return (abs(end - ref['end_temperature_C_display']) < D('1e-12')
                and abs(energy - ref['node_energy_J_display']) < D('1e-15')
                and abs(energy + v['external_power_W'] * h - ref['system_energy_J_display']) < D('1e-15')
                and max(end, v['initial_temperature_C']) <= v['temperature_limit_C'])

    with localcontext() as ctx:
        ctx.prec = 60
        for v, ref in zip(x['thermal_primitives'][:3], y['thermal_primitives'][:3]):
            check(v['id'] + ' 单节点闭式参考', lambda v=v, ref=ref: scalar_ok(v, ref))

        def interior_ok():
            v, r = x['thermal_primitives'][3], y['thermal_primitives'][3]
            c = v['C_J_per_K']; g = v['G_W_per_K']; b = v['base_W']; lam = v['leak_W_per_K']
            if not (c[0] == c[1] > 0 and g[0][0] == g[1][1] and g[0][1] == g[1][0] < 0
                    and b[0] == b[1] and lam[0] == lam[1] and v['activity_increment_W'] == [0, 0]
                    and v['ambient_C'] == v['leak_reference_C']):
                return False
            ambient = v['ambient_C']; common = (sum(g[0]) - lam[0]) / c[0]
            difference = (g[0][0] - g[0][1] - lam[0]) / c[0]
            eq = b[0] / (c[0] * common)
            a = sum(D(t) for t in v['initial_temperature_C']) / 2 - ambient - eq
            d = D(v['initial_temperature_C'][0] - v['initial_temperature_C'][1]) / 2
            t = (difference * d / (common * a)).ln() / (difference - common)
            temp = lambda t: ambient + eq + a * (-common*t).exp() - d * (-difference*t).exp()
            h = D(v['duration_us']) / 1000000; limit = v['temperature_limit_C'][1]
            return (0 < t < h and temp(D(0)) < limit and temp(h) < limit < temp(t)
                    and abs(t-r['NPU_peak_time_s_display']) < D('1e-12')
                    and abs(temp(t)-r['NPU_peak_C_display']) < D('1e-12')
                    and abs(temp(h)-r['NPU_end_C_display']) < D('1e-12'))
        check('H4 双节点段内峰值闭式参考', interior_ok)
    for probe in x['judgement_probes']:
        def judge(p=probe):
            lo, hi = p['supplied_enclosure_C']; limit = p['limit_C']
            return lo <= hi and ('safe' if hi <= limit else 'violation' if lo > limit else 'unresolved') == p['expected']
        check(probe['id'] + ' 区间状态分类', judge)

    manifest = package / 'SHA256SUMS.txt'
    files = {}
    manifest_ok = True
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        path = package / name
        # 不执行或修改清单内容，也不允许清单引用包外文件。
        if Path(name).name != name or not path.is_file():
            manifest_ok = False
            continue
        files[name] = sha(path)
        manifest_ok = manifest_ok and files[name] == digest
    required = {'inputs.json', 'expected.json', 'check_static.py'}
    manifest_ok = manifest_ok and required <= files.keys() and files.get('check_static.py') == sha(Path(__file__))
    return {'schema': 'V1-static-report-1', 'utc_time': datetime.now(timezone.utc).isoformat(),
            'python': sys.version, 'checker_sha256': sha(Path(__file__)), 'manifest_sha256': sha(manifest),
            'checked_file_sha256': files, 'manifest_matches': bool(manifest_ok),
            'checks': results, 'passed_count': sum(c['passed'] for c in results), 'total_count': len(results),
            'passed': bool(manifest_ok and len(results) == 28 and all(c['passed'] for c in results)),
            'scope': 'static and closed-form algebra only; no evaluator, ODE integration or safety certification'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--output', type=Path, help='另存带哈希的JSON记录；已有文件拒绝覆盖')
    args = ap.parse_args()
    try:
        report = run(args.package.resolve())
    except Exception as exc:
        report = {'passed': False, 'error': f'{type(exc).__name__}: {exc}'}
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as f:
            f.write(text)
    print(text)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
