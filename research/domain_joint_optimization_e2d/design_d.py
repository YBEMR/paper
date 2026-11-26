"""Frozen E2-d policies and inherited asset locations."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
C2=ROOT.parent/"domain_joint_optimization_e2c2"
REPO=ROOT.parents[1]
sys.path.insert(0,str(C2))
from settings import INITIAL, clock, sha, read, write
BASE="5f667cf5103f26f8e908c542f400ecf3f59c8a1e"
COMPACT_BASE="82821ae54b8a4e9b9f83ce5930c93aea2a204086"
METHODS=("Full","NoAux","NoCore")
SEEDS=(101,102,103)

def use_aux(variant):
    assert variant in METHODS
    return variant!="NoAux"

def core_kind(variant,iteration,grant):
    if iteration%4==3:
        assert grant is None
        return "ordinary_full"
    if grant is None:return "fallback"
    return None if variant=="NoCore" else "compact_core"
