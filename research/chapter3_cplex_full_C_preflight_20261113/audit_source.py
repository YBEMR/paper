"""Post-seal read-only audit of D282 archived arrays; no CPLEX import or model."""
from pathlib import Path
import hashlib,json,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
PKG=ROOT/'work/cplex_C_preflight_v1';RUN=ROOT/'work/cplex_C_load_execution_v1'
sys.path.insert(0,str(PKG))
from common import read,save,sha,verify_files
from transport_contract import MatrixPacket
start=time.perf_counter();plan=read(PKG/'plan.json');controller=read(RUN/'controller_receipt.json')
checks={}
checks['plan_identity']=sha(PKG/'plan.json')==read(PKG/'plan.identity.json')['sha256']==controller['plan_sha256']
verify_files(PKG,plan['code_hashes']);verify_files(ROOT,plan['input_hashes'])
checks['frozen_sources_and_inputs_unchanged']=True
checks['native_runtime_files_unchanged']=all(sha(p)==h for p,h in plan['runtime_hashes'].items())
checks['sealed_evidence_unchanged']=all(sha(RUN/p)==h for p,h in controller['scientific_evidence_hashes'].items())
worker=read(RUN/'worker_receipt.json');comparison=read(RUN/'comparison.json')
checks['one_native_object']=worker['native_objects_created']==1
checks['no_algorithm_attempts']=worker['algorithm_attempts']==[]
checks['all_readback_invariants']=all(comparison['invariants'].values())
checks['zero_field_differences']=all(r['mismatch_count']==0 for r in comparison['fields'])
checks['start_all23780']=next(r['compared'] for r in comparison['fields'] if r['field']=='x0')==23780
checks['all_1004625_coefficients']=sum(r['compared'] for r in comparison['fields'] if r['field'] in ('A.data','Aeq.data'))==1004625
checks['cleanup']=worker['native_handle_closed'] and controller['owned']['cleanup_ok'] and controller['owned']['job_accounting']['active_processes']==0
checks['within_worker_and_total_window']=worker['sealed_elapsed_s']<280 and controller['method_elapsed_s']<300
checks['job_limit']=controller['owned']['job']['job_memory']==2*2**30 and controller['owned']['job']['active_limit']==1
with np.load(RUN/'native_readback.npz',allow_pickle=False) as d:
    n=len(d['c'])
    mats={name:(tuple(d[name+'_shape'].tolist()),d[name+'_row'],d[name+'_col'],d[name+'_data']) for name in ('A','Aeq')}
    p=MatrixPacket(n,mats['A'],mats['Aeq'],**{k:d[k] for k in ('c','b','beq','lb','ub','intcon','x0')},column_ids=tuple(range(n)))
    checks['archived_full_arrays_match_frozen']=p.hashes()==plan['matrices']['complement']['canonical_arrays_sha256']
    sizes=dict(variables=p.n,integers=len(p.intcon),A_rows=p.A[0][0],Aeq_rows=p.Aeq[0][0],nnz=len(p.A[3])+len(p.Aeq[3]))
oldplan=read(ROOT/'work/root_tail_observer_v1/plan.json');historic={}
for name,base in [('workspace_files',ROOT),('vendor_files',ROOT),('package_files',ROOT/'work/root_tail_observer_v1')]:
    verify_files(base,oldplan[name]);historic[name]=len(oldplan[name])
checks['older_D279_D280_inputs_unchanged']=True
samples=[json.loads(s) for s in (RUN/'resources.jsonl').read_text().splitlines()]
cost=dict(method_s=controller['method_elapsed_s'],phases=worker['phases'],
    entry_to_first_worker_phase_s=worker['phases'][0]['end_elapsed_s']-worker['phases'][0]['duration_s'],
    native_handle_closed_elapsed_s=worker['sealed_elapsed_s'],
    owned_job_cleanup_elapsed_s=controller['owned']['elapsed_s'],
    archive_hash_finalization_s=controller['method_elapsed_s']-controller['owned']['elapsed_s'],
    peak_job_commit_MiB=controller['owned']['job']['peak_job_memory']/2**20,
    peak_sampled_worker_private_MiB=controller['owned']['peak_sampled_private_bytes']/2**20,
    peak_sampled_worker_rss_MiB=controller['owned']['peak_sampled_rss_bytes']/2**20,
    peak_sampled_parent_private_MiB=max(x['parent_private'] for x in samples)/2**20,
    entry_available_GiB=controller['owned']['available_at_entry']/2**30,
    CPU=controller['owned']['job_accounting'],resource_samples=len(samples),
    readback_archive_bytes=(RUN/'native_readback.npz').stat().st_size,
    attribution_note='Wall stages partition observed method time; CPU is separate and must not be added to wall time. Post-seal audit/publication is administrative and does not supply late native evidence.')
record=dict(checks=checks,passed=all(checks.values()),matrix_sizes=sizes,cost=cost,older_frozen_file_counts=historic,
    unexpected_counter=dict(job_total_processes=controller['owned']['job_accounting']['total_processes'],
        python_only_control_total_processes=read(ROOT/'work/cplex_C_controls_v1/job_normal/result.json')['job_accounting']['total_processes'],
        interpretation='Raw TotalProcesses=2 also occurs in the no-CPLEX ordinary control; exact host accounting cause unknown. Not evidence of a second CPLEX object or solve. Active limit1 and final active0 verified.'),
    post_seal_readonly_audit_s=time.perf_counter()-start,additional_native_calls=0)
save(ROOT/'work/cplex_C_preflight_audit.json',record)
print(json.dumps(dict(passed=record['passed'],checks=len(checks),cost=cost),ensure_ascii=True))
