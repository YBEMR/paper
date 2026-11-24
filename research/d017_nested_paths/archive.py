"""Hash final deliverables; default read-only verification."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
manifest=HERE/"archive_manifest.json"
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if "--write" in sys.argv:
    entries={p.relative_to(HERE).as_posix():digest(p) for p in sorted(HERE.rglob("*"))
        if p.is_file() and p!=manifest and "__pycache__" not in p.parts}
    manifest.write_text(json.dumps(entries,indent=2)+"\n",encoding="utf-8")
else:
    entries=json.loads(manifest.read_bytes())
    for name,h in entries.items():assert digest(HERE/name)==h,name
print(dict(archive_files=len(entries),status="PASS"))
