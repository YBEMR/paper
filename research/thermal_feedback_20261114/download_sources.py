"""Optional read-only retrieval of public evidence, pinned where possible.

No author code is executed. Default downloads author CSV/code needed by
audit_public_data.py; --papers includes cached primary paper/HTML locations.
"""
import argparse,hashlib,json,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--papers',action='store_true');args=p.parse_args()
R=Path(__file__).resolve().parent;cache=R.parent/'throttle_sources'
for row in json.loads((R/'source_manifest.json').read_text(encoding='utf-8')):
    if row['kind']!='sev' and not args.papers:continue
    out=cache/row['name'];out.parent.mkdir(parents=True,exist_ok=True)
    data=out.read_bytes() if out.exists() else urllib.request.urlopen(urllib.request.Request(row['url'],headers={'User-Agent':'research-evidence-audit/1.0'}),timeout=30).read()
    if data.startswith(b'version https://git-lfs.github.com/spec/'):
        url=row['url'].replace('https://raw.githubusercontent.com/','https://media.githubusercontent.com/media/')
        data=urllib.request.urlopen(url,timeout=30).read()
    actual=hashlib.sha256(data).hexdigest()
    if actual!=row['sha256']:raise ValueError('Source changed or wrong content: '+row['name']+' expected '+row['sha256']+' got '+actual)
    out.write_bytes(data);print(row['name'],len(data),'HASH_OK')
