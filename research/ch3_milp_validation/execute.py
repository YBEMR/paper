"""Bind the six registered inputs to byte-identical frozen worker, master and launcher."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parent/"ch3_milp_feasibility"


def load_files():
    registration = json.loads((HERE/"registration.json").read_bytes())
    for name, digest in registration["sha256"].items():
        if sha256((FROZEN/name).read_bytes()).hexdigest()!=digest:
            raise ValueError(f"frozen implementation mismatch: {name}")
    return registration, json.loads((FROZEN/"protocol.json").read_bytes())


def config_bytes(registration, original, label):
    config = dict(original, source=registration["source"], cases={label:registration["cases"][label]})
    return (json.dumps(config, indent=2)+"\n").encode("utf-8")


def main():
    reg, original = load_files()
    output = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else HERE/"raw"
    if any((output/key).exists() for key in reg["cases"]):
        raise FileExistsError("choose an empty output destination")
    failed = []
    # The original worker resolves the repository relative to the script location.
    with TemporaryDirectory(prefix="milp-registered-",dir=HERE.parent) as tmp:
        work = Path(tmp)
        for name in reg["sha256"]:
            shutil.copyfile(FROZEN/name, work/name)
        for label in reg["cases"]:
            (work/"protocol.json").write_bytes(config_bytes(reg,original,label))
            run = subprocess.run([sys.executable,"-B",str(work/"launch.py"),str(output)])
            if run.returncode:
                failed.append(label)
    if failed:
        raise SystemExit("failed workers (receipts retained): "+", ".join(failed))


if __name__=="__main__":
    main()
