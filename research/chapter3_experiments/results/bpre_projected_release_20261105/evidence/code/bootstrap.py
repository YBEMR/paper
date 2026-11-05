from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
REPO = WORK/'task_a_rebuild_20261104T114840Z/paper'
SOURCE = REPO/'research/chapter3_experiments'
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(ROOT))
