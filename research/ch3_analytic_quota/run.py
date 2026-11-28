"""Use the previously audited single-core supervisor and physical archive layout."""
import importlib.util
import inspect
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PREV=ROOT.parent/"ch3_mapping_first_nested"

def load(name):
    spec=importlib.util.spec_from_file_location(name,PREV/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT=ROOT
    return module

def lane(code):
    module=load("lane")
    source=inspect.getsource(module.main)
    gate='    gate = json.loads((ROOT/"stage1/gate.json").read_bytes())\n    assert gate["passed"] and gate["safe"]==12\n'
    for old,new in ((gate,""),('"baseline"','"fit"'),('"unified"','"analytic"'),('"paired.py"','"method.py"')):
        assert old in source
        source=source.replace(old,new)
    exec(compile(source,"<frozen single-core supervisor>","exec"),module.__dict__)
    module.main(code)

def pack(code):
    load("pack_lane").main(code)
    for path in (ROOT/"paired_raw"/code).glob("*/parent-*.json"):
        target=ROOT/"paired_results"/code/path.parent.name/path.name
        shutil.copyfile(path,target)

if __name__=="__main__":
    {"lane":lane,"pack":pack}[sys.argv[1]](sys.argv[2])
