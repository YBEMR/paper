"""Audit auxiliary text and ZIP tables without extracting or executing them."""
import csv, hashlib, io, json, statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

root = Path(__file__).resolve().parent
aux = json.loads((root/'auxiliary_manifest.json').read_text(encoding='utf-8'))
for e in aux:
    raw=(root/e['local_path']).read_bytes()
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==e['git_blob_sha']
    e['local_path']='source_cache/'+e['git_blob_sha']+'.txt'
    assert e['sha256']==hashlib.sha256(raw).hexdigest()
    assert e['bytes']==len(raw)
zpath=root/'external_sources/BatchDVFS_results.zip'
raw=zpath.read_bytes()
assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()=='f6b2d87851bb63b7cc301534e43c8d634f0dff8a'
inventory=[]
intervals=[]
with ZipFile(zpath) as z:
    assert sum(e.file_size for e in z.infolist())<10_000_000
    assert z.testzip() is None
    for e in z.infolist():
        content=z.read(e)
        lines=content.decode('utf-8-sig').splitlines()
        rr=list(csv.DictReader(io.StringIO('\n'.join(lines))))
        fields=list(rr[0]) if rr else []
        is_native=e.filename.startswith('nvidia-smi/')
        if is_native:
            ts=[datetime.strptime(r['timestamp'], '%Y/%m/%d %H:%M:%S.%f') for r in rr]
            intervals.extend((b-a).total_seconds() for a,b in zip(ts,ts[1:]))
        inventory.append({'member':e.filename,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'rows':len(rr),'columns':'|'.join(fields),'native_nvidia_smi':is_native,'temperature_column':any('temp' in f.lower() for f in fields)})
with (root/'results/batchdvfs_archive_inventory.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
result={'zip_sha256':hashlib.sha256(raw).hexdigest(),'members':len(inventory),'schema_counts':dict(Counter(r['columns'] for r in inventory)),'rows':sum(r['rows'] for r in inventory),'native_csv_files':sum(r['native_nvidia_smi'] for r in inventory),'temperature_columns_found':sum(r['temperature_column'] for r in inventory),'native_interval_median_s':statistics.median(intervals),'native_interval_min_s':min(intervals),'native_interval_max_s':max(intervals),'read_scope':'entire released BatchDVFS result ZIP plus one controller source; not Clipper/DVFS baseline ZIPs; author PDF direct HTTP403, indexed section4.1 only'}
(root/'results/batchdvfs_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
