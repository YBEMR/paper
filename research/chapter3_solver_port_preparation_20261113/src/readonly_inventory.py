"""Bounded file/registry inventory and saved matrix inspection; no solver import."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,sys,winreg
import numpy as np
from scipy.io import loadmat
parser=argparse.ArgumentParser()
parser.add_argument('--workspace',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();ROOT=args.workspace.resolve();OUT=args.output.resolve();OUT.mkdir(exist_ok=True,parents=True)
def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
roots=[Path(x) for x in ['C:/','D:/','E:/','F:/','H:/','C:/Program Files','C:/Program Files (x86)',
    'F:/Program Files','F:/Program Files (x86)','C:/ProgramData','C:/Users/86130/AppData/Local/Programs',
    'F:/Anaconda3/envs','C:/Users/86130/.conda/envs']]
matches=[];errors=[]
for root in roots:
    try:
        if root.exists():
            for p in root.iterdir():
                if p.is_dir() and re.search(r'gurobi|cplex|^ilog$|^ibm$|highs|python|anaconda',p.name,re.I):
                    matches.append(str(p))
    except OSError as e:errors.append(dict(root=str(root),error=type(e).__name__))
registry=[]
for hive in [winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER]:
    for name in [r'Software\Microsoft\Windows\CurrentVersion\Uninstall',r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall']:
        try:
            with winreg.OpenKey(hive,name) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    with winreg.OpenKey(key,winreg.EnumKey(key,i)) as sub:
                        def q(k):
                            try:return winreg.QueryValueEx(sub,k)[0]
                            except OSError:return None
                        display=q('DisplayName')
                        if display and re.search('gurobi|cplex|ilog|highs|python|matlab|anaconda',display,re.I):
                            registry.append(dict(name=display,version=q('DisplayVersion'),install_location=q('InstallLocation')))
        except OSError:pass
env_names=[k for k in os.environ if re.search('GUROBI|GRB_|CPLEX|ILOG|ILM_',k,re.I)]
# Location-only checks: do NOT read, copy, hash or print license contents/values.
license_paths=[Path('C:/gurobi/gurobi.lic'),Path('C:/Users/86130/gurobi.lic'),Path('C:/Users/86130/.gurobi/gurobi.lic')]
configured=os.environ.get('GRB_LICENSE_FILE')
if configured and '@' not in configured:license_paths.append(Path(configured))
license_presence=[dict(location='configured_path' if configured and str(p)==configured else str(p),
    exists=p.is_file(),contents_read=False) for p in license_paths]
python_paths=[Path('F:/Anaconda3/python.exe'),Path('F:/Python39/python.exe')]
environments=Path('C:/Users/86130/.conda/environments.txt')
if environments.exists():
    for line in environments.read_text(encoding='utf-8').splitlines():
        if line.strip():python_paths.append(Path(line.strip())/'python.exe')
for root in [Path('C:/Users/86130/AppData/Local/Programs/Python'),Path('F:/Anaconda3/envs')]:
    if root.exists():
        python_paths += [p/'python.exe' for p in root.iterdir() if p.is_dir()]
save('environment_inventory.json',dict(date='2026-11-13',search_roots=[str(p) for p in roots],matched_directories=matches,
    registry=registry,related_environment_variable_names=env_names,environment_values_not_exported=True,
    license_locations_checked=license_presence,license_entitlement='UNVERIFIED_NO_ELIGIBILITY_ASSUMED',
    python_executables=sorted(set(str(p) for p in python_paths if p.is_file())),errors=errors,
    scope='Common installed locations/PATH/registry/known Python environments only; not a proof about every arbitrary portable folder or WSL image',
    software_installed=0,license_changes=0,solver_environments_started=0,MATLAB_sessions=0))
folder=ROOT/'work/mechanism_trials_execution_v1/C_noheur';records={}
for name in ['original_zero_based.mat','matlab/request_000001.mat']:
    d=loadmat(folder/name,variable_names=['c','A','b','Aeq','beq','lb','ub','intcon','x0']);r={}
    for k,x in d.items():
        if k.startswith('_'):continue
        arr=x.data if k in ('A','Aeq') else x.reshape(-1)
        nz=np.abs(arr[np.isfinite(arr)&(arr!=0)])
        r[k]=dict(shape=x.shape,dtype=str(x.dtype),nnz=int(x.nnz if k in ('A','Aeq') else np.count_nonzero(arr)),
            min_abs_nonzero=float(nz.min()) if nz.size else None,max_abs_finite=float(nz.max()) if nz.size else None,
            nonzero_abs_below_1e13=int(np.sum(nz<1e-13)),nonzero_abs_below_1e12=int(np.sum(nz<1e-12)),
            nonzero_abs_below_1e9=int(np.sum(nz<1e-9)),positive_inf=int(np.sum(np.isposinf(arr))),
            negative_inf=int(np.sum(np.isneginf(arr))),nan=int(np.sum(np.isnan(arr))))
    records[name]=dict(sha256=sha(folder/name),arrays=r)
save('saved_matrix_inventory.json',dict(records=records,mode='Read frozen numeric arrays only; no reconstruction, solving or thermal evaluation'))
print(json.dumps(dict(python_executables=sorted(set(str(p) for p in python_paths if p.is_file())),
    solver_directories=[p for p in matches if re.search('gurobi|cplex|highs',p,re.I) or Path(p).name.lower() in ('ilog','ibm')],
    solver_environment_names=env_names,license_files_found=sum(x['exists'] for x in license_presence),
    matrix_ranges={n:{k:v for k,v in d['arrays'].items() if k in ('A','Aeq')} for n,d in records.items()}),ensure_ascii=True))
