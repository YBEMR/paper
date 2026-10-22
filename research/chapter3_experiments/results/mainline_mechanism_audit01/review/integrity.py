"""K169 independent original-source/accounting protection: read-only stdlib."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPO=HERE.parents[4]
RESULTS=ROOT/'results'
PILOT=Path('C:/Users/86130/.codex/worktrees/hetero-thermal-pilot/11111')

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as s:
        while b:=s.read(1048576):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def save(p,v):
    with Path(p).open('x',encoding='utf-8') as s:json.dump(v,s,ensure_ascii=False,indent=2);s.write('\n')
def diff(d):return [p for p,h in d.items() if not (REPO/p).is_file() or sha(REPO/p)!=h]

def baseline():
    k168=RESULTS/'whole_native_diagnostic_precheck01/run01/real_preparation'
    declaration=read(k168/'declaration.json')
    before=read(RESULTS/'whole_augmented_native_preparation01/independent_review/before_manifest.json')
    bindings={key:before[key] for key in ('prior_artifact_sha256','target_sha256',
        'original16_call_files_sha256','ledger_declaration_terminal_sha256')}
    sources={p:sha(REPO/p) for p in declaration['source_sha256']}
    pending={}
    for p in (k168/'declaration.json',k168/'ledger.json',k168/'validation.json',
        ROOT/'whole_native_diagnostic/protocol.md',
        RESULTS/'whole_augmented_native_preparation01/independent_review/final_review.json'):
        pending[p.relative_to(REPO).as_posix()]=sha(p)
    old=RESULTS/'deadline_execution01';resume=RESULTS/'deadline_resume01'
    slots=read(old/'declaration.json')['slots'];claims=[]
    for slot in slots[16:]:
        for camp in (old,resume):
            p=camp/'claims'/(slot['slot_id']+'.json')
            if p.exists():claims.append(p.relative_to(REPO).as_posix())
    assert not any(diff(d) for d in bindings.values()) and not claims
    assert declaration['plan']['authorized'] is False and declaration['research_calls_consumed']==0
    available={p.relative_to(PILOT).as_posix():sha(p) for p in sorted((PILOT/'research/hetero_thermal_pilot').glob('C*.md'))}
    result={'protocol':'K169-independent-mechanism-before-v1','source_sha256':sources,'source_count':len(sources),
        **bindings,'K168_pending_sha256':pending,'K168_pending_unconsumed':True,
        'pilot_head_ref':(REPO/'.git/refs/heads/research/hetero-thermal-pilot').read_text('ascii').strip(),
        'pilot_available_Creports_sha256':available,
        'original_consumed':16,'original_unstarted':24,'unexpected_claims':claims,
        'new_science':{'model':0,'candidate_evaluation':0,'thermal':0,'solver':0,'post':0},
        'new_target_directory_excluded':HERE.parent.relative_to(REPO).as_posix()}
    save(HERE/'before_manifest.json',result)
    print({'sources':len(sources),'pilot_Creports':len(available),'original':16,'unstarted':24,'K168_pending':True,'scientific_calls':0})

def verify():
    before=read(HERE/'before_manifest.json')
    changes={key:diff(before[key]) for key in ('source_sha256','prior_artifact_sha256','target_sha256',
        'original16_call_files_sha256','ledger_declaration_terminal_sha256','K168_pending_sha256')}
    old,resume=RESULTS/'deadline_execution01',RESULTS/'deadline_resume01'
    slots=read(old/'declaration.json')['slots'];unexpected=[]
    for slot in slots[16:]:
        for camp in (old,resume):
            p=camp/'claims'/(slot['slot_id']+'.json')
            if p.exists():unexpected.append(p.relative_to(REPO).as_posix())
    checks={'all_sources_and_old_archives_unchanged':not any(changes.values()),
        'old16_original_files400':len(before['original16_call_files_sha256'])==400,
        'K168_still_pending':read(RESULTS/'whole_native_diagnostic_precheck01/run01/real_preparation/declaration.json')['plan']['authorized'] is False,
        'old24_still_have_no_claims':len(slots[16:])==24 and not unexpected,
        'pilot_worktree_report_files_unchanged':all(sha(PILOT/p)==h for p,h in before['pilot_available_Creports_sha256'].items())}
    assert all(checks.values()),changes
    save(HERE/'after_manifest.json',{'protocol':'K169-independent-mechanism-after-v1','checks':checks,
        'changes':changes,'unexpected_old24_claims':unexpected,'passed':True,'before_sha256':sha(HERE/'before_manifest.json'),'scientific_calls':0})
    print(checks)

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['before','after'])
    (baseline if a.parse_args().mode=='before' else verify)()
