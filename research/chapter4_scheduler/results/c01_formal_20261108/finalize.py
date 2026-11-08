"""Verify frozen work and preserve a complete final evidence manifest."""
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
import json
import subprocess
import sys
import time

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[3]
sys.path[:0]=[str(REPO),str(REPO/'research/chapter3_experiments')]
from research.chapter4_scheduler.c01.formal import verify
from research.chapter4_scheduler.mechanism_check.run import read,save,sha

entered=time.monotonic();started=datetime.now(timezone.utc).isoformat()
plan=read(OUT/'execution/plan.json');audit=read(OUT/'audit.json');metrics=read(OUT/'metrics.json')
assert audit['passed'] and metrics['batch']['completed'] and all(r['success'] for r in metrics['rows'])
assert (OUT/'summary.md').exists()
verify(plan,protected=True)
statistics=metrics['statistics'];sa=statistics['SA']
entry=(f"**第四章 C01 七次正式比较已完成（2026-11-08）。** [报告](research/chapter4_scheduler/results/c01_formal_20261108/summary.md)、"
    f"[逐组指标](research/chapter4_scheduler/results/c01_formal_20261108/metrics.csv)、[独立冻结计划](research/chapter4_scheduler/results/c01_formal_20261108/execution/plan.json)。"
    f"原C1/C2显式DAG/230ms/全部72模式及物理模型不变，新入口直接调用原300秒主对照分派，HEFT、ON各一次及原SA101–105共七次，另七次最多60秒同评价器复评，全部最终SAFE及post通过，无补跑。"
    f"HEFT/ON为0.882913165881/0.839132424261 J，ON较HEFT降低{statistics['ON_energy_reduction_vs_HEFT_percent']:.6f}%；"
    f"SA五种子中位{float(F(sa['energy_upper_J_median_among_successes'])):.12f} J，范围"
    f"{float(F(sa['energy_upper_J_range_among_successes'][0])):.12f}–{float(F(sa['energy_upper_J_range_among_successes'][1])):.12f}，安全复评成功5/5。"
    f"方法内{statistics['counts_total']['evaluation_attempts']}实际评价/{statistics['counts_total']['validated_SAFE_receipts']}完整SAFE/"
    f"{statistics['counts_total']['returned_unresolved_receipts']}截止未决/{statistics['counts_total']['cache_hits']}缓存，实际批次{metrics['batch']['wall_s']:.3f}秒。"
    f"192项人工/模拟预检和{audit['assertion_count']}条只读断言通过，524冻结身份/1117旧文件不变。"
    f"HEFT/ON独立相同增强初始化，SA保留原生初始化；非统一初始状态消融。C01已见、无OFF消融/最优证明/独立数值实现，不能单独归因阻塞边或泛化。"
    f"最终峰温上界最高{statistics['maximum_final_peak_upper_degC']:.6f}°C，未展示紧热边界收益。本轮停止，未扩例/提交/推送/合并。\n\n")
brief=REPO/'RESEARCH_BRIEF.md';before=brief.read_bytes();before_hash=sha(brief)
marker='更新：2026-11-08。\n\n'.encode();assert before.count(marker)==1
left,right=before.split(marker,1);insertion=entry.encode();after=left+marker+insertion+right
assert after.replace(insertion,b'',1)==before
brief.write_bytes(after)
save(OUT/'brief_update.json',{'utc':datetime.now(timezone.utc).isoformat(),'before_sha256':before_hash,
    'after_sha256':sha(brief),'prior_bytes_preserved':True,'inserted_text':entry})
verify(plan,protected=True)
checks={}
for argv in (['git','rev-parse','HEAD'],['git','branch','--show-current'],['git','status','--short'],['git','diff','--check']):
    start=time.monotonic();r=subprocess.run(argv,cwd=REPO,capture_output=True,text=True)
    checks[' '.join(argv)]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'wall_s':time.monotonic()-start}
assert checks['git diff --check']['exit_code']==0
verification={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),
    'wall_s':time.monotonic()-entered,'argv':sys.argv,'cwd':str(REPO),
    'git_read_only':checks,'source_identities_verified':len(plan['source_sha256']),
    'protected_existing_files_verified':len(plan['protected_sha256']),
    'no_retry_or_extra_case':True,'no_commit_push_merge':True,'prior_brief_bytes_preserved':True}
save(OUT/'final_verification.json',verification)
manifest={p.relative_to(REPO).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='completion_record.json'}
save(OUT/'completion_record.json',{'ended_utc':datetime.now(timezone.utc).isoformat(),
    'subject_commit':plan['subject_commit'],'branch':plan['branch'],'plan_sha256':metrics['plan_sha256'],
    'actual_method_calls':7,'actual_post_calls':7,'batch':metrics['batch'],'statistics':statistics,
    'new_research_calls_after_batch':0,'final_verification':verification,
    'complete_result_file_manifest_sha256':manifest,
    'limits':'Already exposed C01 C1/C2 only; native initializations; no OFF ablation, independent numerical implementation or optimality claim; no push/merge'})
print(json.dumps({'complete':True,'files':len(manifest),'statistics':statistics,'final_verification_s':verification['wall_s']},ensure_ascii=False),flush=True)
