from pathlib import Path
import hashlib
root=Path(__file__).resolve().parent
count=0
for line in (root/'MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
    expected,name=line.split('  ',1)
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
    count+=1
print(f'PASS: {count} archived files match SHA256 manifest')
