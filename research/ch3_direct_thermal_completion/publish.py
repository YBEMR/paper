"""Stage only individually inventoried output files of this continuation."""
from pathlib import Path
import subprocess
from prepare import ROOT, DRIVER

files = [ROOT/"SHA256SUMS"]
for line in files[0].read_text().splitlines():
    name = line.split(maxsplit=1)[1]
    path = (ROOT/name).resolve()
    assert path.is_relative_to(ROOT) and path.is_file()
    files.append(path)
names = [p.relative_to(DRIVER).as_posix() for p in files]
subprocess.run(["git","add","--sparse","--pathspec-from-file=-","--pathspec-file-nul"],cwd=DRIVER,
               input=b"\0".join(n.encode() for n in names)+b"\0",check=True)
staged = subprocess.check_output(["git","diff","--cached","--name-only","-z"],cwd=DRIVER).decode().split("\0")
assert set(filter(None,staged)) == set(names)
