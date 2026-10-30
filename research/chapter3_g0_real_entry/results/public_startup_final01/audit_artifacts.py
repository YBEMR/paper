"""Read-only hash audit; no scientific modules imported or evaluations run."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    manifest=json.loads((HERE/'source_manifest.json').read_text(encoding='utf-8'))
    checked={}
    for group in ('source_sha256','protected_legacy_sha256'):
        items=manifest[group]
        checked[group]={'count':len(items),'drift':[p for p,h in items.items() if sha(ROOT/p)!=h]}
    old=ROOT/'research/chapter3_g0_real_entry/results/real_entry01_analysis/integrity_audit.json'
    old=json.loads(old.read_text(encoding='utf-8'))
    checks={
      'old_plan':(ROOT/'research/chapter3_g0_real_entry/results/real_entry_plan01/plan.json',old['plan_sha256']),
      'old_batch':(ROOT/'research/chapter3_g0_real_entry/results/real_entry01/batch.json',old['original_batch_sha256']),
      'old_claim':(Path(old['claim_path']),old['claim_sha256']),
      'independent_review':(ROOT/'research/G0第一阶段公共启动_主线6独立审查_20261030.md','977e661d1ae15c7ae3f96c6003d2a00a5e7f59753988ce53b35c0cd500dfbb69'),
    }
    for key,(path,expected) in checks.items():
        actual=sha(path);checked[key]={'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':actual,'matches':actual==expected}
    tests=json.loads((HERE/'checks.json').read_text(encoding='utf-8'))
    manual=json.loads((ROOT/'research/chapter3_g0/results/manual09_public_start_regression/checks.json').read_text(encoding='utf-8'))
    ok=(all(not checked[g]['drift'] for g in ('source_sha256','protected_legacy_sha256'))
        and all(checked[k]['matches'] for k in checks)
        and tests['passed']==tests['total']==79 and manual['passed']==manual['total']==32)
    result={'kind':'READ_ONLY_ARTIFACT_AUDIT_NOT_REAL_VALIDATION','passed':ok,'checked':checked,
            'real_scientific_calls':0,'new_scientific_authorization':False,
            'execution_organization':'phase_public_startup_v1',
            'legacy_organization':'legacy_slot_startup_v1',
            'new_scientific_plan_created':False,'old_claim_reusable':False,
            'final_mock_tests':79,'old_manual_tests':32,'old_manual_assertions':manual['assertions']}
    (HERE/'artifact_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':ok,'source_files':len(manifest['source_sha256']),
                      'protected_files':len(manifest['protected_legacy_sha256'])}))
    if not ok:raise SystemExit(1)

if __name__=='__main__':main()
