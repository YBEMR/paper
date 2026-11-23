"""One missing control: existing idle rule, original Kim busy L/L/H/H."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'research/gpu_idle_dvfs'))
from model import prepare,certify,save,WINDOW,DEP
from scheduler import predictive_calendar,dispatch


def plan(ev,chains,requests,reference,order,setting,dwell):
    # The only policy adaptation: feed the already-H portion of Kim's timeline
    # into the SAME frozen idle calendar, rather than making every stage H.
    boundary=ev.scenes[2].start_ns
    high_rows=[r for r in reference if r.resource=='GPU' and r.start_ns>=boundary]
    calendar=predictive_calendar(high_rows,WINDOW,setting['latency_ns'],setting['energy_j'],dwell)
    rows,completion,calendar=dispatch(sys.modules['events'],requests,chains,order,WINDOW,calendar=calendar)
    assert rows==reference,'Idle control changed the frozen compute schedule'
    return rows,completion,calendar
