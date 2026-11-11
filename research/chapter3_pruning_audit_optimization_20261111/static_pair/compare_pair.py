"""Read the one-shot three-arm exports. No model building, solver, or thermal calls."""
import csv
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
PRIOR=REPO/'research/chapter3_certified_state_pruning_20261111/full_static'
ARMS=['old_on','optimized_on','off']
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def load(folder,with_result=True):
    with np.load(folder/'exported_model.npz',allow_pickle=False) as saved:
        arrays={key:saved[key] for key in saved.files}
    return dict(folder=folder,arrays=arrays,names=read(folder/'variable_names.json'),
                result=read(folder/'result.json') if with_result else None)


def same(left,right):return left.dtype==right.dtype and left.shape==right.shape and left.tobytes()==right.tobytes()


def compare_arrays(left,right):
    assert set(left)==set(right)
    checks={key:same(left[key],right[key]) for key in left};assert all(checks.values()),checks
    return checks


def gate_proofs(preprocessing):
    reports=preprocessing['joint_state_pruning']['scenes'];proofs={};paths=[]
    for scene,meta in reports.items():
        for proof in meta['certificate_catalogue'].values():
            if proof['rule']=='exported_dependency_path':
                assert F(proof['strict_margin'])>0
                assert proof['exceeds_path_row_tolerance'] is True
                paths.append(proof['strict_margin'])
        for interval in meta['interval_reports']:
            audit=interval['gate_off_audit']
            assert audit['rows_checked']==10*audit['states_checked']
            for proof in audit.get('states',[]):
                identity=(scene,interval['interval'],tuple(proof['state']))
                assert proof['checked_rows']==10 and proof['gate_fixed_value']==0 and proof['exact_binary64_box'] is True
                assert F(proof['maximum_residual'])<=0 and F(proof['minimum_slack'])>=0
                # Extra cache accounting is intentionally separate from the unchanged mathematical certificate.
                proofs[identity]={key:proof[key] for key in ['checked_rows','gate_fixed_value','maximum_residual','minimum_slack','exact_binary64_box']}
    return proofs,paths


