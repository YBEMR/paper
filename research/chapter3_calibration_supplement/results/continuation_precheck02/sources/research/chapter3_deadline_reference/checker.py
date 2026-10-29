"""Independent structural time checker, with no planner or thermal dependency.

The response equation, interval endpoints and all pairwise conflicts are
recomputed here.  No result from this module is a thermal SAFE certificate.
"""

from .contract import ContractError, content_hash, exact, normalize


class _InvalidSchedule(ValueError):
    def __init__(self, reason, **details):
        self.reason, self.details = reason, details
        super().__init__(reason)


def _require(condition, reason, **details):
    if not condition:
        raise _InvalidSchedule(reason, **details)


def check_timetable(data, candidate, *, required_opp=None):
    """Check complete scenario coverage without deadlines or a finite horizon.

    ``required_opp=None`` checks general legal per-Stage operating points.
    Supplying H/M/L additionally checks a fixed reference-frequency table.
    The optional argument never changes duration response parameters.
    """
    try:
        normalized = normalize(data)
    except ContractError as error:
        return {"state": "INPUT_CONTRACT_ERROR", "reason": error.code, "details": error.details,
                "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
    try:
        _require(required_opp is None or required_opp in ("H", "M", "L"), "INVALID_REQUIRED_OPP")
        _require(isinstance(candidate, dict) and set(candidate) == {"scenes"}, "CANDIDATE_FIELDS")
        _require(isinstance(candidate["scenes"], dict), "SCENES_OBJECT_REQUIRED")
        scenes = {scene["id"]: scene for scene in normalized["scenarios"]}
        _require(set(candidate["scenes"]) == set(scenes), "INCOMPLETE_SCENARIO_COVERAGE")
        units = {unit["id"]: unit for unit in normalized["platform"]["units"]}
        grid = exact(normalized["start_grid_ms"])
        deployment, completions, all_rows, canonical_scenes = {}, {}, {}, {}
        for scene_id, scene in scenes.items():
            supplied = candidate["scenes"][scene_id]
            _require(isinstance(supplied, list), "SCENE_ROWS_MUST_BE_LIST", scenario=scene_id)
            stages = {stage["id"]: stage for stage in scene["stage_instances"]}
            requests = {request["id"]: request for request in scene["requests"]}
            rows, seen = [], set()
            for given in supplied:
                _require(isinstance(given, dict) and set(given) == {"stage_id", "unit", "opp", "start_ms"},
                         "CANDIDATE_ROW_FIELDS", scenario=scene_id)
                stage_id = given["stage_id"]
                _require(isinstance(stage_id, str) and stage_id in stages, "UNKNOWN_STAGE", scenario=scene_id)
                _require(stage_id not in seen, "DUPLICATE_STAGE_ASSIGNMENT", stage=stage_id)
                seen.add(stage_id)
                stage = stages[stage_id]
                uid, opp = given["unit"], given["opp"]
                _require(isinstance(uid, str) and uid in units and uid in stage["legal_units"],
                         "ILLEGAL_EXECUTION_UNIT", stage=stage_id)
                _require(isinstance(opp, str) and opp in ("H", "M", "L"), "ILLEGAL_OPP", stage=stage_id)
                _require(required_opp is None or opp == required_opp, "REFERENCE_OPP_MISMATCH", stage=stage_id)
                shared_id = stage["shared_stage_id"]
                if shared_id in deployment:
                    _require(deployment[shared_id] == uid, "SHARED_DEPLOYMENT_MISMATCH", shared_stage_id=shared_id)
                else:
                    deployment[shared_id] = uid
                domain_id = units[uid]["domain_id"]
                domain = normalized["platform"]["domains"][domain_id]
                profile = normalized["stage_profiles"][shared_id]["units"][uid]
                _require(opp in profile["legal_opps"], "ILLEGAL_OPP", stage=stage_id)
                # Deliberate independent equation, not contract.duration.
                d_ref = exact(profile["d_ref_ms"])
                alpha = exact(profile["alpha"])
                f_ref = exact(domain["opps"][domain["reference_opp"]]["frequency_GHz"])
                frequency = exact(domain["opps"][opp]["frequency_GHz"])
                duration = d_ref * ((1 - alpha) + alpha * f_ref / frequency)
                start = exact(given["start_ms"])
                _require(start >= 0 and (start / grid).denominator == 1, "START_OUTSIDE_GRID", stage=stage_id)
                request = requests[stage["request_id"]]
                _require(start >= exact(request["release_ms"]), "BEFORE_RELEASE", stage=stage_id)
                rows.append({"stage_id": stage_id, "request_id": stage["request_id"],
                             "shared_stage_id": shared_id, "unit": uid, "opp": opp,
                             "domain_id": domain_id, "start_ms": start, "end_ms": start + duration,
                             "duration_ms": duration})
            _require(seen == set(stages), "INCOMPLETE_STAGE_COVERAGE", scenario=scene_id,
                     missing=sorted(set(stages) - seen))
            by_id = {row["stage_id"]: row for row in rows}
            for predecessor, successor in scene["dependencies"]:
                _require(by_id[predecessor]["end_ms"] <= by_id[successor]["start_ms"],
                         "DEPENDENCY_VIOLATION", predecessor=predecessor, successor=successor)
            for index, left in enumerate(rows):
                for right in rows[index + 1:]:
                    overlap = max(left["start_ms"], right["start_ms"]) < min(left["end_ms"], right["end_ms"])
                    if not overlap:
                        continue
                    _require(left["unit"] != right["unit"], "EXECUTION_UNIT_OVERLAP",
                             stages=[left["stage_id"], right["stage_id"]])
                    _require(left["domain_id"] != right["domain_id"] or left["opp"] == right["opp"],
                             "FREQUENCY_DOMAIN_CONFLICT", stages=[left["stage_id"], right["stage_id"]])
            completions[scene_id] = {
                request_id: str(max(row["end_ms"] for row in rows if row["request_id"] == request_id))
                for request_id in sorted(requests)
            }
            ordered = sorted(rows, key=lambda row: (row["start_ms"], row["stage_id"]))
            all_rows[scene_id] = [dict(row, start_ms=str(row["start_ms"]), end_ms=str(row["end_ms"]),
                                       duration_ms=str(row["duration_ms"])) for row in ordered]
            canonical_scenes[scene_id] = [
                {key: str(row[key]) if key == "start_ms" else row[key]
                 for key in ("stage_id", "unit", "opp", "start_ms")}
                for row in sorted(rows, key=lambda row: row["stage_id"])
            ]
        return {"state": "TIME_STRUCTURAL_VALID", "contract_hash": content_hash(normalized),
                "shared_deployment": {key: deployment[key] for key in sorted(deployment)},
                "completions_ms": completions, "rows": all_rows,
                "timetable_hash": content_hash({"scenes": canonical_scenes}),
                "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
    except _InvalidSchedule as error:
        return {"state": "INVALID_SCHEDULE", "reason": error.reason, "details": error.details,
                "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
    except ContractError as error:
        # Input contract was already checked; this error is a candidate scalar.
        return {"state": "INVALID_SCHEDULE", "reason": error.code, "details": error.details,
                "thermal_status": "NOT_EVALUATED", "energy_status": "NOT_EVALUATED"}
