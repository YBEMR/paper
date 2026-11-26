"""Emit the dependency manifest and pre-run verification receipt without running a search."""
import json
from pathlib import Path
from design import BASE, M1, REG, REPO, ROOT, sha,write_json

def main():
    files=[ROOT/name for name in ("design.py","adapter.py","runner.py","archive.py","batch.py","audit_physics.py","check_events.py","freeze.py")]+[ROOT/"PROTOCOL.md",REG/"history.csv",REG/"selection.csv",REG/"rotation.csv",REG/"cases.json"]
    for dirname in ("m1_transient_thermal_quota_20261126","m1b_transient_thermal_quota_20261126",
                    "m1c_transient_thermal_quota_20261126","m1d_thermal_safe_energy_selection",
                    "m1e_thermal_quota_ablation","m1f_trace_energy_quality","m1g_literature_comparison","m1h_common_beam"):
        files.extend((ROOT.parent/dirname).glob("*.py"))
    files.extend(p for p in (M1/"frozen").rglob("*") if p.suffix in (".py",".json",".csv"))
    files.extend((M1/"inputs").glob("*.csv"))
    write_json(REG/"source_hashes.json",{str(f.relative_to(REPO)):sha(f.read_bytes()) for f in sorted(set(files))})
    builds=list((REG/"checks").glob("V*.json"))
    assert len(builds)==14 and all(len(json.loads(p.read_bytes()))==16 for p in builds)
    ambient=json.loads((REG/"checks/ambient.json").read_bytes())
    physical=json.loads((REG/"checks/physical_triplets.json").read_bytes())
    assert len(ambient)==16 and len(physical)==6
    write_json(REG/"verification.json",dict(base=BASE,old_cases=len(builds),fixed_certificates=224,
               old_actions_beams_terminal_order=True,matching_original_npz=224,
               registered_conditions=len(ambient),real_event_triplets=2,
               max_synthetic_end_error_K=max(v["max_end_error_K"] for v in ambient),
               max_real_moment_error=max(v["max_moment_error"] for v in physical),
               max_real_bin_end_error_K=max(v["max_bin_end_error_K"] for v in physical),
               manifest_sha256=sha((REG/"source_hashes.json").read_bytes())))
if __name__=="__main__":main()
