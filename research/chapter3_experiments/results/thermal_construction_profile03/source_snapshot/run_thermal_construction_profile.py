"""Two existing correctness fixtures; not an original-scale benchmark."""
import argparse
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import shutil
import time

from inputs import load_config
from run_milp_precheck import fixtures
from milp import build_model
from build_observer import BuildObserver
from timing import MethodBudget

HERE = Path(__file__).resolve().parent


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    sources = ['milp.py', 'milp_coefficients.py', 'build_observer.py',
               'config_v01.json', 'run_thermal_construction_profile.py']
    hashes = {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in sources}
    (out/'source_snapshot').mkdir()
    for name in sources:
        shutil.copy2(HERE/name, out/'source_snapshot'/name)
    config = load_config()
    data = fixtures(config)
    results = {}
    for name in ('one_stage_energy', 'chain_fractional'):
        instance, starts = data[name]
        budget = MethodBudget(600)  # correctness probe, not a research budget
        observer = BuildObserver(budget, out/(name+'.jsonl'))
        profiler = cProfile.Profile()
        start = time.perf_counter()
        model = profiler.runcall(build_model, instance, config, starts=starts,
                                budget=budget, progress=observer)
        construction_s = time.perf_counter()-start
        snapshot = observer.finish('MODEL_CONSTRUCTED')
        stats = pstats.Stats(profiler)
        hot = []
        for (filename, line, function), (primitive, calls, own, cumulative, callers) in stats.stats.items():
            hot.append({'file': filename, 'line': line, 'function': function,
                        'calls': calls, 'own_s': own, 'cumulative_s': cumulative})
        hot.sort(key=lambda row: row['cumulative_s'], reverse=True)
        results[name] = {'summary': model.summary(), 'observation': snapshot,
                         'construction_profiled_s': construction_s,
                         'profile_top_35': hot[:35]}
    after = {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in sources}
    result = {'scope': 'two existing small correctness fixtures; profiler overhead included; not performance comparison',
              'results': results, 'source_sha256': hashes, 'source_sha256_after': after,
              'source_stable': hashes == after, 'formal_comparison': False}
    (out/'profile.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({name: row['observation']['construction_components'] for name, row in results.items()}, indent=2))
    if hashes != after:
        raise RuntimeError('source changed during profile')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    run(parser.parse_args().out)
