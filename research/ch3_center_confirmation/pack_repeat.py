"""Verify every delivered online certificate and losslessly store its physical replay."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_mapping_first_nested"))
import pack_lane

if __name__ == "__main__":
    pack_lane.ROOT=Path(sys.argv[1])
    pack_lane.main(sys.argv[2])
