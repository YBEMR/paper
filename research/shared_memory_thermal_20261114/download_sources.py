"""Optional reproducibility download; verifies every archived SHA256, executes nothing."""
import argparse,hashlib,json,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent;P=argparse.ArgumentParser();P.add_argument('--all',action='store_true',help='Include primary PDFs, official HTML and archive metadata');args=P.parse_args();C=R.parent/'shared_memory_sources'
rows=json.loads((R/'source_manifest.json').read_text())
for row in rows:
    if row['status']=='UNAVAILABLE':continue
    if not args.all and not(row['kind']=='author_artifact' or row['id']=='HaX-CoNN_zenodo.zip'):continue
    q=C/row['id'];q.parent.mkdir(parents=True,exist_ok=True)
    data=q.read_bytes() if q.exists() else urllib.request.urlopen(urllib.request.Request(row['url'],headers={'User-Agent':'Research-evidence-audit/1.0'}),timeout=40).read()
    if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Source content drift: '+row['id'])
    q.write_bytes(data);print(row['id'],'SHA256_OK')
