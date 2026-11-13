"""Load the existing candidate-free two-scene C01 contract without rewriting it.

This bridge does not use the AB/AC P0 loader, regenerate tasks/deadlines,
read reference schedules, fix mappings, or change any mode/start choices.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from research.chapter3_method_entry_preparation.prepare import validate_common_input

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / "research/chapter3_method_entry_preparation/results/frozen_entry02/common_input.json"
SOURCE_SHA256 = "07e458f3f811746f78931a340d258e230a8de4afb62ac0140459feff6a7bf80a"


def load_c01(budget, *, source=SOURCE):
    """Return fresh config/instance on the caller's unchanged charged root.

The pinned input is the existing C01 C1/C2 projection, not all eight source
scenarios or a new task family. Its instance horizon is 230ms even though
the unmodified legacy config default remains 400ms. No experiment is run.
"""
    budget.check()
    raw = Path(source).read_bytes()
    budget.check()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("C01_COMMON_INPUT_FILE_DRIFT")
    value = json.loads(raw)
    validate_common_input(value)
    if (value["provenance"]["root_id"] != "C01"
            or value["provenance"]["scenario_subset"] != ["C1", "C2"]
            or value["provenance"]["beta"] != "13/10"):
        raise ValueError("C01_COMMON_INPUT_SCOPE_DRIFT")
    budget.check()
    return deepcopy(value["config"]), deepcopy(value["instance"])
