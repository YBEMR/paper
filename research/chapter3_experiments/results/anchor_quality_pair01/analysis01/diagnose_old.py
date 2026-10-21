"""K151 one-consumed-call audit while continuation is blocked; no new research."""
import importlib.util
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('K151_analysis_saved_only',OUT/'analyze.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def main():
    target=OUT/'old_diagnostic.json'
    a.k.require(not target.exists(),'Never overwrite saved old diagnostic')
    ledger,declaration=a.read(a.ROOT/'ledger.json'),a.read(a.ROOT/'declaration.json')
    a.k.require(ledger['state']=='BLOCKED' and ledger['consumed']==1,'Only the blocked old-only boundary')
    a.k.require(len(ledger['calls'])==1 and ledger['calls'][0]['id']=='old_linked4','Unexpected call history')
    before=a.h.raw_hashes(a.ROOT)
    source=a.h.source_audit(a.ROOT,declaration)
    a.k.require(source['all_match'] and source['count']==174,'Frozen source mismatch')
    row=ledger['calls'][0]
    report,native,phases,costs,schedules=a.k.audit_job('old_linked4',row,declaration)
    result=a.read(a.ROOT/'old_linked4/result.json')
    detail,candidates=a.native_details(result,'old_linked4',a.read(a.ROOT/'input_instance.json'),native)
    matrices=a.model_details(result,'old_linked4')
    after=a.h.raw_hashes(a.ROOT,before)
    a.k.require(before==after,'Raw artifacts changed during saved-record analysis')
    facts={'stage':'K151-old-only','new_research_calls':0,'new_native_calls':0,'new_thermal_evaluations':0,
        'new_candidate_decodes':0,'scope':'terminal old stored records only; no pair comparison; no decision to resume',
        'ledger_state_raw':ledger['state'],'consumed_calls':ledger['consumed'],
        'wrapper_status_raw':row.get('execution'),'wrapper_hard_errors_raw':row.get('context',{}).get('hard_errors'),
        'old':report,'native_details':detail,'candidates':candidates,'matrix_records':matrices,
        'phases':phases,'costs':costs,'schedules':schedules,'source_count':source['count'],
        'source_match':source['all_match'],'raw_hashes_before':before,'raw_hashes_after':after,
        'raw_artifacts_unchanged':True,'source_sha256':a.sha(__file__),
        'declaration_sha256':a.sha(a.ROOT/'declaration.json')}
    a.save(target,facts)
    for name,rows in (('old_native',native),('old_phase_timing',phases),('old_exclusive_costs',costs),
        ('old_matrices',matrices),('old_candidates',candidates)):
        a.h.write_csv(OUT/(name+'.csv'),rows)
    print(json.dumps({'old_complete_SAFE_receipt_verified':report['final_SAFE_receipt_verified'],
        'old_U_J':report['final_U_J'],'raw_wrapper_status':report['execution_status'],
        'native_records':len(native),'raw_unchanged':True},ensure_ascii=False))


if __name__=='__main__':
    main()
