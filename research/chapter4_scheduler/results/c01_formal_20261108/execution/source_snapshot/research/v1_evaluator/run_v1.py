"""Run V1 finite-path prechecks; inputs stay unchanged; results never overwritten."""
import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from evaluate import load, encode, evaluate_trace, evaluate_primitive, coeff_matrix, thermal
from interval import I, Budget, TaylorPanel

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT.parent / 'v1_precheck_draft'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, default=encode)
        f.write('\n')


def bounds(pair):
    return list(map(D, pair))


def contains(pair, exact):
    a, b = bounds(pair)
    return a <= exact <= b


def near(pair, reference, tolerance):
    a, b = bounds(pair)
    return a-tolerance <= D(reference) <= b+tolerance


def aggregate_energy(probe, traces):
    """Only aggregate complete valid paths; rejection deliberately has no energy_J."""
    out = {'status': 'not_aggregatable', 'scope': 'synthetic U1 arithmetic probe only; not savings comparison',
           'reasons': []}
    ids, weights = probe.get('trace_ids', []), probe.get('weights', [])
    if not ids or len(ids) != len(weights) or len(set(ids)) != len(ids):
        out['reasons'].append({'reason': 'invalid_path_weight_lists'})
        return out
    try:
        weight_intervals = [I(w) for w in weights]
        if any(w.lo < 0 for w in weight_intervals) or sum(F(w) for w in weights) != 1:
            raise ValueError('weights must be nonnegative and sum exactly to one')
    except (ValueError, TypeError, ArithmeticError) as exc:
        out['reasons'].append({'reason': 'invalid_weights', 'detail': str(exc)})
        return out
    for tid in ids:
        r = traces.get(tid)
        if r is None:
            out['reasons'].append({'trace_id': tid, 'reason': 'missing_path'})
            continue
        h = r.get('thermal', {})
        required = {'input_status': r.get('input_status') == 'valid',
                    'execution_status': r.get('execution_status') == 'valid',
                    'energy_scope': r.get('energy_scope') == 'complete_window',
                    'rankable_energy': r.get('rankable_energy') is True,
                    'thermal_status': h.get('status') == 'safe',
                    'thermal_complete': h.get('complete') is True,
                    'precision_met': h.get('precision_met') is True}
        failed = [field for field, passed in required.items() if not passed]
        if failed:
            out['reasons'].append({'trace_id': tid, 'reason': 'path_not_complete_valid', 'failed_fields': failed})
    if out['reasons']:
        return out  # Never read or multiply any prefix energy; do not drop paths or renormalize.
    try:
        if any(not isinstance(traces[tid]['thermal'].get('energy_J'), list)
               or len(traces[tid]['thermal']['energy_J']) != 2 for tid in ids):
            raise ValueError('energy_J must contain two interval endpoints')
        energies = [I(*traces[tid]['thermal']['energy_J']) for tid in ids]
        weighted = sum((energy*w for energy, w in zip(energies, weight_intervals)), I(0))
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        out['reasons'].append({'reason': 'invalid_energy_enclosure', 'detail': str(exc)})
        return out
    return {'status': 'valid', 'energy_J': weighted.data(), 'trace_ids': ids,
            'weights': weights, 'scope': out['scope']}


