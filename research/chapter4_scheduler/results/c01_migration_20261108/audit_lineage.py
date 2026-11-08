"""Read-only source reconstruction; never use reference schedules as seeds."""
from contextlib import ExitStack
from datetime import datetime,timezone
import gzip
from pathlib import Path
import sys
import time
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read,save,sha,digest,environment
from research.chapter4_scheduler.c01.input import SOURCE,SOURCE_SHA256
from research.chapter3_workload_calibration.generator import subset
from research.chapter3_formal_input_adapter.core import adapt_bundle

started=datetime.now(timezone.utc).isoformat();clock=time.monotonic();checks=[]
def check(name,value):
    checks.append({"name":name,"passed":bool(value)})
    if not value:raise AssertionError(name)
def deny(*args,**kwargs):raise AssertionError("LINEAGE_AUDIT_FORBIDS_SCHEDULING_OR_INTEGRATION")
archive=REPO/"research/chapter3_workload_calibration/results/calibration01/C01__base_6/evidence.json.gz"
payload_path=REPO/"research/chapter3_formal_input_adapter/results/frozen_semantic02/payload.json"
config_path=REPO/"research/chapter3_experiments/config_v01.json"
with ExitStack() as stack:
    for name in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","heft_method.run_heft","heft_method.build_heft_candidate","sa_method.run_sa"):
        stack.enter_context(patch(name,side_effect=deny))
    check("original calibration evidence hash",sha(archive)=="6f80ec8e944b0753a5a7e73cb8660a0b19c27fd604fba05b6aaf0ce021352d76")
    check("original semantic payload hash",sha(payload_path)=="6dc0b254d412f6a103d22c8b7bf3c8375d1d7a026a0224213e03e4447c11bc74")
    check("candidate-free common input hash",sha(SOURCE)==SOURCE_SHA256)
    import json
    evidence=json.loads(gzip.decompress(archive.read_bytes()));payload=read(payload_path);common=read(SOURCE)
    workload=subset(evidence["workload"],2)
    deadlines=evidence["S1_projections"]["2"]["deadlines"]["13/10"]
    reproduced=adapt_bundle(workload,deadlines,payload["window_receipt"],member_key="2",config=read(config_path),instance_id=common["instance"]["id"])
    check("re-exported input exact equality",reproduced["instance"]==common["instance"])
    check("re-exported config exact equality",reproduced["config"]==common["config"])
    check("adapter receipt and payload equality",reproduced["receipt"]==payload["adapted"]["receipt"])
    check("common receipt provenance",reproduced["receipt"]["receipt_hash"]==common["provenance"]["adapter_receipt_sha256"])
    check("no fixed deployment or formal initial solution",reproduced["receipt"]["fixed_deployment"] is None and reproduced["receipt"]["formal_initial_solution"] is None)
    i=common["instance"];ab=read(REPO/"research/chapter4_scheduler/results/main_comparison_20261108/execution/frozen_inputs/base__R2/instance.json")
    check("identical original physical platform",i["platform"]==ab["platform"])
    check("identical original control and execution rules",i["execution_rules"]==ab["execution_rules"])
    check("actual instance window retained instead of default",i["window_ms"]=="230" and common["config"]["defaults"]["window_ms"]=="400")
    check("both scenes and all modes retained",len(i["scenarios"])==2 and len(i["stage_modes"])==8 and sum(map(len,i["stage_modes"].values()))==72)
    selected={name:app for name,app in workload["applications"].items() if name in {s["application"] for scene in i["scenarios"] for s in scene["stage_instances"]}}
    scene_records=[{"id":s["id"],"weight":s["weight"],"requests":s["requests"],"stage_instances":s["stage_instances"],"dependencies":s["dependencies"],"entry":s["entry"],"maximum_temperature_degC":s["maximum_temperature_degC"]} for s in i["scenarios"]]
    check("source profiles not regenerated or rescaled",reproduced["instance"]["stage_modes"]==payload["adapted"]["instance"]["stage_modes"])
    check("reference deployment and timetable not imported",not reproduced["receipt"]["reference_deployment_imported"] and not reproduced["receipt"]["reference_timetable_imported"])
record={"started_utc":started,"ended_utc":datetime.now(timezone.utc).isoformat(),"wall_s":time.monotonic()-clock,
    "passed":all(c["passed"] for c in checks),"checks":checks,"nature":"Read-only archived workload/subset/deadline/window reconstruction through original adapter; no new tasks, scheduling, reference construction, optimization or thermal integration",
    "environment":environment(),"source_files_sha256":{p.relative_to(REPO).as_posix():sha(p) for p in (archive,payload_path,SOURCE,config_path,
        REPO/"research/chapter3_formal_input_adapter/core.py",REPO/"research/chapter3_formal_input_adapter/semantic_precheck.py",
        REPO/"research/chapter3_method_entry_preparation/prepare.py",REPO/"research/chapter3_workload_calibration/generator.py",REPO/"research/chapter3_workload_calibration/topology.py")},
    "input_sha256":digest(i),"config_sha256":digest(common["config"]),"application_templates":selected,"scenes":scene_records,
    "active_shared_legal_units":reproduced["receipt"]["active_shared_legal_units"],"window_receipt":payload["window_receipt"],
    "reference_payload_read_for_provenance_only":True,"reference_answer_used_by_loader_or_smoke":False,
    "real_constructor_calls":0,"real_method_calls":0,"real_thermal_calls":0}
save(OUT/"lineage_audit.json",record)
print({"passed":record["passed"],"checks":len(checks),"wall_s":record["wall_s"],"input_sha256":record["input_sha256"],"templates":selected},flush=True)
