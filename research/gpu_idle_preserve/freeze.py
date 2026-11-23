"""Freeze implementation plus inherited sources and the exact reused comparison data."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OLD=ROOT/'research/gpu_idle_dvfs'
assert not (HERE/'raw').exists()
names=set(json.loads((OLD/'execution_manifest.json').read_bytes()))
names.add('research/gpu_idle_dvfs/results.json')
for p in (OLD/'raw').glob('*_input.json.gz'):names.add(p.relative_to(ROOT).as_posix())
for p in (OLD/'raw').glob('*C/*kim.json.gz'):names.add(p.relative_to(ROOT).as_posix())
for p in (OLD/'raw').glob('*C/ideal_ideal_fixed_busy.json.gz'):names.add(p.relative_to(ROOT).as_posix())
for p in HERE.iterdir():
    if p.suffix in ['.py','.md','.json'] and p.name!='execution_manifest.json':names.add(p.relative_to(ROOT).as_posix())
manifest={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
(HERE/'execution_manifest.json').write_bytes((json.dumps(manifest,indent=2)+'\n').encode())
print('Frozen files',len(manifest))
