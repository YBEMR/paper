"""Validate and seal diagnostics only; no scientific evaluator imports."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
ROOT=EXP.parents[1]
def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,x):
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
if '--seal' not in sys.argv:
    started=time.perf_counter()
    classes=read(HERE/'equivalence_classes.json')
    counts=read(HERE/'equivalence_counts.json')
    for item in classes:
        row=next(x for x in counts if (x['case'],x['index'])==(item['case'],item['index']))
        assert len(item['full_groups'])==row['full_exact_classes']
        assert sum(map(len,item['full_groups'].values()))==row['full_actions']
        assert len(item['observed_feasible_groups'])==row['observed_feasible_exact_classes']
        assert sum(map(len,item['observed_feasible_groups'].values()))==row['observed_feasible_actions']
    raw=(HERE/'equivalence_classes.json').read_bytes()
    packed=gzip.compress(raw,compresslevel=9,mtime=0)
    assert gzip.decompress(packed)==raw
    (HERE/'equivalence_classes.json.gz').write_bytes(packed)
    manifest=read(EXP/'freeze_manifest.json')
    for path,digest in manifest['files'].items():
        assert sha(ROOT/path)==digest,path
    for row in read(EXP/'delivery_manifest.json')['files']:
        assert sha(ROOT/row['path'])==row['sha256'],row['path']
    static=read(HERE/'monotonicity_e0.json')
    assert static['scheduling_calls']==8 and static['thermal_integrations']==3
    assert static['full_search_calls']==0
    assert len(static['positivity'])==432
    sums=read(HERE/'archive_summary.json')
    for row in sums:
        classes_for_case=[x for x in counts if x['case']==row['case']]
        assert sum(x['observed_feasible_actions'] for x in classes_for_case)==row['compiled_actions']
    write(HERE/'validation.json',dict(PASS=True,source_frozen_files_unchanged=len(manifest['files']),
        original_deliverables_unchanged=479,compressed_members=16,
        gzip_sha256=sha(HERE/'equivalence_classes.json.gz'),
        decompressed_sha256=hashlib.sha256(raw).hexdigest(),
        scientific_calls=0,wall_s=time.perf_counter()-started))
    print(json.dumps(read(HERE/'validation.json')))
else:
    ledger=[json.loads(x) for x in (HERE/'budget.jsonl').read_text().splitlines()]
    assert all(x['status']=='PASS' and x['wall_s']<120 for x in ledger)
    used=sum(x['wall_s'] for x in ledger)
    reserve=30.0
    assert used+reserve<600
    receipt=dict(repository='YBEMR/paper',branch='research/kim-search-mechanism-audit-20261119',
        base_commit='babfc5edccfd036ed21a90c7484fb1ed2bcd9276',
        preregistration='033cf34547bb5cb6041e940c80895cced758002a',
        auxiliary_subprocesses=ledger,supervised_wall_s=used,
        unwrapped_readonly_and_sealing_conservative_charge_s=reserve,
        total_charged_auxiliary_s=used+reserve,auxiliary_total_cap_s=600,
        per_process_cap_s=120,E0_schedule_calls=8,E0_single_scene_thermal_integrations=3,
        new_full_policy_scientific_replays=0,new_search_runs=0,formal_algorithm_runs=0,
        unchanged_frozen_files=29,unchanged_original_deliverables=479,
        remote_pinned_manifests=True,external_review_approval=False,
        publication='Pending publication; immutable commit and verification receipt reported separately.')
    write(HERE/'RUN_RECEIPT.json',receipt)
    excluded={'equivalence_classes.json','SHA256SUMS.json','publication_receipt.json'}
    paths=sorted(p for p in HERE.iterdir() if p.is_file() and p.name not in excluded)
    records=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p),
        git_blob_sha1=hashlib.sha1(b'blob '+str(p.stat().st_size).encode()+b'\0'+p.read_bytes()).hexdigest())
        for p in paths]
    write(HERE/'SHA256SUMS.json',dict(schema='diagnostic-delivery-sha256/1',files=records,
        excludes=['self','publication_receipt.json','reproducible cache/','uncompressed equivalence_classes.json']))
    print(json.dumps(dict(files=len(records)+1,charged_s=used+reserve,validation='PASS')))
