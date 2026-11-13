"""Read package metadata in two known Python installations. No solver imports."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
records=[]
for exe in ('F:/Anaconda3/python.exe','F:/Python39/python.exe'):
    p=subprocess.run([exe,str(HERE/'environment_probe.py')],capture_output=True,text=True,check=True,timeout=60)
    records.append(json.loads(p.stdout))
root=Path('F:/Anaconda3/Lib/site-packages/scipy/optimize')
wrapper=root/'_highs/_highs_wrapper.cp312-win_amd64.pyd'
milp=root/'_milp.py'
matlab=Path('F:/Matlab2023/Program_Files/MATLAB_R2023b')
matched=[]
for directory,_,files in os.walk(matlab):
    for name in files:
        if any(s in name.lower() for s in ('gurobi','cplex','highs')):
            matched.append(str(Path(directory,name).relative_to(matlab)))
pathdef=matlab/'toolbox/local/pathdef.m'
path_hits=[line.strip() for line in pathdef.read_text(encoding='utf-8',errors='replace').splitlines()
           if any(s in line.lower() for s in ('gurobi','cplex','highs'))]
result=dict(interpreters=records,embedded_highs=dict(distribution='SciPy 1.13.1',
    engine_version='UNKNOWN_NOT_EXPOSED_BY_READONLY_METADATA',wrapper_present=wrapper.is_file(),
    wrapper_sha256=hashlib.sha256(wrapper.read_bytes()).hexdigest(),
    public_milp_source_sha256=hashlib.sha256(milp.read_bytes()).hexdigest(),
    full_x0_public_parameter=False,public_callback_parameter=False,engine_called=False),
    matlab_R2023b=dict(version='23.2',source='Windows installed-software registry',
        filename_keyword_hits=matched,
        solver_interface_candidates=[s for s in matched if 'highspeed' not in s.lower()],
        excluded_unrelated_highspeed_files=[s for s in matched if 'highspeed' in s.lower()],
        default_pathdef_solver_entries_found=path_hits,
        runtime_path_unqueried=True,session_started=False),
    scope='Known interpreters and installed R2023b filenames/default path only; custom MATLAB user path, arbitrary portable installs and inaccessible H drive remain unknown',
    matlab_file_scan_note='Read-only file names and pathdef.m entries; no MATLAB runtime query',
    path_executables={s:shutil.which(s) for s in ('gurobi_cl','cplex','highs','python','python3','py')},
    solver_models_created=0,license_sessions_started=0,optimization_calls=0)
with Path(sys.argv[1]).open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(json.dumps(dict(versions=[r['python'] for r in records],solver_importable=[r['importable'] for r in records]),ensure_ascii=True))
