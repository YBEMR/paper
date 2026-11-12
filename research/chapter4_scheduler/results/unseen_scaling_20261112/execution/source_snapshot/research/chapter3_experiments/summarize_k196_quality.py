"""Read-only comparison of K196 archives and the six fresh heuristic jobs."""
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def extract(raw, reference):
    ev = raw.get('evaluation')
    accepted = sorted((r for r in raw.get('evaluations', []) if r.get('accepted_safe')),
                      key=lambda r: r['evaluation']['completed_at_elapsed_s'])
    initial = accepted[0]['evaluation'] if accepted else None
    energy = raw.get('safe_upper_bound_J')
    out = {'method_state': raw.get('state'), 'reason': raw.get('reason'),
           'initial_energy_J': initial['safe_upper_bound_J'] if initial else None,
           'final_energy_J': energy, 'first_safe_s': raw.get('first_safe_at_s'),
           'best_safe_s': None, 'method_elapsed_s': (raw.get('timing') or {}).get('method_elapsed_s'),
           'initialization_source': accepted[0]['source'] if accepted else None,
           'candidate_count': raw.get('candidate_count'), 'thermal_evaluations': raw.get('thermal_evaluations'),
           'cache_hits': raw.get('cache_hits'), 'algorithm_coverage': raw.get('remaining_domain'),
           'algorithm_proved_optimal': raw.get('independently_proven_optimal'),
           'initial_candidate': accepted[0]['candidate'] if accepted else None,
           'final_candidate': raw.get('safe_candidate')}
    if energy is None or not ev:
        return out
    u, lo, ref_u, eps = Q(energy), Q(reference['reference_L_J']), Q(reference['reference_U_J']), Q(reference['epsilon_J'])
    matching = [r['evaluation']['completed_at_elapsed_s'] for r in accepted
                if Q(r['evaluation']['safe_upper_bound_J']) == u]
    out.update(best_safe_s=min(matching) if matching else ev.get('completed_at_elapsed_s'),
               gap_to_reference_U_J=str(u-ref_u), gap_to_reference_L_J=str(u-lo),
               relative_gap_to_reference_U_percent=float(100*(u-ref_u)/ref_u),
               reaches_enumeration_epsilon=u-lo <= eps,
               weighted_energy_interval_J=ev['weighted_energy_J'],
               schedule_with_exact_ends=ev['legality']['scenes'],
               peaks_degC={sid:s['peaks_degC'] for sid,s in ev['scenes'].items()},
               maximum_peak_upper_degC=max(float(v[1]) for s in ev['scenes'].values() for v in s['peaks_degC'].values()),
               energy_components_J={sid:s['energy_components_J'] for sid,s in ev['scenes'].items()})
    # The input is frozen to two equally weighted scenarios.
    out['weighted_energy_components_J'] = {key:[str(sum(Q(s['energy_components_J'][key][i])
        for s in ev['scenes'].values())/2) for i in (0,1)]
        for key in next(iter(ev['scenes'].values()))['energy_components_J']}
    return out


def summarize(folder):
    folder = Path(folder).resolve()
    audit = read(ROOT/'research/chapter3_experiments/results/k196_quality_comparison01/archive_audit.json')
    batch = read(folder/'batch.json')
    rows = []
    for name in ['heft']+['sa'+str(s) for s in range(101,106)]:
        slot = folder/'slots'/(name+'__method')
        path = slot/'worker/raw_result.json'
        if not path.exists():
            rows.append({'id':name, 'state':'NOT_RUN' if name in batch['not_run'] else 'NO_RAW_RECEIPT',
                         'rankable':False})
            continue
        metadata = read(slot/'slot_result.json')
        row = extract(read(path), audit['milp']['energy'])
        row.update(id=name, raw_sha256=sha(path), execution_status=metadata['status'],
                   total_method_wall_s=metadata['total_wall_s'],
                   complete_safe_preserved=bool(metadata.get('worker',{}).get('safe',{}).get('preserved')))
        post_slot = folder/'slots'/(name+'__post')
        post_path = post_slot/'worker/post_result.json'
        post = read(post_path) if post_path.exists() else {}
        post_meta = read(post_slot/'slot_result.json') if (post_slot/'slot_result.json').exists() else {}
        if post:
            assert post['method_receipt_sha256'] == sha(path)
        row.update(post_state=post.get('state'), post_execution_status=post_meta.get('status'),
                   post_wall_s=post_meta.get('total_wall_s'),
                   rankable=(metadata['status'] in ('NORMAL_COMPLETION','NORMAL_TIME_LIMIT')
                             and row['complete_safe_preserved'] and post.get('state')=='SAFE'
                             and post_meta.get('status')=='NORMAL_COMPLETION'))
        rows.append(row)
    sa = [r for r in rows if r['id'].startswith('sa') and r['rankable']]
    stats = {'seeds_planned':5, 'complete_valid_results':len(sa), 'median_representative_seed':None}
    if sa:
        ordered = sorted(sa, key=lambda r:(Q(r['final_energy_J']),r['id']))
        values = [Q(r['final_energy_J']) for r in ordered]
        def percentile(p):
            at=(len(values)-1)*p; i=int(at); f=at-i
            return values[i] if i==len(values)-1 else values[i]*(1-f)+values[i+1]*f
        stats.update(energy_median_J=str(statistics.median(values)), energy_min_J=str(min(values)),
                     energy_max_J=str(max(values)), energy_IQR_J=str(percentile(Q(3,4))-percentile(Q(1,4))),
                     median_method_wall_s=statistics.median(r['total_method_wall_s'] for r in sa),
                     quartile_definition='linear interpolation, index=(n-1)*p; successful results only',
                     median_representative_seed=ordered[(len(ordered)-1)//2]['id'])
    return {'schema':'k196-six-quality-comparison-v1', 'batch_state':batch['state'],
            'batch_error':batch.get('error'), 'batch_total_wall_s':batch['total_wall_s'],
            'method_calls':batch['method_attempts'], 'post_calls':batch['post_attempts'],
            'batch_sha256':sha(folder/'batch.json'), 'milp_archive':audit['milp'],
            'heuristics':rows, 'sa_statistics':stats,
            'scope':'Saved receipts only; zero new solve, search, legality or thermal evaluation.'}


if __name__ == '__main__':
    if len(sys.argv)!=3:
        raise SystemExit('Usage: summarize_k196_quality.py BATCH_FOLDER NEW_OUTPUT_JSON')
    result = summarize(sys.argv[1])
    destination=Path(sys.argv[2]); destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'state':result['batch_state'],'methods':result['method_calls'],
                      'posts':result['post_calls'],'sa':result['sa_statistics']},ensure_ascii=False))
