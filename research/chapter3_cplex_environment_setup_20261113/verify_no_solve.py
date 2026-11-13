"""Verify installed CPLEX binding and a four-column API roundtrip. Never solve.

This is an environment/interface check, not an R1 model, LP/MILP call, thermal
evaluation, MIP-start acceptance test or proof of unlimited solve capacity.
"""
from pathlib import Path
import argparse
import ctypes
import datetime
import hashlib
import importlib.metadata
import json
import os
import platform
import struct
import sys
import time


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def bits(xs):
    return b''.join(struct.pack('<d', float(x)) for x in xs)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    started=time.perf_counter()
    import numpy as np
    from scipy import sparse
    import psutil
    import cplex

    studio=Path('F:/CPLEX/CPLEX_Studio222')
    dll=Path(cplex.__file__).parent/'_internal/cplex2220.dll'
    source=studio/'cplex/bin/x64_win64/cplex2220.dll'
    checks={}
    checks['cplex_package_version']=importlib.metadata.version('cplex')=='22.2.0.0'
    checks['docplex_package_version']=importlib.metadata.version('docplex')=='2.32.264'
    checks['runtime_dll_matches_academic_studio']=sha(dll)==sha(source)
    # Prevent accidental algorithm entry if this check is edited later.
    forbidden=[]
    def reject(*a,**kw):
        forbidden.append('forbidden_algorithm_entry')
        raise RuntimeError('No solve/populate/feasopt/tune/conflict calls authorized')
    cplex.Cplex.solve=reject
    cplex.Cplex.populate_solution_pool=reject

    # Synthetic, four columns only. No original R1 data is read.
    c=np.array([0.,.5,.5,0.],dtype=np.float64)
    lb=[0.,-5.,-cplex.infinity,0.]
    ub=[1.,55.,cplex.infinity,1.]
    x0=np.array([1.,.25,.25,0.],dtype=np.float64)
    A=sparse.csr_matrix(np.array([[1.,1.5,0.,0.],
                                 [0.,1.249904865300502e-8,-1.249904865300502e-8,0.],
                                 [0.,1.,-1.,0.]],dtype=np.float64))
    rhs=[1.375,1.3973128858024693e-63,0.]
    sense='LLE';itypes='ICCI';names=['column_0','column_1','column_2','column_3']
    # Explicit MATLAB intcon -> Python conversion; no minimum-index inference.
    matlab_intcon=np.array([1,4]);python_intcon=matlab_intcon-1
    checks['explicit_one_to_zero_based_indices']=python_intcon.tolist()==[0,3]
    model=None
    closed=False
    try:
        model=cplex.Cplex()
        model.set_log_stream(None);model.set_results_stream(None)
        model.set_warning_stream(None);model.set_error_stream(None)
        model.feasopt=reject
        model.conflict.refine=reject
        model.parameters.tune_problem=reject
        model.objective.set_sense(model.objective.sense.minimize)
        model.objective.set_offset(0.)
        model.variables.add(obj=c.tolist(),lb=lb,ub=ub,types=itypes,names=names)
        rows=[cplex.SparsePair(ind=A.indices[A.indptr[i]:A.indptr[i+1]].tolist(),
                             val=A.data[A.indptr[i]:A.indptr[i+1]].tolist()) for i in range(3)]
        model.linear_constraints.add(lin_expr=rows,senses=sense,rhs=rhs,names=['le_0','le_1','eq_0'])
        model.MIP_starts.add(cplex.SparsePair(ind=list(range(4)),val=x0.tolist()),
                            model.MIP_starts.effort_level.check_feasibility,'full_four_column_start')
        checks['native_engine_version']=model.get_version()=='22.2.0.0'
        checks['variable_and_row_counts']=model.variables.get_num()==4 and model.linear_constraints.get_num()==3
        checks['column_order']=model.variables.get_names()==names
        checks['objective_binary64']=bits(model.objective.get_linear())==bits(c)
        checks['objective_sense_and_constant']=model.objective.get_sense()==model.objective.sense.minimize and bits([model.objective.get_offset()])==bits([0.])
        checks['bounds_binary64_including_native_infinity_sentinel']=bits(model.variables.get_lower_bounds())==bits(lb) and bits(model.variables.get_upper_bounds())==bits(ub)
        checks['integer_domains']=model.variables.get_types()==list(itypes)
        checks['row_senses']=model.linear_constraints.get_senses()==list(sense)
        checks['rhs_binary64_including_1e_minus63']=bits(model.linear_constraints.get_rhs())==bits(rhs)
        back=model.linear_constraints.get_rows()
        checks['matrix_indices_and_all_coefficients_binary64']=all(
            list(got.ind)==list(want.ind) and bits(got.val)==bits(want.val) for got,want in zip(back,rows)) and len(back)==len(rows)
        checks['nnz_count']=sum(len(r.val) for r in back)==A.nnz
        start,effort=model.MIP_starts.get_starts(0)
        checks['complete_start_stored_binary64']=list(start.ind)==list(range(4)) and bits(start.val)==bits(x0) and model.MIP_starts.get_num()==1
        checks['start_check_effort_stored']=effort==model.MIP_starts.effort_level.check_feasibility
        psutil_paths=sorted(set(m.path for m in psutil.Process().memory_maps() if Path(m.path).name.lower()=='cplex2220.dll'))
        # psutil 5.9.0 omits the F: drive for this module on this host. Query
        # the Windows loader directly; never infer a drive from the expected path.
        kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel32.GetModuleHandleW.argtypes=[ctypes.c_wchar_p]
        kernel32.GetModuleHandleW.restype=ctypes.c_void_p
        kernel32.GetModuleFileNameW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint32]
        kernel32.GetModuleFileNameW.restype=ctypes.c_uint32
        handle=kernel32.GetModuleHandleW('cplex2220.dll')
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        buffer=ctypes.create_unicode_buffer(32768)
        size=kernel32.GetModuleFileNameW(handle,buffer,len(buffer))
        if size==0 or size>=len(buffer):raise RuntimeError('Incomplete Windows module path')
        loaded=[buffer.value]
        checks['actual_loaded_dll_is_bound_python_runtime']=len(loaded)==1 and os.path.normcase(os.path.realpath(loaded[0]))==os.path.normcase(os.path.realpath(dll))
        checks['no_algorithm_entry']=not forbidden
        engine_version=model.get_version()
    finally:
        if model is not None:
            model.end();closed=True
    checks['native_handle_closed']=closed
    record=dict(date=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        purpose='USER_AUTHORIZED_ENVIRONMENT_SETUP_AND_NO_SOLVE_MICRO_INTERFACE_CHECK',
        python=dict(executable=sys.executable,version=sys.version,platform=platform.platform()),
        packages={n:importlib.metadata.version(n) for n in ['cplex','docplex','numpy','scipy','pip','setuptools']},
        cplex_module=str(Path(cplex.__file__).resolve()),native_engine_version=engine_version,
        runtime=dict(studio_dll=str(source),python_dll=str(dll),loaded_dll_paths=loaded,
            loaded_path_method='Windows GetModuleHandleW/GetModuleFileNameW',psutil_paths_untrusted_drive=psutil_paths,
            studio_sha256=sha(source),python_sha256=sha(dll),
            pre_upgrade_community_dll_sha256='8d742ace170d1f75f22c1d746b494c647d4148b43c8217446e11f9e89f7c6538',
            official_configuration='docplex config --upgrade F:/CPLEX/CPLEX_Studio222'),
        entitlement=dict(source='User explicitly confirmed IBM academic entitlement in this conversation',
            installed_product_tag='IBM_ILOG_CPLEX_Optimization_Studio_Developer_Edition-22.2.0',
            credential_contents_read=False,license_files_modified=False,
            unrestricted_runtime_binding_verified=checks['runtime_dll_matches_academic_studio'],
            full_R1_capacity_tested=False,account_eligibility_independently_queried=False),
        checks=checks,passed=all(checks.values()),check_count=len(checks),
        native_mip_start_acceptance='NOT_TESTED_NO_OPTIMIZATION; attribute roundtrip is not acceptance',
        numerical_solve_stability='UNKNOWN_NOT_TESTED',R1_adapter_ready=False,
        calls=dict(native_empty_environment_and_micro_model=1,optimize=0,LP=0,MILP=0,MATLAB=0,
                   full_R1_build=0,full_R1_native_matrix_load=0,thermal_evaluation=0),
        elapsed_s=time.perf_counter()-started)
    with args.output.open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(passed=record['passed'],checks=checks,version=engine_version,loaded_dll_paths=loaded,elapsed_s=record['elapsed_s']),ensure_ascii=True))
    if not record['passed']:raise SystemExit(1)


if __name__=='__main__':main()
