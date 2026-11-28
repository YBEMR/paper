"""Use the verified V1 lossless archive format and restoration utility."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/"ch3_integrated_quality_v1"))
import evidence
evidence.ROOT = ROOT

if __name__ == "__main__":
    if len(sys.argv) == 2:
        evidence.pack(sys.argv[1])
    else:
        evidence.restore(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
