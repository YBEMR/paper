"""Necessary fixed-witness regression, not a workload/search pilot."""
import os
for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
from pathlib import Path
from time import perf_counter
import json
import numpy as np
from instance import Instance, ROOT, HERE, events, read
from adapter import load_m2


def main():
    start = perf_counter()
    rows = []
    specs = [
        ("balanced_forward_reference_start","C","forward_flat_25C","independent"),
        ("balanced_reverse_reference_start","C","reverse_flat_25C","independent"),
        ("balanced_forward_reference_start","D005","forward_flat_25C","joint"),
        ("balanced_forward_preheated","C",None,None),
    ]
    source_sha = read(ROOT / "research/multidnn_model_review/frozen_sources.json")["sha256"][
        "research/kim_multidnn_search_trial/solver.py"]
    for case_id, dep, archive_case, selector in specs:
        instance = Instance(case_id)
        m, source, patches = load_m2(instance, source_sha)
        archived = None
        if archive_case:
            path = ROOT / "research/kim_multidnn_expansion/raw/expanded" / archive_case / f"deployment_{dep}.json"
            chosen = read(path)[selector]
            opps, archived = chosen["opps"], chosen["physical"]
        else:
            opps = ["LLL","LLL","LHL","LHL"]
        physical = instance.replay(dep, opps)
        schedules = [events.time_scene(instance.platform,s,dep,o) for s,o in zip(instance.scenes,opps)]
        assert all(s.deadline_feasible for s in schedules)
        kernels = [m.thermal.compile_scene(s.duration_ns*1e-9,s.active_w,s.transfer_w,
                    events.thermal_kwargs(instance.platform,o,instance.ambient,True,"base"))
                   for s,o in zip(schedules,opps)]
        temp = np.array(instance.initial)[None,:]
        energy = 0.
        state = np.ones(1,dtype=np.uint8)
        for kernel in kernels:
            e,temp,status = kernel.batch(temp)
            energy += e[0]
            state = m.joint.combine(state,status)
        assert abs(energy-physical["energy_j"]) <= 1e-7
        assert max(abs(temp[0]-physical["final_c"])) <= 1e-7
        assert int(state[0]) == {"SAFE":1,"VIOLATION":2,"UNRESOLVED":3}[physical["thermal_status"]]
        assert physical["required"] == physical["completed"] == instance.required
        error = None
        if archived:
            error = dict(energy_j=abs(physical["energy_j"]-archived["energy_j"]),
                         peak_upper_c=max(abs(np.array(physical["peak_upper_c"])-archived["peak_upper_c"])),
                         final_c=max(abs(np.array(physical["final_c"])-archived["final_c"])),
                         slack_ms=abs(physical["min_slack_ms"]-archived["min_slack_ms"]))
            assert error["energy_j"] <= 1e-7 and error["peak_upper_c"] <= 5.1e-4
            assert error["final_c"] <= 1e-7 and error["slack_ms"] == 0
            assert physical["thermal_status"] == archived["thermal_status"]
        if case_id == "balanced_forward_reference_start" and dep == "C":
            approved = read(ROOT / "research/multidnn_model_review/inputs/preheat_state.json")
            assert max(abs(np.array(physical["final_c"])-approved["initial_c"])) <= 1e-7
        rows.append(dict(case_id=case_id,deployment=dep,opps=opps,physical=physical,
                         archival_error=error,affine_energy_error_j=float(abs(energy-physical["energy_j"])),
                         affine_final_error_c=float(max(abs(temp[0]-physical["final_c"])))))
        print(case_id,dep,physical["thermal_status"],physical["energy_j"],"PASS",flush=True)
    report = dict(status="PASS",role="fixed witness regression only; no optimizer/pilot run",
                  elapsed_s=perf_counter()-start,tests=rows)
    path = HERE / "regression.json"
    path.write_bytes((json.dumps(report,indent=2,allow_nan=False)+"\n").encode())


if __name__ == "__main__":
    main()
