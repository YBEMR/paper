"""Single planner OR single H audit worker. Real mode closed throughout B0."""
import argparse,json,os,sys,time,platform
from pathlib import Path
# -I isolated interpreter: only this copied source bundle is on the project path.
CORE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CORE)); sys.dont_write_bytecode=True
from h02_pair_preflight.common import require,sha,encoded
from h02_pair_preflight.paired_heuristic_entry import validate_packet
from h02_pair_b0.io_contract import load_json,atomic_json,policy_files,require_research_authorization,digest_file,consume_worker_launch
from h02_pair_b0.budget import RootClock,RootBudgetExpired
from h02_pair_b0.boundary import install_worker_boundary
EXECUTION_STATE={'real_backend_entered':False,'kind':None}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--job',required=True); parser.add_argument('--job-sha',required=True); parser.add_argument('--bundle',required=True); parser.add_argument('--output',required=True); parser.add_argument('--mode',choices=('real','mock'),required=True)
    args=parser.parse_args(); outpath=Path(args.output).resolve(); bundle=Path(args.bundle).resolve()
    # Only public job is read. In real mode every step remains on parent root time.
    job=load_json(args.job); require(sha(job)==args.job_sha,'JOB_HASH_MISMATCH')
    policy,gate=policy_files()
    if args.mode=='real': require_research_authorization(gate,policy)
    require(job['kind'] in ('planner','audit'),'WORKER_KIND')
    require(job['limit_s']==(120 if job['kind']=='planner' else 60),'WORKER_LIMIT_DRIFT')
    root=RootClock(job['limit_s'],origin=job['root_origin'],clock=time.monotonic)
    root.check()
    if args.mode=='real': consume_worker_launch(job,gate,policy,outpath)
    # Code bundle is source-only and includes no sealed H file or prior results.
    manifest=load_json(bundle/'runtime_manifest.json')
    for rel,h in manifest['source_files_sha256'].items(): require(digest_file(bundle/rel)==h,'BUNDLE_SOURCE_HASH')
    for name,h in manifest['policy_files_sha256'].items(): require(digest_file(CORE/'h02_pair_b0'/name)==h,'BUNDLE_POLICY_HASH')
    # Original runner archives platform.platform(); prime its stdlib cache before
    # the file/native boundary, while still charging the SAME parent deadline.
    host_platform=platform.platform(); root.check()
    paths=[Path(sys.base_prefix)/'Lib',Path(sys.base_prefix)/'DLLs',Path(sys.base_prefix)/'python313.zip']
    events=install_worker_boundary(bundle,outpath,stdlib_roots=paths)
    if args.mode=='mock':
        require(job['kind']=='planner','MOCK_WORKER_IS_PUBLIC_PLANNER_ONLY')
        require(set(job)=={'kind','root_origin','limit_s','packet','probe_denied_paths'},'MOCK_JOB_FIELDS')
        validate_packet(job['packet'])
        denied=[]
        for path in job['probe_denied_paths']:
            try: Path(path).read_bytes()
            except PermissionError: denied.append(path)
            else: raise ValueError('ISOLATION_PROBE_WAS_NOT_DENIED')
        output={'evidence_kind':'MOCK_ONLY','worker_kind':'planner','view':job['packet']['view'],'input_sha256':job['packet']['plan_sha256'],'denied_paths':denied,'boundary_events':events,'root':root.summary(),'research_calls':0,'new_safe':0,'real_backend_entered':False,'platform_archive_cache_compatible':platform.platform()==host_platform}
    else:
        from h02_pair_b0.backends import resolve_real_bindings,planner_chain,audit_chain
        bindings=resolve_real_bindings(gate,policy)
        EXECUTION_STATE.update(real_backend_entered=True,kind=job['kind'])
        atomic_json(outpath/'real_backend_entry.json',{'kind':job['kind'],'at_elapsed_s':root.elapsed,'root_limit_s':root.limit_s,'scope':'Backend ready; invocation may remain unknown on abrupt process stop. Do not falsely report zero.'})
        if job['kind']=='planner':
            require(set(job)=={'kind','root_origin','limit_s','packet','ordinal','launch_claim_sha256'},'PLANNER_JOB_FIELDS')
            output=planner_chain(bindings,job['packet'],root,outpath/'method')
        else:
            require(set(job)=={'kind','root_origin','limit_s','truth','token','audit_claim_sha256','ordinal','launch_claim_sha256'},'AUDIT_JOB_FIELDS')
            output=audit_chain(bindings,job['truth'],job['token'],root,on_receipt=lambda receipt:atomic_json(outpath/'formed_audit_receipt.json',receipt))
    # Post-cutoff serialization cannot add, repair or re-evaluate a candidate.
    atomic_json(outpath/'worker_return.json',{'job_sha256':args.job_sha,'kind':job['kind'],'payload':output,'returned_at_elapsed_s':root.elapsed,'environment':{'python':sys.version,'platform':host_platform,'sys_platform':sys.platform},'boundary_kind':'trusted Python application boundary, NOT OS sandbox'})
    return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as error:
        sys.stderr.buffer.write((json.dumps({'state':'INPUT_OR_INTERFACE_ERROR','reason':type(error).__name__+':'+str(error),'real_backend_entered':EXECUTION_STATE['real_backend_entered'],'worker_kind':EXECUTION_STATE['kind'],'research_calls':None if EXECUTION_STATE['real_backend_entered'] else 0,'new_safe':None if EXECUTION_STATE['real_backend_entered'] else 0},ensure_ascii=False)+'\n').encode('utf-8')); raise SystemExit(3)