def precheck(output):
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output/'source'; snapshot.mkdir()
    for p in ROOT.glob('*.py'):
        (snapshot/p.name).write_bytes(p.read_bytes())
    tests = []
    def check(name, predicate):
        try:
            passed = bool(predicate())
            detail = '' if passed else 'condition failed'
        except Exception as exc:
            passed, detail = False, f'{type(exc).__name__}: {exc}'
        tests.append({'name': name, 'passed': passed, 'detail': detail})
    static = subprocess.run([sys.executable, str(PACKAGE/'check_static.py')], capture_output=True, encoding='utf-8')
    save(output/'static_gate.json', json.loads(static.stdout))
    check('冻结输入及28项静态入口', lambda: static.returncode == 0)
    if static.returncode != 0:
        save(output/'precheck.json', {'passed':False,'tests':tests,'reason':'static_gate_failed; evaluator not run'})
        print('Static input gate failed; evaluator not run.')
        return 1
    x = load(PACKAGE/'inputs.json')
    # Evaluate without expected.json. Read the oracle only AFTER all outputs exist.
    traces = {tr['id']: evaluate_trace(x, tr) for tr in x['traces']}
    primitives = {v['id']: evaluate_primitive(v, x['accuracy']) for v in x['thermal_primitives']}
    save(output/'traces.json', traces); save(output/'primitives.json', primitives)
    y = load(PACKAGE/'expected.json')
    for tid in ['F1', 'F2', 'F3']:
        actual = traces[tid]; expected = y['traces'][tid]
        check(tid+' 独立手写Stage时间表', lambda a=actual, e=expected:
              len(a['schedule']) == len(e['schedule_rows']) and all(all(row[k] == ref[k] for k in ref) for row, ref in zip(a['schedule'], e['schedule_rows'])))
        check(tid+' 执行状态', lambda a=actual, e=expected: a['execution_status'] == e['execution_status'])
        check(tid+' 持续保证未升级', lambda a=actual: a['sustained_safety'] == 'not_evaluated')
        if tid != 'F3':
            h = actual['thermal']
            check(tid+' 完整热安全与精度', lambda h=h, a=actual: h['status'] == 'safe' and h['complete'] and h['precision_met'] and a['rankable_energy'])
            check(tid+' 公共和逐节点基准能量', lambda h=h, e=expected:
                  contains(h['external_J'], e['external_energy_J']) and contains(h['base_by_node_J'][0], e['CPU_base_energy_J']) and contains(h['base_by_node_J'][1], e['NPU_base_energy_J']))
            check(tid+' 活动能耗独立双算', lambda h=h, e=expected: contains((I(*h['activity_by_node_J'][0])+I(*h['activity_by_node_J'][1])).data(), e['activity_energy_J']))
            check(tid+' 总能量含漏电及尾段', lambda h=h, e=expected:
                  bounds(h['energy_J'])[0] >= e['total_energy_algebraic_enclosure_J'][0]
                  and bounds(h['energy_J'])[1] <= e['total_energy_algebraic_enclosure_J'][1]
                  and h['covered_until_us'] == 80000 and h['states'][-1]['time_us'] == 80000)
            check(tid+' 全部峰温处于解析充分界', lambda h=h: all(25 <= bounds(v)[0] <= bounds(v)[1] <= 59 for v in h['peak_C']))
        else:
            check('F3 截止到原期限／部分能量不得排名', lambda: actual['failure']['lateness_us'] == 1000 and actual['thermal']['covered_until_us'] == 53000 and not actual['rankable_energy'] and actual['energy_scope'] == 'prefix_to_failed_deadline')
    check('F4 W1失败不运行热传播', lambda: traces['F4']['input_status'] == 'invalid' and traces['F4']['reason'] == 'W1_incompatible' and 'thermal' not in traces['F4'])
    with localcontext() as ctx:
        ctx.prec = 80
        for v in x['thermal_primitives'][:3]:
            h = D(v['duration_us'])/1000000; lam = D(v['leak_W_per_K'])
            a = (v['ambient_conductance_W_per_K']-lam)/v['C_J_per_K']
            eq = (v['ambient_conductance_W_per_K']*v['ambient_C']+v['base_W']+v['activity_increment_W']-lam*v['leak_reference_C'])/(v['ambient_conductance_W_per_K']-lam)
            end = eq+(v['initial_temperature_C']-eq)*(-a*h).exp()
            en = (v['base_W']+v['activity_increment_W'])*h+lam*((eq-v['leak_reference_C'])*h+(v['initial_temperature_C']-eq)*(1-(-a*h).exp())/a)+v['external_power_W']*h
            result = primitives[v['id']]
            check(v['id']+' 区间覆盖独立80位解析值', lambda r=result, end=end, en=en: contains(r['end_temperature_C'][0], end) and contains(r['energy_J'], en) and r['status'] == 'safe')
        u = D('.2')/D('.098'); a = D('12.5')-u
        at = (D('6.9')*D('12.5')/(D('4.9')*a)).ln()/2
        peak = 25+u+a*(-D('4.9')*at).exp()-D('12.5')*(-D('6.9')*at).exp()
        check('H4 内部峰值被包络覆盖／正确违规', lambda: contains(primitives['H4']['peak_C'][1], peak) and primitives['H4']['status'] == 'violation' and bounds(primitives['H4']['end_temperature_C'][1])[1] < D('27.5') and primitives['H4']['precision_met'])
        check('区间除法覆盖精确1/3与负区间', lambda: (I(1)/3).lo <= D(1)/3 <= (I(1)/3).hi and (I(-2,-1)/I(-4,-2)).lo <= D('.25') and (I(-2,-1)/I(-4,-2)).hi >= 1)
        panel = TaylorPanel([[I(1)]], [I(1)], F(1,10))
        check('Taylor余项覆盖独立exp(0.1)', lambda: panel.value(F(1,10))[0].lo <= D('.1').exp() <= panel.value(F(1,10))[0].hi)
    for probe in x['judgement_probes']:
        p = I(*probe['supplied_enclosure_C']); limit = probe['limit_C']
        status = 'safe' if p.hi <= limit else 'violation' if p.lo > limit else 'unresolved'
        check(probe['id']+' 状态分类', lambda p=probe, s=status: s == p['expected'])

    variants = {}
    def variant(name, data, trace, predicate, budget=None):
        r = evaluate_trace(data, trace, budget)
        variants[name] = {'input': data, 'trace': trace, 'output': r}
        check(name, lambda: predicate(r))
        return r
    base = x['traces'][0]
    tr = deepcopy(base); tr['switch_requests'] = []
    variant('持续A有限四轮', x, tr, lambda r: [q['release_us'] for q in r['requests']] == [0,20000,40000,60000] and r['thermal']['status'] == 'safe')
    tr = deepcopy(base); tr['window_us'] = 120000; tr['switch_requests'].append({'time_us':85000,'to_mode':'A'})
    r = variant('A到B再到A有限路径', x, tr, lambda r: len(r['requests']) == 7 and r['requests'][-2]['release_us'] == 85000 and r['thermal']['status'] == 'safe')
    check('转换不重置温度／回A恢复工作点', lambda: next(s for s in r['thermal']['states'] if s['time_us']==85000)['temperature_C'] != [['30','30'],['30','30']] and next(s for s in r['thermal']['segments'] if s['start_us']==85000)['opps']['C0']=='H')
    tr = deepcopy(base); tr['window_us']=90000; tr['switch_requests'][0]['time_us']=55000
    variant('空闲时切换无需排空等待', x, tr, lambda r: r['requests'][3]['base_us']==55000 and r['thermal']['status']=='safe')
    tr = deepcopy(base); tr['switch_requests'][0]['time_us']=39999
    variant('最小切换间隔前拒绝', x, tr, lambda r: r['input_status']=='invalid' and r['reason']=='minimum_switch_interval')
    tr = deepcopy(base); tr['switch_requests'][0]['time_us']=40001
    variant('释放后切换保留已释放工作', x, tr, lambda r: r['execution_status']=='deadline_violation' and r['requests'][2]['mode']=='A')
    d = deepcopy(x); d['fixed_plans']['A']['stages'][0]['duration_us']=D('2000.25'); d['fixed_plans']['A']['stages'][1]['offset_us']=D('2000.25')
    variant('非整数微秒结束与整轮平移不取整', d, base, lambda r: r['schedule'][0]['end_us']==F(8001,4) and r['requests'][3]['base_us']==F(192001,4) and r['execution_status']=='valid')
    d = deepcopy(x); d['fixed_plans']['A']['stages'][0]['opp']='unsupported'
    variant('非法模式', d, base, lambda r: r['input_status']=='invalid' and r['reason']=='illegal_mode')
    d = deepcopy(x); d['fixed_plans']['A']['stages'][1]['offset_us']=0
    variant('依赖违规', d, base, lambda r: r['input_status']=='invalid' and r['reason']=='dependency_violation')
    d = deepcopy(x); a = deepcopy(d['fixed_plans']['A']['stages'][0]); a['id']='collision';d['fixed_plans']['A']['stages'].append(a)
    variant('单元重叠拒绝', d, base, lambda r: r['input_status']=='invalid' and r['reason']=='unit_overlap')
    # Derived interface fixtures, never replace the frozen two-node inputs.
    d = deepcopy(x); p=d['platform'];p['nodes'].append('CPU2');p['C_J_per_K'].append(D('.02'))
    for row in p['G_W_per_K']: row.append(0)
    p['G_W_per_K'].append([0,0,D('.1')]);p['temperature_limit_C'].append(80)
    p['units']['C1']={'node':'CPU2','frequency_domain':'DC'};p['opps']['C1']=deepcopy(p['opps']['C0'])
    a=deepcopy(d['fixed_plans']['A']['stages'][0]);a.update(id='parallel',unit='C1',duration_us=1000);d['fixed_plans']['A']['stages'].append(a)
    tr=deepcopy(base);tr['initial_temperature_C'].append(30);tr['initial_opps']['C1']='H'
    variant('共享域同频并发', d, tr, lambda r:r['execution_status']=='valid' and r['thermal']['status']=='safe')
    bad=deepcopy(d);bad['fixed_plans']['A']['stages'][-1]['opp']='L'
    variant('共享域异频并发拒绝', bad, tr, lambda r:r['input_status']=='invalid' and r['reason']=='shared_domain_conflict')
    free=deepcopy(bad);free['fixed_plans']['A']['stages'][-1]['offset_us']=2000
    rr=variant('域清空同刻切频／CPU与NPU并发', free, tr, lambda r:r['execution_status']=='valid' and r['thermal']['status']=='safe')
    check('空闲同域单元工作点同步而不重复计基准', lambda: next(s for s in rr['thermal']['segments'] if s['start_us']==2000)['opps']['C0']=='L' and len(rr['thermal']['base_by_node_J'])==3)
    d=deepcopy(x);del d['semantics']['extra_preparation_us']
    variant('缺准备语义不得默认为零', d, base, lambda r:r['input_status']=='invalid')
    variant('入口温度已违规', x, dict(deepcopy(base),initial_temperature_C=[81,30]), lambda r:r['thermal']['status']=='violation' and not r['rankable_energy'])
    variant('计时预算中断', x, base, lambda r:not r['rankable_energy'] and r['thermal']['status']=='unresolved', Budget(seconds=0))
    variant('传播资源中断', x, base, lambda r:not r['rankable_energy'] and not r['thermal']['complete'], Budget(panels=0))
    h4=evaluate_primitive(x['thermal_primitives'][3],x['accuracy'],Budget(refinements=0))
    check('内部峰值细化中断保留已知违规', lambda:not h4['complete'] and h4['status']=='violation'
          and bool(h4['known_violations']) and not h4['rankable_energy'])
    hot=deepcopy(base);hot['initial_temperature_C']=[81,30]
    variant('中断保留入口可靠违规', x, hot, lambda r:r['thermal']['status']=='violation' and not r['thermal']['complete'] and bool(r['thermal']['known_violations']), Budget(panels=0))
    with patch('evaluate.coeff_matrix', side_effect=ArithmeticError('injected numeric failure')):
        variant('数值计算异常不得误标输入无效', x, base, lambda r:r['input_status']=='valid' and r['thermal']['status']=='unresolved' and not r['rankable_energy'])
    # Force exhaustion specifically during endpoint evaluation after peak checks.
    real_value=TaylorPanel.value
    real_peak=TaylorPanel.peak
    budget=Budget()
    peak_calls=[0]
    def count_peak(*args,**kwargs):
        out=real_peak(*args,**kwargs)
        peak_calls[0]+=1
        return out
    def late_value(panel,left,right=None):
        out=real_value(panel,left,right)
        if peak_calls[0]>=2 and right is None:
            budget.seconds=-1
        return out
    with patch.object(TaylorPanel,'value',late_value), patch.object(TaylorPanel,'peak',count_peak):
        variant('末步计算跨预算不得接纳新结果', x, base, lambda r:not r['rankable_energy'] and not r['thermal']['complete'], budget)
    v=deepcopy(x['thermal_primitives'][0]);v['C_J_per_K']=-1
    check('独立热部件拒绝负热容', lambda:evaluate_primitive(v,x['accuracy'])['status']=='invalid')
    hot_v=deepcopy(x['thermal_primitives'][0]);hot_v['initial_temperature_C']=81
    late_budget=Budget()
    def expire_after_thermal(*args,**kwargs):
        result=thermal(*args,**kwargs)
        late_budget.seconds=-1
        return result
    with patch('evaluate.thermal',expire_after_thermal):
        late_result=evaluate_primitive(hot_v,x['accuracy'],late_budget)
    check('独立热部件返回超时仍保留已知违规', lambda:late_result['status']=='violation' and not late_result['complete'] and bool(late_result['known_violations']) and 'energy_J' not in late_result)
    save(output/'primitive_late_return.json',late_result)
    save(output/'derived_interface_checks.json',variants)
    save(output/'interrupted_peak.json',h4)

    # Independent numerical ODE cross-check is diagnostic, never the error certificate.
    ode=[]
    try:
        import numpy as np
        from scipy.integrate import solve_ivp
        for tid in ['F1','F2']:
            r=traces[tid]; state=np.array([30.,30.,0.]); p=x['platform']
            for seg in r['thermal']['segments']:
                c=np.array(p['C_J_per_K'],float);g=np.array(p['G_W_per_K'],float)
                b=np.array(seg['base_W'],float);q=np.array(seg['activity_W'],float);lam=np.array(seg['leak_W_per_K'],float)
                def rhs(t,z):
                    power=b+q+lam*(z[:2]-float(p['leak_reference_C']))
                    return np.r_[(-g@(z[:2]-float(p['ambient_C']))+power)/c, sum(power)+float(p['external_power_W'])]
                h=float((seg['end_us']-seg['start_us'])/1000000)
                sol=solve_ivp(rhs,[0,h],state,rtol=1e-11,atol=1e-13,method='DOP853')
                if not sol.success: raise RuntimeError(sol.message)
                state=sol.y[:,-1]
            ode.append({'id':tid,'terminal_C':state[:2].tolist(),'energy_J':float(state[2]),'proof_role':'diagnostic_only'})
            check(tid+' 独立逐事件ODE核对',lambda r=r,z=state:all(near(v,str(t),D('1e-8')) for v,t in zip(r['thermal']['end_temperature_C'],z[:2])) and near(r['thermal']['energy_J'],str(z[2]),D('1e-10')))
    except ImportError:
        ode.append({'status':'not_available','required_for_certificate':False})
    save(output/'ode_crosscheck.json',ode)

    weighted = aggregate_energy(x['usage_aggregation_probe'], traces)
    check('加权能量只接纳完整有效路径', lambda:weighted['status']=='valid')
    save(output/'weighted_energy.json', weighted)
    rejected = {}
    for label, tid in [('deadline_prefix', 'F3'), ('invalid_window', 'F4'), ('missing_path', 'missing')]:
        probe = {'trace_ids':['F1',tid], 'weights':[D('.5'),D('.5')]}
        rejected[label] = aggregate_energy(probe, traces)
        check('加权拒绝 '+label, lambda r=rejected[label]:r['status']=='not_aggregatable' and 'energy_J' not in r and bool(r['reasons']))
    interrupted = deepcopy(traces)
    interrupted['F2']['thermal'] = {'status':'unresolved','complete':False}
    # Even a stale rankable flag cannot authorize aggregation of incomplete output.
    rejected['interrupted_stale_flag'] = aggregate_energy(x['usage_aggregation_probe'], interrupted)
    check('加权拒绝中断且不信任陈旧标志', lambda:rejected['interrupted_stale_flag']['status']=='not_aggregatable' and 'energy_J' not in rejected['interrupted_stale_flag'])
    zero_probe = {'trace_ids':['F1','F3'], 'weights':[1,0]}
    rejected['zero_weight_invalid_path'] = aggregate_energy(zero_probe,traces)
    check('零权重不掩盖声明路径违规', lambda:rejected['zero_weight_invalid_path']['status']=='not_aggregatable' and 'energy_J' not in rejected['zero_weight_invalid_path'])
    save(output/'aggregation_rejections.json', rejected)
    for tid,r in traces.items():
        if 'schedule' in r:
            keys=['mode','request_id','stage','unit','opp','release_us','deadline_us','start_us','end_us']
            with (output/(tid+'_schedule.csv')).open('x',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
                for row in r['schedule']:writer.writerow({k:str(row[k]) for k in keys})
        if 'thermal' in r and 'states' in r['thermal']:
            with (output/(tid+'_temperature.csv')).open('x',encoding='utf-8-sig',newline='') as f:
                writer=csv.writer(f);writer.writerow(['time_us','CPU_lo_C','CPU_hi_C','NPU_lo_C','NPU_hi_C'])
                for row in r['thermal']['states']:writer.writerow([row['time_us']]+[s for v in row['temperature_C'] for s in v])
    report={'utc_time':datetime.now(timezone.utc).isoformat(),'tests':tests,'passed':all(t['passed'] for t in tests),
            'passed_count':sum(t['passed'] for t in tests),'total_count':len(tests),
            'scope':'V1 finite-path precheck, not V2 or optimization experiment',
            'input_sha256':sha(PACKAGE/'inputs.json'),'expected_sha256':sha(PACKAGE/'expected.json'),
            'source_sha256':{p.name:sha(p) for p in sorted(ROOT.glob('*.py'))},'python':sys.version}
    save(output/'precheck.json',report)
    print(json.dumps({'passed':report['passed'],'checks':f"{report['passed_count']}/{report['total_count']}",
                      'failures':[t for t in tests if not t['passed']],'output':str(output)},ensure_ascii=False))
    return 0 if report['passed'] else 1


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=['precheck'])
    ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args()
    return precheck(args.output.resolve())


if __name__=='__main__':
    sys.exit(main())