def main():
    started=datetime.now(timezone.utc).isoformat();t=time.monotonic()
    assert (HERE/'batch_completed.json').exists()
    current={arm:load(HERE/'execution'/arm) for arm in ARMS}
    assert all(data['result']['success'] and not data['result']['forbidden_attempts'] for data in current.values())
    old,new,off=[current[arm] for arm in ARMS]
    matrices_equal=compare_arrays(old['arrays'],new['arrays'])
    assert old['names']==new['names']
    assert sha(old['folder']/'row_metadata.jsonl')==old['result']['row_metadata_sha256']
    assert sha(new['folder']/'row_metadata.jsonl')==new['result']['row_metadata_sha256']
    assert old['result']['row_metadata_sha256']==new['result']['row_metadata_sha256']
    historical_on=load(PRIOR/'execution/on',False);historical_off=load(PRIOR/'execution/off',False)
    old_archive_checks=compare_arrays(old['arrays'],historical_on['arrays'])
    off_archive_checks=compare_arrays(off['arrays'],historical_off['arrays'])
    assert old['names']==historical_on['names'] and off['names']==historical_off['names']
    assert all(read(data['folder']/'options.json')==read(old['folder']/'options.json') for data in current.values())
    assert all(data['result']['events']==old['result']['events'] for data in current.values())
    deleted=set(off['names'])-set(new['names']);predicted=set(read(PRIOR/'comparison.json')['removed_names'])
    assert deleted==predicted and len(deleted)==2938
    for data in [old,new]:
        result=data['result'];assert (result['variables'],result['rows'],result['nonzeros'])==(16919,94958,990904)
        assert sum(result['joint_state_blocks'].values())==6860
    old_preprocessing=read(old['folder']/'preprocessing.json')
    new_preprocessing=read(new['folder']/'preprocessing.json')
    old_proofs,old_paths=gate_proofs(old_preprocessing)
    new_proofs,new_paths=gate_proofs(new_preprocessing)
    assert old_proofs==new_proofs and len(old_proofs)==2938
    for data in current.values():
        certificates=read(data['folder']/'energy_certificate_checks.json')
        assert len(certificates)==424 and all(item['passed'] for item in certificates)
        assert all(F(value)<=0 for item in certificates for value in item['exact_residual_difference_maxima'])
    # The mathematical cut/check data must match too, not only the float matrix.
    assert read(old['folder']/'energy_bound_certificates.json')==read(new['folder']/'energy_bound_certificates.json')
    assert read(old['folder']/'energy_certificate_checks.json')==read(new['folder']/'energy_certificate_checks.json')
    rows=[]
    for arm,data in current.items():
        r=data['result'];ret=read(HERE/f'{arm}.command_receipt.json')
        components=r['construction'].get('construction_components',{})
        get=lambda key:components.get(key,{}).get('exclusive_s')
        stats=(read(data['folder']/'preprocessing.json').get('joint_state_pruning',{})
               .get('audit_certificate_cache',{}).get('stats',{}))
        rows.append(dict(arm=arm,variables=r['variables'],rows=r['rows'],nonzeros=r['nonzeros'],
            states=sum(r['joint_state_blocks'].values()),source_import_verify_s=r['import_and_verification_s'],
            support_s=get('joint_state_support_pruning'),gate_off_audit_s=get('joint_state_gate_off_audit'),
            conditional_row_assembly_s=get('thermal_conditional_rows'),build_s=r['build_s'],export_s=r['export_s'],
            build_plus_export_s=r['build_plus_export_s'],energy_certificate_check_s=r['energy_certificate_check_s'],
            archive_s=r['archive_s'],worker_s=r['worker_elapsed_s'],command_wall_s=ret['wall_s'],
            peak_rss_after_export_bytes=r['peak_memory']['after_export'].get('bytes'),
            peak_rss_after_archive_bytes=r['peak_memory']['after_archive'].get('bytes'),
            certification_environment_prepare_s=stats.get('preparation_s'),
            certificate_key_s=stats.get('key_s'),probe_prepare_s=stats.get('probe_prepare_s'),
            certificate_export_s=stats.get('export_s'),strict_verify_s=stats.get('verify_s'),
            certificate_cache_hit_s=stats.get('cache_hit_s'),cache_hits=stats.get('hits'),cache_misses=stats.get('misses'),
            cache_clears=stats.get('clears'),identity_invalidations=stats.get('identity_invalidations'),
            strict_rows_evaluated=stats.get('strict_rows_evaluated'),represented_certified_rows=stats.get('rows_represented')))
    cache_report=new_preprocessing['joint_state_pruning'].get('audit_certificate_cache')
    cache_statistics=None if cache_report is None else cache_report.get('stats')
    summary=dict(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),wall_s=time.monotonic()-t,
        on_arrays_byte_identical=matrices_equal,old_on_matches_historical_archive=old_archive_checks,
        off_matches_historical_archive=off_archive_checks,on_names_equal=True,on_all_row_metadata_sha256=old['result']['row_metadata_sha256'],
        same_options_events_objective_bounds_integer_indices=True,deleted_state_name_set_equals_frozen_prediction=True,
        deleted_states=2938,gate_proof_results_exactly_equal=True,represented_gate_rows=29380,
        energy_cuts_exact_and_unchanged=True,rows=rows,optimized_cache_statistics=cache_statistics,
        cache_timing_availability='missing instrumentation' if cache_statistics is None else 'raw implementation stats retained; nested in gate-off audit/build',
        timing_semantics='All reported costs are this run; stage components are nested in build. Process wall additionally includes archive/exit; peak RSS is process lifetime peak, not incremental build peak.',
        precision_scope='Exact binary64 arrays and exact-rational certificate results with integer original y, not LP or near-integer acceptance-tube equivalence.',
        new_model_builds=0,new_solver_calls=0,new_thermal_calls=0)
    with (HERE/'comparison.json').open('x') as stream:json.dump(summary,stream,ensure_ascii=False,indent=2,allow_nan=False)
    with (HERE/'timing_comparison.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
