"""Read-only final SAFE identity check shared by A mock and B real wiring."""
from h02_pair_preflight.common import require,sha,exact,candidate_identity,timely
from h02_pair_preflight.receipts import safe_receipt,technical_issues

def verify_final_export(packet,result):
    c,i=packet['planner']['config'],packet['planner']['instance']
    candidate=result.get('safe_candidate')
    require(result.get('method')=='heft' and result.get('seed') is None,'FINAL_METHOD_IDENTITY')
    if candidate is None:
        require(result.get('state')!='SAFE' and not any(r.get('accepted_safe') for r in result.get('evaluations',[])),'RECORDER_BEST_MISSING')
        if result.get('reason')=='DECLARED_SEARCH_COMPLETED':
            require(result.get('problem_id')==i['id'] and result.get('input_sha256')==sha(i) and result.get('timing',{}).get('limit_s')==120,'NO_SAFE_FINAL_IDENTITY')
        return {'best':None,'technical_details':technical_issues(result)}
    require(result.get('state')=='SAFE','FINAL_TOP_LEVEL_NOT_SAFE')
    require(result.get('problem_id')==i['id'] and result.get('input_sha256')==sha(i),'METHOD_RESULT_IDENTITY')
    require(result.get('timing',{}).get('limit_s')==120,'FINAL_ROOT_LIMIT_DRIFT')
    safe=[]
    for row in result.get('evaluations',[]):
        if row.get('accepted_safe') is True:
            cand=row['candidate']; identity=candidate_identity(i,cand)
            require(row.get('candidate_sha256')==identity['candidate_raw_sha256'],'RECORDER_CANDIDATE_HASH')
            safe_receipt(i,cand,row['evaluation'],c['accuracy_targets'],120)
            formed=row['evaluation']['completed_at_elapsed_s']; returned=row.get('returned_at_s')
            require(timely(returned,float('inf')) and returned>=formed,'RECORDER_RETURN_TIME')
            safe.append(row)
    require(safe,'NO_ACCEPTED_SAFE_RECORD')
    best=min(safe,key=lambda row:exact(row['evaluation']['safe_upper_bound_J']))
    require(candidate==best['candidate'] and result.get('evaluation')==best['evaluation'] and exact(result['safe_upper_bound_J'])==exact(best['evaluation']['safe_upper_bound_J']),'NOT_CANDIDATE_RECORDER_BEST')
    require(result.get('safe_solution_source')==best['source'],'FINAL_SOURCE_NOT_RECORDER_BEST')
    return {'best':best,'identity':candidate_identity(i,candidate),'technical_details':technical_issues(result)}
