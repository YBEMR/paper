"""Project saved once-only postchecks to scene/thermal tables, without evaluating heat."""
import csv
from fractions import Fraction as F
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    facts = json.loads((ROOT/'analysis01/facts.json').read_text(encoding='utf-8'))
    assert facts['process_terminal']['state'] == 'COMPLETED' and facts['observed_rows'] == 40
    scenes, peaks = [], []
    for row in facts['rows']:
        path = ROOT/'calls'/row['problem_id']/row['method']/'postcheck.json'
        post = json.loads(path.read_text(encoding='utf-8'))
        assert post['state'] == 'SAFE' and post['rankable_energy'] is True
        for sid, scene in post['scenes'].items():
            base = {'problem_id': row['problem_id'], 'method': row['method'], 'scene': sid,
                    'source': path.relative_to(ROOT).as_posix()}
            out = dict(base)
            out.update({'complete': scene['complete'], 'covered_until_s': scene['covered_until_s'],
                        'energy_lo_J': float(F(scene['energy_J'][0])),
                        'energy_hi_J': float(F(scene['energy_J'][1])),
                        'post_elapsed_s': post['elapsed_s']})
            for name, interval in scene['energy_components_J'].items():
                out[name+'_lo_J'] = float(F(interval[0]))
                out[name+'_hi_J'] = float(F(interval[1]))
            scenes.append(out)
            for node, interval in scene['peaks_degC'].items():
                peaks.append(dict(base, node=node, peak_lo_degC=float(F(interval[0])),
                                  peak_hi_degC=float(F(interval[1])),
                                  peak_lo_exact=interval[0], peak_hi_exact=interval[1]))
    for name, records in [('scene_energy.csv', scenes), ('scene_peak_temperature.csv', peaks)]:
        with (ROOT/'analysis01'/name).open('x', encoding='utf-8-sig', newline='') as stream:
            writer=csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader();writer.writerows(records)
    summary = {'scope': 'Projection of original once-only post; not another evaluation or budget evidence',
               'scene_rows': len(scenes), 'node_peak_rows': len(peaks),
               'max_post_peak_upper_degC': max(p['peak_hi_degC'] for p in peaks),
               'research_calls': 0, 'new_thermal_evaluations': 0}
    with (ROOT/'analysis01/post_projection.json').open('x',encoding='utf-8') as stream:
        json.dump(summary,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(summary)


if __name__ == '__main__':
    main()
