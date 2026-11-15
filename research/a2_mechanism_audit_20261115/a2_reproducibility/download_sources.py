"""Fetch only public, immutable inputs listed in this package; verify every hash."""
from pathlib import Path
import urllib.request,hashlib,json,argparse
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=Path('INPUT'));args=ap.parse_args()
root=Path(__file__).resolve().parent
jobs=[('DependableSystemsLab/EdgeEngine','5a09503b0ebfddb2e6c995df1bdaa9630537dc63','EdgeEngine','edgeengine_source_manifest.json'),('dankang21/jetson-latency-lab','6993db85cae594d765ad56a5edd7916eac6d410c','jll_samples','jll_sample_manifest.json')]
for repo,ref,target,manifest in jobs:
    records=json.loads((root/manifest).read_text(encoding='utf-8'))
    for r in records:
        p=args.out/target/r['path'];url=f'https://raw.githubusercontent.com/{repo}/{ref}/{r["path"]}'
        if p.exists(): data=p.read_bytes()
        else:
            with urllib.request.urlopen(url,timeout=45) as response:data=response.read()
        digest=hashlib.sha256(data).hexdigest()
        if digest!=r['sha256']:raise ValueError(f'Input hash mismatch: {p}')
        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    print(target,len(records),'files verified')
