"""Reassemble exact published CSV from ordered, hash-verified case shards."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent/'results';index=json.loads((R/'candidates/index.json').read_text());parts=[]
for i,row in enumerate(index['files']):
    data=(R/'candidates'/row['name']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==row['sha256']
    lines=data.splitlines(keepends=True)
    if i==0:header=lines[0];parts.append(header)
    assert lines[0]==header and len(lines)-1==row['rows']
    parts.extend(lines[1:])
full=b''.join(parts);assert hashlib.sha256(full).hexdigest()==index['full_csv_sha256']
(R/'all_candidates.csv').write_bytes(full)
print('Verified and assembled',index['total_rows'],'candidate rows')
