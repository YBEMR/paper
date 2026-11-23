"""Read-only adapters for the twelve inputs approved at 3db685b."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REVIEW = ROOT / "research/multidnn_model_review"
sys.path.insert(0, str(REVIEW))
from verify_inputs import verify_rows, require, sha
sys.path.insert(0, str(ROOT / "research/kim_scene_dvfs_admission"))
import scene_events as events


def read(path):
    return json.loads(path.read_bytes())


class Instance:
    def __init__(self, case_id):
        cfg = read(REVIEW / "protocol.json")
        manifest = read(REVIEW / "input_manifest.json")
        for name, expected in manifest.items():
            require(sha(REVIEW / name) == expected, f"input changed: {name}")
        sources = read(REVIEW / "frozen_sources.json")
        for name, expected in sources["sha256"].items():
            require(sha(ROOT / name) == expected, f"source changed: {name}")
        self.case = read(REVIEW / "inputs/cases" / (case_id + ".json"))
        self.stream = read(REVIEW / self.case["input_stream"])
        starts = verify_rows(self.stream, cfg)
        self.window_ns = self.case["objective_window_ns"]
        self.scenes = events.partition_requests(
            [events.Request(*r) for r in self.stream["requests"]],
            list(zip(starts, cfg["orders"][self.case["order"]])),
            self.window_ns, cfg["service_ns"])
        recovered = [[q.id, q.app, q.release_ns+s.start_ns, q.deadline_ns+s.start_ns]
                     for s in self.scenes for q in s.requests]
        require(recovered == self.stream["requests"], "request coverage changed")
        self.required = self.case["required"]
        require(self.required == len(recovered) == sum(self.case["counts"]), "expected count")
        self.ambient = self.case["ambient_c"]
        self.initial = self.case["initial_c"]
        require(min(self.initial) >= 25 and self.ambient >= 25, "thermal affine domain")
        self.platform = deepcopy(events.PLATFORM)
        self.platform["thermal"]["initial_C"] = list(self.initial)
        self.domain = read(REVIEW / self.case["domain"])
        require(sha(REVIEW / self.case["domain"]) == self.case["domain_sha256"], "domain hash")
        self.order = self.domain["search_order"]
        require(len(self.order) == 81, "concrete deployment count")
        self.frozen = read(ROOT / cfg["domain"]["source_deployments"])
        require(self.domain["deployments"] == self.frozen["deployments"], "domain entities")
        require(self.frozen["clock_policy"] == self.domain["clock_policy"], "clock policy")
        self.identity = sha256(json.dumps(dict(case=self.case, stream=self.stream,
            domain=self.domain, source_manifest_sha=sha(REVIEW / "frozen_sources.json")),
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def bind(self):
        # Process-local copies only. Frozen source/config files are not edited.
        events.PLATFORM = self.platform
        events.FROZEN = self.frozen

    def replay(self, deployment, opps):
        self.bind()
        p = events.replay_sequence(self.platform, self.scenes, deployment, opps, self.ambient)
        if p["fully_replayed"]:
            require(p["required"] == p["completed"] == self.required, "full request certificate")
            require(p["scene_rows"][-1]["end_ns"] == self.window_ns, "tail missing")
        return p
