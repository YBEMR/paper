"""Rotate six pinned, independent cold cells per flow and retain all on-time evidence."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_center_confirmation"))
import lane

def main(code,budget):
    assert code in lane.CASES and budget in (60,600)
    lane.ROOT = ROOT
    core = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    for rep in (1,2,3):
        work = ROOT/"lanes"/str(budget)/code/f"r{rep}"
        arms = ("A","B") if (lane.CASES.index(code)+rep-1)%2==0 else ("B","A")
        for pos,arm in enumerate(arms,1):
            lane.run_cell(code,arm,budget,rep,pos,work/"paired_raw"/code/f"{arm}-{budget}",core)
        subprocess.run([sys.executable,"-Bu",str(ROOT.parent/"ch3_center_confirmation/pack_repeat.py"),str(work),code],check=True)
        shutil.rmtree(work/"paired_raw")

if __name__=="__main__":
    main(sys.argv[1],int(sys.argv[2]))
