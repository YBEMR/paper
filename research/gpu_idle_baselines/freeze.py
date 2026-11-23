"""Freeze causal controllers and inherited physical/comparison evidence before one batch."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert not (HERE/'raw').exists()
prior=json.loads((ROOT/'research/gpu_idle_preserve/execution_manifest.json').read_bytes())
for n,h in prior.items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
names=set(prior)
names.update(['research/gpu_idle_preserve/results.json','research/gpu_idle_preserve/execution_manifest.json'])
for p in (ROOT/'research/gpu_idle_preserve/raw').glob('*C/*.json.gz'):names.add(p.relative_to(ROOT).as_posix())
for p in HERE.iterdir():
    if p.suffix in ('.py','.json','.md') and p.name!='execution_manifest.json':names.add(p.relative_to(ROOT).as_posix())
manifest={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
(HERE/'execution_manifest.json').write_bytes((json.dumps(manifest,indent=2)+'\n').encode())
print('Frozen sources and inputs:',len(manifest))
