"""Archive completed engineering review only; no scientific work or process creation."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REPO=ROOT/'work/publish_repo'
DEST=REPO/'research/chapter3_budget_protocol_20261112'
OUT=ROOT/'outputs'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    c=HERE/'candidate_on';receipt=read(c/'freeze_receipt.json');plan=read(c/'plan.json')
    assert receipt['tests_passed'] and receipt['state']=='FROZEN_TESTED_NOT_APPROVED_NOT_RUN'
    assert sha(c/'plan.json')==receipt['plan_sha256']==read(c/'plan.identity.json')['sha256']
    assert not (ROOT/plan['execution_directory']).exists()
    for name,expected in plan['workspace_files'].items():assert sha(ROOT/name)==expected,name
    for name,expected in plan['package_files'].items():assert sha(c/name)==expected,name
    assert read(c/'approval.template.json')['approved'] is False
    names=[p.relative_to(HERE).as_posix() for p in HERE.glob('*') if p.is_file()]
    names += ['candidate_on/'+name for name in plan['package_files']]
    names += ['candidate_on/'+name for name in ('plan.json','plan.identity.json','approval.template.json','freeze_receipt.json')]
    assert len(names)==len(set(names))
    DEST.mkdir(exist_ok=False)
    for name in sorted(names):
        target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(HERE/name,target);assert sha(target)==sha(HERE/name)
    sums=''.join(sha(DEST/name)+'  '+name+'\n' for name in sorted(names))
    (DEST/'SHA256SUMS').write_text(sums,encoding='utf-8',newline='\n');names.append('SHA256SUMS')
    brief=REPO/'RESEARCH_BRIEF.md';old=brief.read_bytes();assert b'**D273' not in old
    index=old.index(b'**D272')
    paragraph=('**D273（2026-11-12，仅预算与验收工程复核，零新增科研调用）：** '
        '基于143629e及7b723b1／63ad11f冻结证据，确认上次ON在intlinprog请求前因固定预算不足停止，不能记为ON数值失败。'
        '静态复核65.844秒启动、11861次READY读取、进程发布及单调时钟；没有内部时点，启动根因仍未知。'
        '新增独立候选预算控制、响应绝对截止、被动启动计时和分层回执；旧冻结文件、一次性消费记录及科学模型不改。'
        f'{receipt["tests"]}项纯控制测试通过，覆盖慢启动、预算不足、普通超时、空向量、迟到证据、候选拒绝及清理异常；'
        '实际新MATLAB会话、MILP／LP调用、完整热评价、大规模构模均为0。唯一推荐另行申请的科研动作是'
        '保存ON诊断原生240秒／方法总窗420秒，响应截止370秒、验证截止420秒，一次请求、无重试；'
        '候选冻结不等于批准，不复用旧授权。真实清理和控制器成本另报，不把方法窗冒充进程硬实时上限。'
        '正式A/B/C准备了统一600秒动态预算协议，完整12次Stage与66模式不变，各组独立构模初始化，'
        '普通超时不阻断其他组；共同表达和正式生命周期尚未冻结，仍不具备立即执行条件。'
        '保存入口不能与历史OFF拼成加速结论；互补门控仍只证明代数等价，求解收益未验证。见'
        '[预算与科学验收报告](research/chapter3_budget_protocol_20261112/README.md)。\n\n').encode('utf-8')
    new=old[:index]+paragraph+old[index:];assert new.replace(paragraph,b'',1)==old;brief.write_bytes(new)
    OUT.mkdir(exist_ok=True)
    deliver={'REPORT.txt':'R1预算与科学验收协议报告.txt','ABC_PROTOCOL.txt':'R1正式ABC动态预算协议.txt',
             'candidate_on/plan.json':'R1下一次ON冻结候选.json','candidate_on/freeze_receipt.json':'R1预算协议冻结回执.json'}
    for source,name in deliver.items():shutil.copyfile(DEST/source,OUT/name)
    archive=OUT/'R1预算协议证据.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):z.write(DEST/name,name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in names:assert z.read(name)==(DEST/name).read_bytes()
    delivery=dict(package_files=len(names),plan_sha256=receipt['plan_sha256'],tests=receipt['tests'],
        history_files_unchanged=receipt['historical_files_unchanged'],archive_bytes=archive.stat().st_size,
        archive_sha256=sha(archive),historical_brief_bytes_preserved=True,scientific_calls_this_turn=0,
        new_execution_ledger_exists=False,approval=False)
    (OUT/'R1预算协议交付校验.json').write_text(json.dumps(delivery,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(delivery,ensure_ascii=False))


if __name__=='__main__':main()
