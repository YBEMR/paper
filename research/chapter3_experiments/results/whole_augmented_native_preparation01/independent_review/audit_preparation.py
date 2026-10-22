"""K168 read-only preparation audit: stdlib, hashes and archived JSON only."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPO=HERE.parents[4]
RESULTS=ROOT/'results'
OLD_REVIEW=RESULTS/'whole_augmented_precheck01/independent_review'

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as stream:
        while b:=stream.read(1048576):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def relative(p):return Path(p).relative_to(REPO).as_posix()
def save(p,v):
    with Path(p).open('x',encoding='utf-8') as stream:json.dump(v,stream,ensure_ascii=False,indent=2);stream.write('\n')
def mismatches(mapping):return [p for p,h in mapping.items() if not (REPO/p).is_file() or sha(REPO/p)!=h]

def baseline():
    prior=read(OLD_REVIEW/'before_manifest.json')
    after=read(OLD_REVIEW/'after_manifest02.json')
    files=set(prior['source_sha256'])
    files.update(['research/chapter3_experiments/whole_augmented.py','research/chapter3_experiments/precheck_whole_augmented.py'])
    sources={p:sha(REPO/p) for p in sorted(files)}
    auxiliary=dict(prior['declarations_terminals_analysis_repair_sha256'])
    for folder in ('deadline_execution01','deadline_resume01'):
        for name in ('ledger.json','declaration.json','status.json','process_terminal.json','worker_terminal.json','launcher_claim.json','launcher_result.json'):
            p=RESULTS/folder/name
            if p.is_file():auxiliary[relative(p)]=sha(p)
    stage_evidence={}
    for p in [OLD_REVIEW/'final_review02.json',OLD_REVIEW/'review_manifest02.json',OLD_REVIEW/'after_manifest02.json',
        RESULTS/'whole_augmented_precheck01/run04/checks.json',RESULTS/'deadline_numerical_readonly01/history/facts.json',
        RESULTS/'deadline_numerical_readonly01/history/timing_scope.md']:
        stage_evidence[relative(p)]=sha(p)
    old=RESULTS/'deadline_execution01';resume=RESULTS/'deadline_resume01'
    slots=read(old/'declaration.json')['slots'];unexpected=[]
    for slot in slots[16:]:
        for camp in (old,resume):
            p=camp/'claims'/(slot['slot_id']+'.json')
            if p.exists():unexpected.append(relative(p))
    checks={'K167_before_preserved':not mismatches(prior['prior_artifact_sha256']) and not mismatches(prior['target_sha256']),
        'K167_final_passed':read(OLD_REVIEW/'final_review02.json')['passed'] is True,
        'current_whole_matches_K167':sources['research/chapter3_experiments/whole_augmented.py']==after['whole_augmented_sha256'],
        'current_formal_matches_K167':sources['research/chapter3_experiments/formal_milp.py']==after['formal_hook_sha256'],
        'original400_preserved':len(prior['archived_call_files_sha256'])==400 and not mismatches(prior['archived_call_files_sha256']),
        'remaining24_no_claims':len(slots[16:])==24 and not unexpected}
    assert all(checks.values()),checks
    result={'protocol':'K168-native-preparation-independent-before-v1','checks':checks,'passed':True,
        'source_count':len(sources),'source_sha256':sources,
        'prior_artifact_sha256':prior['prior_artifact_sha256'],'target_sha256':prior['target_sha256'],
        'original16_call_files_sha256':prior['archived_call_files_sha256'],'original16_call_files_count':400,
        'ledger_declaration_terminal_sha256':auxiliary,'previous_evidence_sha256':stage_evidence,
        'unstarted24_slot_ids':[s['slot_id'] for s in slots[16:]],'unexpected_claims':unexpected,
        'original_consumed':16,'original_unstarted':24,
        'scientific_calls':0,'execution_authorization':False}
    save(HERE/'before_manifest.json',result)
    facts=read(RESULTS/'deadline_numerical_readonly01/history/facts.json')
    r2=next(r for r in facts['targeted_receipts'] if r['condition']=='Deadline' and r['replicate']=='R2')
    observation={k:r2[k] for k in ['problem_id','source_folder','root_s','root_budget_exhausted',
        'first_initial_SAFE_s','initial_SAFE_U_J','variables','rows','retained_options','formulation',
        'native_MaxTime_s','native_intlinprog_call_s','response_exitflag','response_x_empty',
        'response_final_numfeaspoints','response_final_numnodes','solver_x0_acceptance','numerical_consistency_state','native_options']}
    observation.update(protocol='K168-archived-original-options-only-v1',
        scope='Archival facts only. Future MaxTime must use new root remaining time; previous x0/SAFE are not free initialization. Old labels/payload are not transformed here.',
        facts_sha256=sha(RESULTS/'deadline_numerical_readonly01/history/facts.json'),scientific_calls=0)
    save(HERE/'archived_reference.json',observation)
    print({'before_passed':True,'sources':len(sources),'original_files':400,'original_consumed':16,'unstarted':24,'scientific_calls':0})

if __name__=='__main__':baseline()
