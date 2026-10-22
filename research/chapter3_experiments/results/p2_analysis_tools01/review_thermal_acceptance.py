"""Match saved P0/P2 HEFT candidates; no new thermal evaluation."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RESULTS = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def run():
    sources = {}; rows = []
    def read(path):
        sources[path.relative_to(REPO).as_posix()] = sha(path)
        return json.loads(path.read_text(encoding='utf-8'))
    for index in range(1, 6):
        p2path = RESULTS/'p2_execution01/calls'/f'initial_78__R{index}/heft/wrapper_raw_result.json'
        p0path = next(p for p in (RESULTS/'p0_execution01/calls'/f'base__R{index}/heft/wrapper_raw_result.json',
                                RESULTS/'p0_resume01/calls'/f'base__R{index}/heft/wrapper_raw_result.json') if p.is_file())
        p2 = read(p2path); p0 = read(p0path)
        target = p2['evaluations'][1]; evaluation = target['evaluation']
        digest = canonical(target['candidate'])
        matches = []
        for i, value in enumerate(p0['evaluations']):
            if canonical(value['candidate']) != digest: continue
            old = value['evaluation']
            matches.append({'source': p0path.relative_to(REPO).as_posix()+f':evaluations[{i}]',
                'candidate_sha256': digest, 'state': old['state'], 'accepted_safe': value['accepted_safe'],
                'rankable_energy': old.get('rankable_energy'),
                'all_scenes_complete': set(old.get('scenes', {})) == set(value['candidate']['scenes'])
                    and all(s.get('complete') is True and F(s.get('covered_until_s', '-1')) == F('0.4')
                            for s in old.get('scenes', {}).values()),
                'peaks_degC': {sid: scene.get('peaks_degC') for sid, scene in old.get('scenes', {}).items()}})
        witnesses = evaluation.get('violations') or []
        strict = [v for v in witnesses if F(v['temperature_degC'][0]) > F(v['limit_degC'])]
        safe_matches = [m for m in matches if m['state'] == 'SAFE' and m['accepted_safe'] is True
                        and m['rankable_energy'] is True and m['all_scenes_complete']]
        checks = {'full_candidate_hash_matches_saved_P0_SAFE': bool(safe_matches),
            'P2_saved_hash_matches_full_candidate': target.get('candidate_sha256') == digest,
            'P2_strict_point_witness': evaluation['state'] == 'THERMAL_VIOLATION'
                and evaluation.get('reason') == 'POINT_WITNESS' and bool(strict),
            'P2_rejected_candidate_before_budget': target.get('accepted_safe') is False
                and target.get('returned_at_s') is not None and target['returned_at_s'] < 300,
            'all_limits_80': all(F(v['limit_degC']) == 80 for v in witnesses),
            'all_witnesses_within_window_and_before_budget': all(F(v['time_s']) <= F('0.4')
                and v.get('formed_at_elapsed_s') is not None and v['formed_at_elapsed_s'] < 300 for v in witnesses)}
        rows.append({'sample': 'R'+str(index), 'P2_source': p2path.relative_to(REPO).as_posix()+':evaluations[1]',
            'candidate_sha256': digest, 'P0_matches': matches, 'P2_source_kind': target.get('source'),
            'P2_returned_at_s': target.get('returned_at_s'), 'strict_witnesses': strict,
            'P0_final_candidate_sha256': canonical(p0.get('safe_candidate')),
            'P2_final_candidate_sha256': canonical(p2.get('safe_candidate')),
            'P0_P2_final_candidates_identical': canonical(p0.get('safe_candidate')) == canonical(p2.get('safe_candidate')),
            'rejected_candidate_is_P0_final': digest == canonical(p0.get('safe_candidate')),
            'checks': checks, 'passed': all(checks.values())})
    return {'passed': all(r['passed'] for r in rows), 'checks_count': sum(len(r['checks']) for r in rows),
        'samples': rows, 'P0_SAFE_to_P2_violated_same_full_candidate': sum(r['passed'] for r in rows),
        'P0_P2_final_HEFT_candidates_identical': sum(r['P0_P2_final_candidates_identical'] for r in rows),
        'safe_claim': 'Initial temperature changes acceptance of these five specific saved arrangements.',
        'unsupported_claim': 'This does not establish a change in final HEFT arrangement or net benefit from MILP thermal feedback.',
        'new_scientific_evaluations': 0, 'source_sha256': sources, 'script_sha256': sha(Path(__file__))}


if __name__ == '__main__':
    report = run(); target = HERE/'thermal_acceptance_review.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print({'passed': report['passed'], 'count': report['checks_count'],
           'same_P0_SAFE_now_violated': report['P0_SAFE_to_P2_violated_same_full_candidate'],
           'final_HEFT_same': report['P0_P2_final_HEFT_candidates_identical']})
