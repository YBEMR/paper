"""Publish saved execution evidence only. No science imports, process creation or evaluation."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RUN=ROOT/'work/on_budget_candidate_A420_execution_v1'
REPO=ROOT/'work/publish_repo'
DEST=REPO/'research/chapter3_on_A420_execution_20261112'
OUT=ROOT/'outputs'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    a=read(HERE/'audit/audit.json');candidate=read(HERE/'audit/candidate_identity_audit.json')
    cleanup=read(HERE/'audit/postrun_process_check.json');bindings=read(HERE/'audit/source_bindings.json')
    assert a['passed'] and candidate['passed'] and cleanup['passed']
    assert a['native_calls_observed']==1 and a['physical_evaluation_attempts']==2
    assert a['retries']==a['formal_ABC_runs']==a['new_transforms']==a['model_builds']==0
    for name,h in bindings.items():assert sha(ROOT/name)==h,name
    frozen=ROOT/'work/budget_protocol_v2/candidate_on';plan=read(frozen/'plan.json')
    assert sha(frozen/'plan.json')==a['plan_sha256']
    for name,h in plan['workspace_files'].items():assert sha(ROOT/name)==h,name
    for name,h in plan['package_files'].items():assert sha(frozen/name)==h,name
    DEST.mkdir(exist_ok=False);names=[]
    for name in ('README.md','REPORT.txt','audit_run.py','package_delivery.py','prelaunch_identity.json'):
        shutil.copyfile(HERE/name,DEST/name);names.append(name)
    for p in sorted((HERE/'audit').glob('*.json')):
        shutil.copyfile(p,DEST/p.name);names.append(p.name)
    prefix=RUN.relative_to(ROOT).as_posix()+'/'
    binary=[]
    for name,h in bindings.items():
        if not name.startswith(prefix):continue
        relative='execution/'+name[len(prefix):];target=DEST/relative
        if target.suffix=='.mat':
            binary.append(dict(source=name,original_package_path=relative,archive_member=target.name,sha256=h,bytes=(ROOT/name).stat().st_size))
            continue
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        assert sha(target)==h;names.append(relative)
    # Respect repository ignore rules: preserve native MAT bytes inside a tracked ZIP.
    binary_archive='execution/matlab/native_mat_artifacts.zip'
    with zipfile.ZipFile(DEST/binary_archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for item in binary:z.write(ROOT/item['source'],item['archive_member'])
    with zipfile.ZipFile(DEST/binary_archive) as z:
        assert z.testzip() is None
        for item in binary:assert hashlib.sha256(z.read(item['archive_member'])).hexdigest()==item['sha256']
    (DEST/'binary_artifacts.json').write_text(json.dumps(dict(archive=binary_archive,members=binary,
        reason='Native .mat files are ignored by repository policy; ZIP preserves exact bytes without force-add.'),
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    names.extend([binary_archive,'binary_artifacts.json'])
    assert len(names)==len(set(names))
    (DEST/'SHA256SUMS').write_text(''.join(sha(DEST/n)+'  '+n+'\n' for n in sorted(names)),encoding='utf-8',newline='\n')
    names.append('SHA256SUMS')
    brief=REPO/'RESEARCH_BRIEF.md';old=brief.read_bytes();assert b'**D274' not in old
    index=old.index(b'**D273')
    paragraph=('**D274（2026-11-12，用户批准420秒方案唯一ON诊断，取得根LP及下界进展、返回原初解SAFE）：** '
        '按aa1dde9冻结计划和用户明确批准执行一次保存ON：原生MaxTime=240秒、方法420秒、响应截止370秒；'
        '无调参、补跑或A/B/C。实际1个MATLAB会话、1次intlinprog、2次完整评价；347个冻结来源及执行器身份不变。'
        '第67.469秒收到原生进入事件，第226.407秒收到rootlp、第226.688秒收到heuristics，提供根LP完成的后续阶段证据；'
        '原生下界0.7452555210277564 J超过平凡界0，但未独立严格认证。原生因时间限制以exitflag=2返回23780维向量，'
        '最终numnodes=0、numfeaspoints=1、relativegap原字段16.290137，没有最优性证明。'
        '向量通过新旧行数值准入、调度合法性和完整双场景SAFE，调度及能耗区间均与共同初解相同，'
        '没有不同调度或严格能耗改善。响应311.016秒、完整验证312.422秒；方法312.422秒、实际含收尾320.516秒。'
        'intlinprog调用墙钟243.169秒，实际MaxTime仍为240秒，全部证据在截止内；正常清理、无警告或错误。'
        '26项执行审计与5项候选核对通过，自有进程全部退出。启动主要等待位于Popen返回后至READY接收前，内部根因仍未知。'
        '结果支持继续准备同表达正式A/B/C，但不是历史OFF／新ON加速证据，未计重新构模及转换认证成本，'
        '未证明重复稳定性或互补门控相对收益。一次性授权已消费，科研运行停止；正式ABC仍需共同表达、独立构模预算接线及另行批准。'
        '见[唯一ON执行报告与原始证据](research/chapter3_on_A420_execution_20261112/README.md)。\n\n').encode('utf-8')
    new=old[:index]+paragraph+old[index:];assert new.replace(paragraph,b'',1)==old;brief.write_bytes(new)
    OUT.mkdir(exist_ok=True)
    for source,name in {'REPORT.txt':'R1_420秒ON诊断执行报告.txt','audit.json':'R1_420秒ON诊断审计.json',
                        'candidate_identity_audit.json':'R1_420秒ON候选身份核对.json'}.items():
        shutil.copyfile(DEST/source,OUT/name)
    archive=OUT/'R1_420秒ON诊断证据.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):z.write(DEST/name,name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in names:assert hashlib.sha256(z.read(name)).hexdigest()==sha(DEST/name),name
    result=dict(approved_subject_commit=a['approved_subject_commit'],plan_sha256=a['plan_sha256'],
        approval_sha256=a['approval_sha256'],archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,
        package_files=len(names),execution_files=sum(n.startswith('execution/') for n in names),
        raw_execution_artifacts=sum(n.startswith(prefix) for n in bindings),native_mat_artifacts=len(binary),
        audit_checks=len(a['checks']),candidate_checks=len(candidate['checks']),historical_brief_bytes_preserved=True,
        native_calls=1,complete_physical_evaluations=2,retries=0,formal_ABC_runs=0,authorization_consumed=True)
    (OUT/'R1_420秒ON诊断交付校验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
