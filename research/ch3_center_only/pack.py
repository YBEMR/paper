"""Reuse the verified lossless archive layout."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/"ch3_mapping_first_nested"))
import pack_lane

if __name__ == "__main__":
    pack_lane.ROOT = ROOT
    pack_lane.main(sys.argv[1])
