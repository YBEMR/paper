"""Only D282 native-object load/readback; no scientific optimizer path."""
import sys,time
# Wait before third-party imports or any native environment creation.
if __name__=='__main__' and sys.stdin.readline().strip()!='D282_GO':raise SystemExit('No protected launch')
import argparse,json,traceback,importlib.metadata,os
from pathlib import Path
from common import Deadline,read,save,sha,verify_files

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--t0',type=float,required=True);args=parser.parse_args()
    plan=read(args.plan);out=args.output;root=args.workspace;here=Path(__file__).resolve().parent
    deadline=Deadline(args.t0,plan['limits']['worker_deadline_s']);phases=[]
    last=time.perf_counter();model=None;attempts=[];created=0;closed=False;passed=False;error=None
    def progress(stage,**extra):
        deadline.check()
        with (out/'progress.jsonl').open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(dict(stage=stage,elapsed_s=time.perf_counter()-args.t0,**extra),allow_nan=False)+'\n')
    def phase(name):
        nonlocal last
        now=time.perf_counter();phases.append(dict(phase=name,duration_s=now-last,end_elapsed_s=now-args.t0));last=now
        progress(name)
    try:
        verify_files(here,plan['code_hashes']);verify_files(root,plan['input_hashes'])
        for path,h in plan['runtime_hashes'].items():
            if sha(path)!=h:raise ValueError('Runtime drift: '+path)
        phase('identity_reads')
        import numpy as np
        from scipy.io import loadmat
        from transport_contract import MatrixPacket
        import cplex
        from native_adapter import seal_algorithms,seal_instance,loaded_dll,load,readback,compare,archive_packet
        attempts,blocked,deny=seal_algorithms(cplex)
        phase('imports_and_algorithm_guards')
        packets={}
        for label in ('original','complement'):
            spec=plan['matrices'][label];d=loadmat(root/spec['path'],variable_names=['c','A','b','Aeq','beq','lb','ub','intcon','x0'])
            n=d['c'].size
            p=MatrixPacket.read(d,intcon_base=spec['intcon_base'],sense='min',objective_constant=0.,column_ids=range(n))
            if p.hashes()!=spec['canonical_arrays_sha256']:raise ValueError('Array identity drift: '+label)
            packets[label]=p;deadline.check()
        old=packets['original'];new=packets['complement']
        composition=dict(original_arrays_match_frozen=True,complement_arrays_match_frozen=True,
            unchanged_integer_indices=np.array_equal(old.intcon,new.intcon),
            original_prefix_c_bitwise=old.c.tobytes()==new.c[:old.n].tobytes(),
            original_prefix_x0_bitwise=old.x0.tobytes()==new.x0[:old.n].tobytes(),
            original_prefix_lb_bitwise=old.lb.tobytes()==new.lb[:old.n].tobytes(),
            original_prefix_ub_bitwise=old.ub.tobytes()==new.ub[:old.n].tobytes(),
            added_objective_zero=bool(np.all(new.c[old.n:]==0)))
        cert=read(root/plan['projection_certificate'])
        composition['saved_exact_projection_checks']=all(v is True for v in cert['checks'].values())
        if not all(composition.values()):raise ValueError('Original/complement provenance mismatch')
        save(out/'input_identity.json',dict(checks=composition,certificate_checks=cert['checks'],
            relation='Frozen exact projection certificate + exact original/transformed source hashes + native bitwise identity; no new projection proof or physical rebuild',
            canonical_hashes={k:v.hashes() for k,v in packets.items()}))
        phase('saved_arrays_load_and_verify')
        model=cplex.Cplex();created+=1;seal_instance(model,deny)
        with (out/'native.log').open('x',encoding='utf-8',newline='\n') as log:
            model.set_log_stream(log);model.set_results_stream(log);model.set_warning_stream(log);model.set_error_stream(log)
            dll=loaded_dll();wanted=plan['python_dll']
            if os.path.normcase(os.path.realpath(dll))!=os.path.normcase(os.path.realpath(wanted)):raise ValueError('Loaded DLL path drift')
            if model.get_version()!=plan['cplex_version'] or sha(dll)!=plan['runtime_hashes'][wanted]:raise ValueError('Native version/DLL drift')
            parameter_snapshot={str(p):v for p,v in model.parameters.get_all()}
            param_meta={}
            for path,value in plan['D283_proposed_parameters'].items():
                p=model.parameters
                for token in path.split('.'):p=getattr(p,token)
                lo,hi=p.min(),p.max()
                if value!='N(t)' and not lo<=value<=hi:raise ValueError('Proposed parameter outside supported range: '+path)
                param_meta[path]=dict(proposed=value,current=p.get(),default=p.default(),minimum=lo,maximum=hi)
            save(out/'runtime.json',dict(engine_version=model.get_version(),dll_path=dll,dll_sha256=sha(dll),
                cplex_package=importlib.metadata.version('cplex'),python=sys.version,
                installed_parameter_snapshot=parameter_snapshot,D283_parameter_validation=param_meta,
                algorithm_guards=blocked,guard_scope='Protocol guard, not an adversarial security boundary',
                user_entitlement='IBM academic, user-confirmed; bound Developer Edition runtime; no account query or capacity solve'))
            phase('native_environment_and_parameter_metadata')
            load(model,cplex,new,deadline.check,progress,plan['block_rows'])
            phase('native_model_load')
            q,invariants=readback(model,cplex,new,deadline.check,progress,plan['block_rows'])
            phase('native_complete_readback')
            result=compare(new,q,invariants);save(out/'comparison.json',result)
            archive_packet(out/'native_readback.npz',q)
            save(out/'native_readback.identity.json',dict(sha256=sha(out/'native_readback.npz'),bytes=(out/'native_readback.npz').stat().st_size))
            phase('comparison_and_lossless_archive')
            passed=result['passed'] and not attempts
            model.end();closed=True;model=None
        phase('native_release_and_log_close')
    except BaseException as e:
        error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc());passed=False
    finally:
        if model is not None:
            try:model.end();closed=True
            except BaseException as e:error=dict(type='CleanupFailure',message=str(e),preceding=error);passed=False
    if not closed or created!=1:passed=False
    save(out/'worker_receipt.json',dict(passed=passed,error=error,phases=phases,
        native_objects_created=created,native_handle_closed=closed,algorithm_attempts=attempts,
        calls=dict(optimization=0,independent_LP=0,full_R1_rebuild=0,thermal_evaluation=0),
        MIP_start='STORED_AND_READ_BACK_ONLY; native search acceptance untested',
        sealed_elapsed_s=time.perf_counter()-args.t0))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
