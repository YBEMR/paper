"""Recheck exact-energy assertion only; does not rerun numerical fixtures."""
from decimal import Decimal as D
from pathlib import Path
import argparse
import scaled as s

p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);args=p.parse_args()
source=Path(args.source);out=Path(args.out)
if out.exists():raise FileExistsError(out)
r=s.a.old.read(source)
failed=[v['name'] for v in r['checks'] if not v['passed']]
if failed!=['activity_energy_exact']:raise ValueError('not_the_single_assertion_failure')
current=s.identities()
checks=[dict(name='saved_runtime_dependencies_match',passed=all(v==current[k] for k,v in r['hashes'].items() if not k.replace('\\','/').endswith('thermal_pressure_numerics/precheck.py')))]
bounds=r['artifacts']['pulse_changed_OPP_tail']['result']['activity_by_node_J'][1]
tol=D(s.a.load()['problem']['evaluation']['accuracy']['energy_enclosure_width_J'])
checks.append(dict(name='activity_interval_encloses_exact_Qd',passed=D(bounds[0])<=D('.00125')<=D(bounds[1]) and D(bounds[1])-D(bounds[0])<=tol,bounds=bounds))
out.mkdir(parents=True)
s.a.old.write(out/'result.json',dict(scope='saved-result assertion correction only; no new timings',source=str(source),source_sha256=s.a.cp.sha(source),passed=all(v['passed'] for v in checks),checks=checks,hashes=current))
print(checks)
raise SystemExit(0 if all(v['passed'] for v in checks) else 1)
