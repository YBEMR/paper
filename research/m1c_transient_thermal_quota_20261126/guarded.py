"""Development-only gated replacement, same from-empty starts and terminal rule."""
from common import CASES
from run import fixed

if __name__=="__main__":
    for case in CASES:
        for gen in (("H","N","Hs") if case=="L800" else ("H",)):
            fixed(case,gen,"guarded")
