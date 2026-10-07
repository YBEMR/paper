"""Read-only PDF extraction; derived text and source hashes stay in research/."""
from pathlib import Path
import subprocess, json, hashlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research' / 'extracted'
OUT.mkdir(parents=True, exist_ok=True)
PREFLIGHT = Path('C:/Users/86130/.codex/skills/academic-research-suite/ars/scripts/pdf_read_preflight.py')
records = []
for src in [*sorted((ROOT / 'papers').glob('*.pdf')), ROOT / 'main.pdf']:
    target = OUT / (src.stem + '.txt')
    proc = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(src), str(target)], capture_output=True)
    info = subprocess.run(['pdfinfo', str(src)], capture_output=True).stdout.decode('utf-8', errors='replace')
    # The preflight's --output requires POSIX dirfd operations. On Windows,
    # preserve its stdout verdict without changing its validation logic.
    pre = subprocess.run(['python', str(PREFLIGHT), str(src)], capture_output=True)
    pre_text = pre.stdout.decode('utf-8', errors='replace')
    try:
        pre_data = json.loads(pre_text)
    except json.JSONDecodeError:
        pre_data = {'verdict': 'UNAVAILABLE', 'warnings': [pre.stderr.decode('utf-8', errors='replace')]}
    (OUT / (src.stem + '.preflight.json')).write_text(json.dumps(pre_data, ensure_ascii=False, indent=2), encoding='utf-8')
    record = {'file': str(src.relative_to(ROOT)), 'sha256': hashlib.sha256(src.read_bytes()).hexdigest(), 'extraction_exit': proc.returncode, 'stderr': proc.stderr.decode('utf-8', errors='replace'), 'pdfinfo': info, 'preflight_exit': pre.returncode, 'preflight_verdict': pre_data.get('verdict')}
    if target.exists():
        txt = target.read_text(encoding='utf-8')
        record['characters'] = len(txt)
        record['first_page_excerpt'] = txt.split('\f')[0][:1600]
    records.append(record)
(ROOT / 'research' / 'inventory_raw.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
for r in records:
    print('\nFILE:', r['file'], 'CHARS:', r.get('characters'), 'EXIT:', r['extraction_exit'])
    print(r.get('first_page_excerpt', 'NO TEXT'))
