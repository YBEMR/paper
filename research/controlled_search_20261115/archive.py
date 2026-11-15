"""Post-stop lossless candidates/envelopes; traces carry exact semantic hashes."""
from copy import deepcopy
import json
from pathlib import Path
from runtime import compact_receipt
from support import sha,save,read

def write_result(path,value):
    path=Path(path)
    if path.name!='result.json':save(path,value);return
    out=dict(value)
    for name in ['evaluations','reconstruction_attempts','graph_proposals']:
        if name not in value:continue
        rows=value[name];pieces=[];lines=[];size=0;count=0
        def flush():
            nonlocal lines,size,count
            if not lines:return
            target=path.parent/f'{name}_{len(pieces)+1:03d}.jsonl'
            target.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
            pieces.append({'file':target.name,'records':len(lines),'bytes':target.stat().st_size,'sha256':sha(target)})
            count+=len(lines);lines=[];size=0
        for raw in rows:
            row=dict(raw)
            if name=='evaluations':row['receipt']=compact_receipt(raw['receipt'])
            line=json.dumps(row,ensure_ascii=False,separators=(',',':'),allow_nan=False)
            if size+len(line.encode('utf-8'))+1>600000:flush()
            lines.append(line);size+=len(line.encode('utf-8'))+1
        flush();out[name]={'archived_jsonl':pieces,'records':count}
    out['archive_note']='Post-stop only. All candidate/energy/peak/identity fields retained; evaluation traces/legality bodies replaced by exact hashes. Final and initial complete receipts retain full traces.'
    save(path,out)
def read_result(path):
    path=Path(path);value=read(path)
    for name in ['evaluations','reconstruction_attempts','graph_proposals']:
        ref=value.get(name)
        if not isinstance(ref,dict) or 'archived_jsonl' not in ref:continue
        rows=[]
        for piece in ref['archived_jsonl']:
            p=path.parent/piece['file'];assert sha(p)==piece['sha256']
            part=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]
            assert len(part)==piece['records'];rows+=part
        assert len(rows)==ref['records'];value[name]=rows
    return value
