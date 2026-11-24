"""Launch once, wall time includes imports, compilation, scheduling, integration, I/O."""
from pathlib import Path
import json,subprocess,sys,os,platform,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
cfg=json.loads((HERE/"config.json").read_bytes())
out=HERE/"raw";out.mkdir(exist_ok=False)
start=time.perf_counter()
env=os.environ.copy();env["NESTED_START"]=str(start)
identity=dict(execution_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
    python=sys.version,platform=platform.platform(),wall_budget_s=cfg["batch_wall_budget_s"],
    start_local=time.strftime("%Y-%m-%d %H:%M:%S"),command="python -B research/d017_nested_paths/launch.py")
(HERE/"environment.json").write_text(json.dumps(identity,indent=2)+"\n",encoding="utf-8")
with (out/"console.txt").open("x",encoding="utf-8") as f:
    p=subprocess.Popen([sys.executable,"-B",str(HERE/"worker.py")],cwd=ROOT,env=env,stdout=f,stderr=f)
    try:code=p.wait(timeout=cfg["batch_wall_budget_s"]-(time.perf_counter()-start))
    except subprocess.TimeoutExpired:p.kill();p.wait();code="TIMEOUT"
result=dict(exit_code=code,wall_seconds=time.perf_counter()-start,pid=p.pid)
(out/"receipt.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(result)
sys.exit(0 if code==0 else 1)
