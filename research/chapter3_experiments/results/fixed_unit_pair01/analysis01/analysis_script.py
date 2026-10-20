"""K129 failed pair audit: never reconstruct missing method evidence."""
from pathlib import Path
from fractions import Fraction as F
import csv,hashlib,importlib.util,json
REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'research/chapter3_experiments/results/fixed_unit_pair01'
P=REPO/'research/chapter3_experiments/results/night_k127_run02/analysis01/analysis_script.py'
spec=importlib.util.spec_from_file_location('k127_readonly',P); a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')
def main():
    ledger=a.read(ROOT/'ledger.json'); declaration=a.read(ROOT/'declaration.json')
    assert ledger['state']=='BLOCKED' and ledger['consumed']==2
    rows={r['id']:r for r in ledger['calls']}
    assert rows['old_n1']['state']=='COMPLETED' and rows['all_opp_start']['state']=='TECHNICAL_BLOCK'
    assert not (ROOT/'all_opp_start/result.json').exists()
    out=ROOT/'analysis01'; out.mkdir(exist_ok=False)
    originals=[ROOT/'ledger.json',ROOT/'declaration.json',ROOT/'old_n1/result.json',ROOT/'claims/all_opp_start_result.json']
    before={str(p.relative_to(ROOT)):sha(p) for p in originals}
    job={'id':'old_n1','method':'n1','condition':'base'}
    old=a.analyze_job(ROOT,job,rows['old_n1'],{'input_identities':{'base':{'instance_sha256':declaration['input_sha256']}}})
    assert old['final_SAFE_receipt_verified'] and not old['stored_receipt_errors']
    seed=old['initialisation_selected_candidate']; views=[]; models=[]
    for k,scene in enumerate(a.read(ROOT/'input_instance.json')['scenarios']):
        p=ROOT/'all_opp_start'/f'initial_scene_{k:03d}.json'; before[str(p.relative_to(ROOT))]=sha(p)
        checkpoint=a.read(p); sid=scene['id']
        assert checkpoint['candidate']=={'scenes':{sid:seed['scenes'][sid]}}
        assert checkpoint['state']=='INITIAL_POINT_READY' and checkpoint['evaluation']['state']=='SAFE'
        views.append({'scene':sid,'state':checkpoint['state'],
            'candidate_equals_old_fresh_seed_scene':True,'checkpoint_completed_at_s':checkpoint['completed_at_s'],
            'model_view_SAFE_at_s':checkpoint['evaluation']['completed_at_elapsed_s'],
            'evaluation_state':'model_view_SAFE_only','not_original_full_aggregate':True})
        p=ROOT/'all_opp_start'/f'build_scene_{k:03d}.jsonl'; before[str(p.relative_to(ROOT))]=sha(p)
        model=json.loads(p.read_text(encoding='utf-8').splitlines()[-1]); assert model['status']=='MODEL_CONSTRUCTED'
        models.append({'scene':sid,**{x:model[x] for x in ['status','method_elapsed_seconds','options','variables','binary_variables','rows','nonzeros_in_rows','events_per_scene']}})
    worker=ROOT/'all_opp_start/matlab'
    assert not list(worker.glob('request_*.request.json'))
    frozen_ok=all(sha(ROOT/'source_snapshot'/name)==h for name,h in declaration['source_sha256'].items())
    assert frozen_ok
    new={'state':'TECHNICAL_BLOCK','safe_upper_bound_J':None,'full_method_result_exists':False,
        'method_timing_unavailable':True,'wrapper_wall_s':rows['all_opp_start']['wrapper_wall_s'],
        'final_archive_exception':rows['all_opp_start']['error'],'earliest_cause':'unknown; final archive may mask earlier failure',
        'native_request_files':0,'native_entry_evidence':False,'views':views,'models':models,
        'missing_U_not_reconstructed':True,'posthoc_work':'saved checkpoint/model log read only'}
    facts={'protocol':declaration['protocol'],'verification_scope':'saved records only; no heat replay/solve/U recovery',
        'reused_audit_source':{'path':P.relative_to(REPO).as_posix(),'sha256':sha(P)},'old':old,'new':new,
        'comparison':{'quality_test_completed':False,'strict_new_vs_old':None,'new_vs_HEFT_gap':None,
            'reason':'new method result unavailable after technical failure',
            'fresh_seed_scene_candidates_equal':True,'full_new_seed_receipt_and_interval_unavailable':True,
            'consumed_method_calls':2,'wrapper_total_s':sum(r['wrapper_wall_s'] for r in rows.values()),
            'old_method_s':old['timing']['method_elapsed_s'],'new_method_s':None,
            'retry':False,'new_temperature_conditions':0},'frozen_snapshot_unchanged':frozen_ok,'raw_hashes':before}
    for rel,h in before.items():assert sha(ROOT/rel)==h
    facts['raw_unchanged']=True; save(out/'facts.json',facts)
    with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['method','state','safe_U_J','method_s','wrapper_s','quality_valid']; w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        w.writerow(dict(method='old_N1',state='SAFE',safe_U_J=old['final_U_J'],method_s=old['timing']['method_elapsed_s'],wrapper_s=rows['old_n1']['wrapper_wall_s'],quality_valid=True))
        w.writerow(dict(method='fixed_unit_all_OPP_start',state='TECHNICAL_BLOCK',safe_U_J='',method_s='',wrapper_s=new['wrapper_wall_s'],quality_valid=False))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    points=old['updates']; xs=[x['at_s'] for x in points];ys=[float(F(x['energy_J'][1])) for x in points]
    fig,ax=plt.subplots(figsize=(7.5,4))
    ax.step(xs+[old['timing']['method_elapsed_s']],ys+[ys[-1]],where='post',label='old N1 SAFE U')
    ax.hlines(float(F(old['L0_gap']['L0_J'])),0,old['timing']['method_elapsed_s'],linestyle=':',label='independent full-domain L0')
    ax.text(.98,.95,'New method: technical block; no full-domain U saved',transform=ax.transAxes,ha='right',va='top',fontsize=9)
    ax.set(xlabel='Billed method time (s)',ylabel='Weighted system energy (J)');ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(out/'old_n1_energy_bounds.png',dpi=180);plt.close(fig)
    lines=['# K129：实现与预检完成，质量配对因归档故障未完成','',
        '材料类型：冻结调用的只读结果审计。仅核存档，不重算温度、不补求解、不恢复缺失的预算内U。','',
        '| 调用 | 状态 | 原输入全场景安全U/J | 方法耗时/s | 包装耗时/s |',
        '|---|---|---:|---:|---:|',
        f"| 旧N1 | SAFE／正常完成 | {float(F(old['final_U_J'])):.12f} | {old['timing']['method_elapsed_s']:.3f} | {rows['old_n1']['wrapper_wall_s']:.3f} |",
        f"| 全Stage工作点／时序 | TECHNICAL_BLOCK | 未保存，不补造 | 未恢复 | {new['wrapper_wall_s']:.3f} |",'',
        '新版已完成AB／AC两个模型：441／405选项，271／296事件，8525／13810变量，39733／89973行；两个模型视图的初始候选与本次旧N1新种子逐Stage相同，x0检查点均READY。它们不是原输入全场景聚合回执，不能加权补记方法安全U。',
        '最终归档input_config.json.tmp发生OSError errno22，外层账本正确记技术失败。该异常可能遮蔽更早的启动／归档错误；session停留pid记录、READY存在、无request或closed回执，最早原因未知，不归因于MILP数学模型或算法质量。',
        '新调用已消费，未重启／补跑／延时；两调用包装总计196.328秒。旧N1方法165.672秒；新调用缺正式method时序，25.265秒仅包装墙钟，不冒作solver时间或完整方法时序。',
        '事后仅向本次worker写stop，观察其pid与已知子进程退出；另存清理记录，不补写原closed或SAFE回执。后续写入探针成功，仍不足以定位先前瞬态错误。',
        '本次未完成首要的新版对旧N1严格节能检验，也无法判断是否缩小与HEFT的差距。旧N1全域L0未闭合，内部界不升级为全域最优。',
        '', '旧N1已存安全U轨迹：[图](old_n1_energy_bounds.png)；细节见facts.json、comparison.csv、原ledger及独立审查。技术修复另行预检，不回改原调用源码快照或结果。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');(out/'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'old_SAFE_verified':True,'new_technical_block':True,'calls':2,'wrapper_s':facts['comparison']['wrapper_total_s'],'new_U':None}))
if __name__=='__main__':main()
