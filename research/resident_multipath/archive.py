"""Write/verify a content-addressed delivery inventory without rerunning experiments."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = HERE.relative_to(ROOT).as_posix() + "/"
MANIFEST = HERE / "archive_manifest.json"


def inventory():
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", PREFIX], cwd=ROOT)
    names = sorted(set(x.decode("utf-8") for x in output.split(b"\0") if x))
    result = {}
    for name in names:
        assert name.startswith(PREFIX)
        path = ROOT / name
        if path == MANIFEST:
            continue
        data = path.read_bytes()
        result[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Freeze the completed delivery inventory")
    args = parser.parse_args()
    files = inventory()
    if args.write:
        environment = json.loads((HERE / "environment.json").read_bytes())
        result = dict(schema=1,execution_commit=environment["execution_commit"],
            scope="Git-visible task files only; this self-referential manifest excluded",
            files=files)
        MANIFEST.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode())
    else:
        result = json.loads(MANIFEST.read_bytes())
        assert result["files"] == files, "Archive files changed or file inventory differs"
    print({"status": "written" if args.write else "PASS", "files": len(files),
           "bytes": sum(row["bytes"] for row in files.values())})


if __name__ == "__main__":
    main()
