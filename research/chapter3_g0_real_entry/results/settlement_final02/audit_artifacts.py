"""Recheck source/protected/history hashes. No scientific imports."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    manifest=read(HERE/'source_manifest.json')
    groups={k:{'count':len(manifest[k]),'drift':[p for p,h in manifest[k].items() if sha(ROOT/p)!=h]}
            for k in ('source_sha256','protected_legacy_sha256')}
    history=read(ROOT/'research/chapter3_g0_real_entry/results/public_start_real01_analysis/raw_files_sha256.json')
    ignored=[p for p in history if p.endswith('.mat')]
    history_drift=[p for p,h in history.items() if p not in ignored and sha(ROOT/p)!=h]
    old=read(ROOT/'research/chapter3_g0_real_entry/results/real_entry01_analysis/integrity_audit.json')
    unchanged={
      'original_batch':sha(ROOT/'research/chapter3_g0_real_entry/results/real_entry01/batch.json')==old['original_batch_sha256'],
      'original_claim':sha(Path(old['claim_path']))==old['claim_sha256'],
      'public_claim':sha(ROOT/'research/chapter3_g0_real_entry/claims/e9bea2f70602e815f8efe6192241b5b6d596dbabbc2f15a6d8f3202450c78243.json')==
          read(ROOT/'research/chapter3_g0_real_entry/results/public_start_real01_analysis/integrity_audit.json')['claim_sha256']}
    checks=read(HERE/'checks.json');manual=read(ROOT/'research/chapter3_g0/results/manual10_settlement_regression/checks.json')
    ids=[read(p)['id'] for p in (HERE/'cases').glob('*.json')]
    traces=[read(p) for p in (HERE/'scratch').glob('settlement-coordinator-*/trace.json')]
    assert len(traces)==1
    trace=traces[0]
    lifecycle={'phase2_started_s':trace['phase2_started_s'],'control_seconds':trace['settlement_summary']['control_seconds'],
        'session_attempts':trace['session_lifecycle']['attempts'],
        'safe_candidate_unchanged':trace['S0']['candidate']==trace['final']['candidate'],
        'safe_energy_unchanged':trace['S0']['U_J']==trace['final']['U_J'],
        'safe_scope_unchanged':trace['S0']['scope']==trace['final']['scope'],
        'safe_formation_time_unchanged':trace['S0']['completed_at_elapsed_s']==trace['final']['completed_at_elapsed_s'],
        'kind':'FAKE_LIFECYCLE_NOT_REAL_RESULT'}
    passed=(all(not g['drift'] for g in groups.values()) and not history_drift and all(unchanged.values())
        and checks['passed']==checks['total']==len(set(ids))==len(ids)==89
        and manual['passed']==manual['total']==32 and manual['protection_passed']
        and all(lifecycle[k] for k in ('safe_candidate_unchanged','safe_energy_unchanged','safe_scope_unchanged','safe_formation_time_unchanged')))
    record={'kind':'READ_ONLY_HASH_AUDIT_AND_EXISTING_MOCK_RECEIPTS','passed':passed,
        'source_and_protected':groups,'history_drift':history_drift,'history_ignored_local_mat':ignored,
        'claims_and_old_result_unchanged':unchanged,'unique_mock_tests':len(set(ids)),
        'ten_new_groups':[i for i in ids if '.SettlementTests.test_group' in i],
        'old_manual_tests':32,'old_manual_assertions':manual['assertions'],
        'fake_lifecycle':lifecycle,'new_real_calls':0,'new_matlab_processes':0,
        'new_integrations':0,'new_scientific_approval_or_claim':False}
    (HERE/'artifact_audit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':passed,'active_sources':groups['source_sha256']['count'],
        'protected_files':groups['protected_legacy_sha256']['count'],'new_groups':len(record['ten_new_groups']),
        'lifecycle':lifecycle},ensure_ascii=False))
    assert passed

if __name__=='__main__':main()
