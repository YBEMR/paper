"""Cold cell with the frozen analytic control or a single initial quota."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREV = ROOT.parent / "ch3_analytic_quota"
sys.path.insert(0, str(PREV))
from method import analytic_expand, capture, f, m, paired


def main(code, arm, budget, dest):
    assert arm in ("anchors", "center") and budget in (60, 600)
    f.ORIGIN = m.CLOCK = float(os.environ["CELL_START"])
    f.log(dest / "start.jsonl", "begin", core=list(os.sched_getaffinity(0)))
    m.RUN = m.u2.stack()
    api = m.RUN[0].e
    if arm == "anchors":
        expand = analytic_expand(api.expand)
    else:
        from simplified import expand
    api.expand = capture(expand, dest)
    obj = next(o for o in m.u2.CASES if m.label(o) == code)
    paired.baseline(obj, dest, budget)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4]))
