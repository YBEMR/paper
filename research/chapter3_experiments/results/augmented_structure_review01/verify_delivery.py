"""K136 stored-evidence and scope checks only; no build/solve/thermal imports."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE.parent / 'augmented_quality_pair01'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

declaration = json.loads((SOURCE / 'declaration.json').read_text(encoding='utf-8'))
source_match = all(sha(ROOT / path) == digest and sha(SOURCE / 'source_snapshot' / path) == digest
                   for path, digest in declaration['source_sha256'].items())
raw_paths = ['research/chapter3_experiments/results/' + name for name in
             ['augmented_quality_pair01', 'augmented_pair_wrapper_precheck01',
              'augmented_pair_wrapper_precheck02', 'augmented_pair_claim01.json']]
listed = subprocess.check_output(['git', 'ls-files', '--stage', '-z', '--', *raw_paths], cwd=ROOT)
historical = []
for item in listed.split(b'\0'):
    if not item:
        continue
    metadata, filename = item.split(b'\t', 1)
    mode, expected, stage = metadata.split()
    assert stage == b'0'
    data = (ROOT / filename.decode('utf-8')).read_bytes()
    observed = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest().encode()
    historical.append(observed == expected)

docs = [HERE / 'summary.md', HERE / 'independent_review.md', HERE / 'metrics/summary.md']
missing_links = []
for path in docs:
    text = path.read_text(encoding='utf-8')
    for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
        if '://' in link or link.startswith('#'):
            continue
        target = link.split('#', 1)[0].split(':', 1)[0]
        if target and not (path.parent / target).resolve().exists():
            missing_links.append({'source': str(path.relative_to(ROOT)), 'link': link})

metrics = json.loads((HERE / 'metrics/facts.json').read_text(encoding='utf-8'))
before = json.loads((HERE / 'metrics/hashes_before.json').read_text(encoding='utf-8'))
after = json.loads((HERE / 'metrics/hashes_after.json').read_text(encoding='utf-8'))
read_files_match = before == after and len(before) == 47 and all(
    sha(SOURCE / path) == item['sha256'] and (SOURCE / path).stat().st_size == item['size_bytes']
    for path, item in before.items())
checks = {
    'K135_144_sources_unchanged': source_match and len(declaration['source_sha256']) == 144,
    'all_prior_tracked_pair_artifacts_unchanged': bool(historical) and all(historical),
    'all_delivery_local_links_exist': not missing_links,
    'analysis_status_not_research_run': metrics.get('status') == 'ANALYZED',
    'no_new_research_calls': metrics.get('research_calls') == 0,
    'metrics_47_read_files_unchanged': read_files_match,
    'new_report_has_unique_bounded_revision': '最多两遍' in (HERE/'summary.md').read_text(encoding='utf-8'),
    'new_report_preserves_quality_failure': '新版仍为初始1.080823451833 J' in (HERE/'summary.md').read_text(encoding='utf-8'),
}
receipt = {'scope': 'stored bytes, link and scope checks; no simulation or optimization',
           'checks': checks, 'passed': all(checks.values()),
           'historical_tracked_file_count': len(historical), 'missing_links': missing_links}
(HERE/'delivery_verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
raise SystemExit(0 if receipt['passed'] else 1)
