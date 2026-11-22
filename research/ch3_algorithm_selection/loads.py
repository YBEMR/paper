"""Generate once; verify every frozen request and its scene independently on admission."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE/"config.json").read_bytes())
GRID = 40_000_000
NAMES = ["sc0", "sc1", "sc2", "sc3"]


def packed(rows):
    return json.dumps(rows, separators=(",", ":")).encode()


def create(spec):
    rows = []
    offset = 0
    for frames, apps in zip(spec["frames"], spec["active"], strict=True):
        for frame in range(offset, offset + frames):
            for app in apps:
                rows.append([f"f{frame:04d}-a{app}", app, frame*GRID, (frame+1)*GRID])
        offset += frames
    return rows


def verify(rows, spec):
    from bisect import bisect_right
    from itertools import accumulate
    edges = list(accumulate(spec["frames"]))
    if edges[-1] != 250 or len(edges) != 4 or len(rows) != 500:
        raise ValueError("Invalid service or request count")
    frame_apps = [[] for _ in range(250)]
    for ident, app, release, due in rows:
        frame, residual = divmod(release, GRID)
        if residual or not 0 <= frame < 250 or due != release+GRID or ident != f"f{frame:04d}-a{app}":
            raise ValueError("Invalid job or frame grid")
        frame_apps[frame].append(app)
    if any(apps != spec["active"][bisect_right(edges, frame)] for frame, apps in enumerate(frame_apps)):
        raise ValueError("Incorrect scene membership or duplicated job")
    if Counter(row[1] for row in rows) != dict(enumerate(spec["counts"])):
        raise ValueError("Incorrect per-network request counts")
    return sha256(packed(rows)).hexdigest()


def freeze():
    dest = HERE/"streams"
    dest.mkdir(exist_ok=True)
    manifest = {}
    for load, spec in CFG["loads"].items():
        rows = create(spec)
        digest = verify(rows, spec)
        if load == "original" and digest != CFG["original_sha"]:
            raise ValueError("Reference differs from historical forward_flat")
        (dest/f"{load}.json").write_bytes(packed(rows)+b"\n")
        manifest[load] = digest
    (dest/"sha256.json").write_bytes(packed(manifest)+b"\n")


def install(ev, load):
    """The frozen constructor has validated forward_flat and initialized empty caches."""
    spec = CFG["loads"][load]
    rows = json.loads((HERE/"streams"/f"{load}.json").read_bytes())
    digest = verify(rows,spec)
    if digest != json.loads((HERE/"streams/sha256.json").read_bytes())[load]:
        raise ValueError("Stream digest changed")
    from itertools import accumulate
    switches = list(zip([n*GRID for n in [0,*accumulate(spec["frames"][:-1])]], NAMES, strict=True))
    events = ev.events
    scenes = events.partition_requests([events.Request(*row) for row in rows], switches, 251*GRID, 250*GRID)
    if ev.unit.absolute_requests(scenes) != rows or any(
        (s.start_ns,s.service_end_ns,s.end_ns) !=
        (switches[j][0], switches[j][0]+spec["frames"][j]*GRID,
         switches[j][0]+(spec["frames"][j]+int(j==3))*GRID) for j,s in enumerate(scenes)):
        raise ValueError("Physical scenes differ from frozen load")
    if load == "original" and (scenes != ev.scenes or digest != ev.identity):
        raise ValueError("Reference replay scenes differ")
    ev.scenes, ev.identity = scenes, digest
    ev.case_id = f"{load}_{int(ev.ambient)}C"
    ev.counts = [Counter(q.app for q in scene.requests) for scene in scenes]


if __name__ == "__main__":
    freeze()
