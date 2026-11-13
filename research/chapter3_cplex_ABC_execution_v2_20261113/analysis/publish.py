"""Lossless publication of finished evidence; never alters the run directory."""
import hashlib
import json
import shutil
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = ROOT / 'work/cplex_ABC_execution_v2'
REPO = ROOT / 'work/publish_repo'
DEST = REPO / 'research/chapter3_cplex_ABC_execution_v2_20261113'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576), b''):h.update(block)
    return h.hexdigest()

def save(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if DEST.exists():
    raise RuntimeError('Publication destination exists; do not overwrite')
start = time.perf_counter()
DEST.mkdir(parents=True)
manifest = dict(kind='lossless_administrative_publication_no_science_upgrade',
    source_run='work/cplex_ABC_execution_v2', solver_calls=0, model_builds=0, thermal_evaluations=0,
    archives={}, copied_files=[])

def copy(src,relative):
    dst=DEST/relative
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dst)
    before,after=sha(src),sha(dst)
    assert before==after
    manifest['copied_files'].append(dict(source=src.relative_to(ROOT).as_posix(),
        destination=relative,bytes=src.stat().st_size,sha256=before))

for arm in 'ABC':
    files=sorted(p for p in (RUN/arm).rglob('*') if p.is_file())
    entries=[dict(path=p.relative_to(RUN).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
    archive=DEST/('raw_'+arm+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,p.relative_to(RUN).as_posix())
    with zipfile.ZipFile(archive,'r') as z:
        assert set(z.namelist())=={e['path'] for e in entries}
        for e in entries:
            h=hashlib.sha256()
            size=0
            with z.open(e['path']) as f:
                for block in iter(lambda:f.read(1048576),b''):
                    h.update(block);size+=len(block)
            assert h.hexdigest()==e['sha256'] and size==e['bytes']
            assert sha(RUN/e['path'])==e['sha256']
    manifest['archives'][archive.name]=dict(bytes=archive.stat().st_size,sha256=sha(archive),
        uncompressed_bytes=sum(e['bytes'] for e in entries),files=entries,all_decompressed_bytes_verified=True)
    print(arm,'archive verified',archive.stat().st_size,flush=True)
    for name in ['allocation.json','input_identity.json','readback.json','reduction_verification.json',
                 'initialization.json','initial_admission.json','initial_complete_evaluation.json',
                 'final_admission.json','final_complete_evaluation.json','native_response.json',
                 'runtime.json','parameters_at_solve.json','observed_native_summary.json',
                 'response_ack.json','scientific_snapshot.json','controller_receipt.json',
                 'controller_completion.json','worker_receipt.json','native.log','stderr.log']:
        copy(RUN/arm/name,'execution/'+arm+'/'+name)
for p in sorted(RUN.iterdir()):
    if p.is_file():copy(p,'execution/'+p.name)
for p in sorted((ROOT/'work/cplex_ABC_D285_launch_v1').iterdir()):
    if p.is_file():copy(p,'launch/'+p.name)
for p in sorted(OUT.iterdir()):
    if p.is_file() and p.suffix in ('.json','.py','.txt'):
        copy(p,'analysis/'+p.name)
copy(OUT/'REPORT.md','REPORT.md')
manifest['publication_copy_and_compression_wall_s']=time.perf_counter()-start
save(DEST/'ARCHIVE_MANIFEST.json',manifest)

# Only exact, user-authorized research archives are allowed, matching repo precedent.
ignore=REPO/'.gitignore'
with ignore.open('ab') as f:
    f.write(b'\n# 2026-11-13 authorized D285 ABC: exact lossless scientific evidence archives.\n')
    for arm in 'ABC':
        f.write(('!/'+(DEST/('raw_'+arm+'.zip')).relative_to(REPO).as_posix()+'\n').encode('utf-8'))

brief=REPO/'RESEARCH_BRIEF.md'
old=brief.read_bytes()
offset=old.index(b'\n')+1
block='''
## D285 执行：完整 R1 CPLEX A/B/C 均取得严格节能原生调度（2026-11-13）

- 按 366169c 的新授权完成一轮 A→B→C：每组独立构模 1 次、求解 1 次、完整评价 2 次；600/550 秒、动态额度、单线程/种子 0 和原内存限额未改，无重试。三组真实 Job 内身份、矩阵读回、最终向量双矩阵准入、独立合法性、完整 AB/AC SAFE、严格区间改善及只读审计全部通过。
- 共同初解约 1.084886371304 J；A/B/C 完整能耗分别约 0.860728789677、0.860647236548、0.860642651063 J，均为不同原生调度，节能约 20.67%。三组全为普通 TIME_LIMIT，处理节点 0/133/154、原生 gap 约 13.53%/13.29%/13.29%，无独立全局最优证明。
- 原生额度 404/452/431 秒；含最终归档的方法计费 545.156/545.687/546.874 秒。C 比 B 少约 4.585 微焦耳，但准备多 20.625 秒、方法成本没有优势；单次 R1 结果不证明稳定约简加速，不能将全部初解改善归因于约简。
- 授权已消费、清理正常，无追加科研调用。完整报告、全成本、分层证据及无损原始归档见 [D285 正式执行](research/chapter3_cplex_ABC_execution_v2_20261113/REPORT.md)。后续若重复或推广需独立冻结与新授权。

'''
brief.write_bytes(old[:offset]+block.replace('\n','\r\n').encode('utf-8')+old[offset:])

# Exact publication paths, never a broad add of the working tree.
paths=['.gitignore','RESEARCH_BRIEF.md']+[p.relative_to(REPO).as_posix() for p in sorted(DEST.rglob('*')) if p.is_file()]
(ROOT/'work/cplex_ABC_D285_stage_paths.nul').write_bytes(b'\0'.join(p.encode('utf-8') for p in paths)+b'\0')
print('Published',len(paths),'paths; bytes',sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()),flush=True)
