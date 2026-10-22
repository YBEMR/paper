"""Independent K167 file-integrity binding; imports no scientific modules."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
ROOT=REPO/'research/chapter3_experiments'
RESULTS=ROOT/'results'
ALLOWED='research/chapter3_experiments/formal_milp.py'


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(1048576):digest.update(block)
    return digest.hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def differences(values):
    return [name for name,digest in values.items()
            if not (REPO/name).is_file() or sha(REPO/name)!=digest]


def call_inventory():
    old,resume=RESULTS/'deadline_execution01',RESULTS/'deadline_resume01'
    slots=read(old/'declaration.json')['slots'];files={};missing=[]
    for slot in slots[:16]:
        camp=old if slot['ordinal']<=2 else resume
        for suffix in ('.json','_method_return.json','_result.json','_artifact_sha256.json'):
            path=camp/'claims'/(slot['slot_id']+suffix)
            if not path.is_file():missing.append(path.relative_to(REPO).as_posix());continue
            files[path.relative_to(REPO).as_posix()]=sha(path)
        folder=camp/'calls'/slot['problem_id']/slot['id']
        for path in sorted(folder.rglob('*')):
            if path.is_file():files[path.relative_to(REPO).as_posix()]=sha(path)
    unstarted=[]
    for slot in slots[16:]:
        for camp in (old,resume):
            if (camp/'claims'/(slot['slot_id']+'.json')).exists():
                unstarted.append(slot['slot_id'])
    return files,missing,unstarted


def snapshot():
    source_path=RESULTS/'deadline_numerical_readonly01/before.json'
    baseline=read(source_path)
    source=baseline['source_sha256'];prior=baseline['prior_artifact_sha256'];target=baseline['target_sha256']
    changes=differences(source)
    calls,missing,unstarted=call_inventory()
    auxiliary={}
    for path in [RESULTS/'deadline_resume01/declaration.json',RESULTS/'deadline_resume01/process_terminal.json',
        RESULTS/'deadline_resume01/worker_terminal.json',RESULTS/'deadline_resume01/analysis01/facts.json',
        RESULTS/'deadline_cutoff_repair01/post_summary.json',RESULTS/'deadline_cutoff_repair01/repair_review.json']:
        if path.is_file():auxiliary[path.relative_to(REPO).as_posix()]=sha(path)
    return {'protocol':'K167-independent-integrity-before-v1',
        'K165_before_sha256':sha(source_path),'source_sha256':source,
        'source_count':len(source),'allowed_old_source_change':ALLOWED,
        'initial_old_source_changes':changes,
        'initial_unexpected_old_source_changes':[x for x in changes if x!=ALLOWED],
        'prior_artifact_sha256':prior,'target_sha256':target,
        'prior_artifact_count':len(prior),'target_count':len(target),
        'prior_mismatches':differences(prior),'target_mismatches':differences(target),
        'archived_call_files_sha256':calls,'archived_call_files_count':len(calls),
        'missing_original_16_claims':missing,'unexpected_started_remaining_slots':unstarted,
        'declarations_terminals_analysis_repair_sha256':auxiliary,
        'consumed':16,'unstarted':24,'new_model_solver_thermal_or_post_calls':0}


def verify(before):
    changes=differences(before['source_sha256'])
    mismatches={key:differences(before[key]) for key in (
        'prior_artifact_sha256','target_sha256','archived_call_files_sha256',
        'declarations_terminals_analysis_repair_sha256')}
    _,missing,unstarted=call_inventory()
    return {'protocol':'K167-independent-integrity-after-v1',
        'source_count':248,'allowed_old_source_change':ALLOWED,'old_source_changes':changes,
        'unexpected_old_source_changes':[x for x in changes if x!=ALLOWED],
        'mismatches':mismatches,'missing_claims':missing,'unexpected_started_remaining_slots':unstarted,
        'all_other_247_sources_and_old_artifacts_preserved':not any(mismatches.values())
            and not missing and not unstarted and not any(x!=ALLOWED for x in changes),
        'consumed':16,'unstarted':24,'new_model_solver_thermal_or_post_calls':0}


if __name__=='__main__':
    result=snapshot()
    assert result['source_count']==248 and result['prior_artifact_count']==432 and result['target_count']==30
    assert not any(result[k] for k in ('initial_unexpected_old_source_changes','prior_mismatches',
        'target_mismatches','missing_original_16_claims','unexpected_started_remaining_slots'))
    with (HERE/'before_manifest.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print({'before_bound':True,'old_sources':248,'allowed_change':ALLOWED,
        'prior':432,'target':30,'archived_call_files':result['archived_call_files_count'],
        'consumed':16,'unstarted':24,'new_scientific_calls':0})
