"""Inventory exact K148 files; never include unrelated cases or ignored MAT."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[4]
PREFIX = 'research/chapter3_experiments/'
ALLOWED = [PREFIX+'results/five_open_preparation01',
           PREFIX+'results/five_open_precheck01', PREFIX+'results/linked_five_open_pair01',
           PREFIX+'run_five_open_pair.py', PREFIX+'test_five_open_pair.py',
           PREFIX+'results/linked_five_open_claim01.json']
FIXED = ['RESEARCH_BRIEF.md', 'research/03_证据与检索记录.md']
inventory_path = PREFIX+'results/linked_five_open_pair01/delivery_inventory.json'
raw = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z', '--', *ALLOWED], cwd=REPO)
names = sorted(set(FIXED+[n.decode('utf-8') for n in raw.split(b'\0') if n]))
assert inventory_path not in names, 'Inventory already exists; inspect before replacing'
records = {}
secrets = re.compile(rb'(?:github_pat_[A-Za-z0-9_]{30,}|ghp_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
for name in names:
    p = REPO/name
    assert p.is_file() and p.suffix.lower() not in ('.mat', '.pyc'), name
    content = p.read_bytes()
    if secrets.search(content):
        raise RuntimeError('Potential credential literal detected; withhold file: '+name)
    records[name] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
report = {'scope': 'completed K148 stage only; unrelated case/latex files excluded',
          'files': records, 'files_before_inventory': len(names),
          'bytes_before_inventory': sum(r['bytes'] for r in records.values()),
          'ignored_mat_and_credentials_not_added': True,
          'automatic_reviews_untouched': True,
          'research_calls_consumed': 2, 'reserved_method_seconds': 600}
(REPO/inventory_path).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
names.append(inventory_path)
target = REPO/'.runtime/k148_stage_paths.txt'
target.parent.mkdir(exist_ok=True)
target.write_bytes(b'\0'.join(n.encode('utf-8') for n in names)+b'\0')
print(json.dumps({'exact_stage_files': len(names), 'MiB': report['bytes_before_inventory']/1048576,
                  'stage_path_file': str(target), 'potential_credential_matches': 0}))
