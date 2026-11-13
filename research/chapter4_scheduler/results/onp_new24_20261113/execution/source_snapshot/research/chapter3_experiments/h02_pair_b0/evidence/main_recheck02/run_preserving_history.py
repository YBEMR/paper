"""Rerun unchanged B0 pure/mock checks; preserve imported historical receipts."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
CORE=HERE.parents[2]
sys.path.insert(0,str(CORE)); sys.dont_write_bytecode=True
import tempfile,os
test_temp=HERE/"mock_temp"
test_temp.mkdir(exist_ok=True)
os.environ["TEMP"]=str(test_temp); os.environ["TMP"]=str(test_temp)
tempfile.tempdir=str(test_temp)
from h02_pair_b0 import run_precheck as original
from h02_pair_b0.io_contract import atomic_json
REDIRECT={"regression_tests.json","input_identity_check.json","run_ledger.json"}
def preserve(path,value):
    path=Path(path)
    if path.parent==original.HERE/"evidence" and path.name in REDIRECT:
        path=HERE/path.name
    atomic_json(path,value)
original.atomic_json=preserve
if __name__=="__main__": raise SystemExit(original.main())
