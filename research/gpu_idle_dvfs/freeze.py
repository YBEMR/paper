"""Freeze local execution plus the inherited physical/source/input manifest."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert not (HERE/'raw').exists()
old=json.loads((ROOT/'research/kim_gap_diagnostics/execution_manifest.json').read_bytes())
sources=list(old)+['research/kim_gap_diagnostics/common.py','research/kim_gap_diagnostics/inputs/cases.json']
sources += [str(p.relative_to(ROOT)).replace('\\','/') for p in HERE.iterdir() if p.suffix in ('.py','.md','.json') and p.name!='execution_manifest.json']
result={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(sources))}
(HERE/'execution_manifest.json').write_bytes((json.dumps(result,indent=2,ensure_ascii=False)+'\n').encode())
print('Frozen source/input files:',len(result))
