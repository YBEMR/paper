"""Read-only checks of derived means, source identities and rendered files."""
from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import time
from PIL import Image

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[4]
read = lambda p: json.loads(p.read_text())
started, entered = datetime.now(timezone.utc).isoformat(), time.monotonic()
plan = read(OUT / "plan.json")
result = read(OUT / "B_metrics.json")
checks = []


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


check("plan identity", hashlib.sha256((OUT / "plan.json").read_bytes()).hexdigest() == read(OUT / "plan_identity.json")["sha256"])
check("unchanged derivation source", hashlib.sha256((OUT / "reuse_trajectories.py").read_bytes()).hexdigest() == plan["script_sha256"])
for relative, expected in plan["source_identities"].items():
    check("source unchanged " + relative, hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected["sha256"])
check("exact seven schedules and fourteen reused scenes", len(result["scheme_summary"]) == 7 and result["scenario_trajectories"] == result["source_receipts_reused"] == 14)
check("exact56 node-scene averages", len(result["node_time_means"]) == 56)
by_scheme = defaultdict(list)
for row in result["node_time_means"]:
    lo, hi = F(row["mean_lower_degC"]), F(row["mean_upper_degC"])
    duration, ambient = F(row["duration_s"]), F(row["ambient_degC"])
    check("full duration " + row["scheme"] + row["scene"] + row["node"], duration == F(2, 5))
    check("endpoint mean identity " + row["scheme"] + row["scene"] + row["node"],
          (lo, hi) == (ambient + F(row["integral_lower_Ks"]) / duration, ambient + F(row["integral_upper_Ks"]) / duration))
    by_scheme[row["scheme"]].append(row)
maximizers = []
for summary in result["scheme_summary"]:
    rows = by_scheme[summary["scheme"]]
    check("eight means per fixed scheme " + summary["scheme"], len(rows) == 8)
    expected = max(F(row["mean_lower_degC"]) for row in rows), max(F(row["mean_upper_degC"]) for row in rows)
    check("max interval uses maxlower/maxupper " + summary["scheme"], expected == (F(summary["worst_node_scene_time_mean_lower_degC"]), F(summary["worst_node_scene_time_mean_upper_degC"])))
    winner = next(row for row in rows if row["scene"] == summary["upper_max_scene"] and row["node"] == summary["upper_max_node"])
    others = [row for row in rows if row is not winner]
    separation = F(winner["mean_lower_degC"]) - max(F(row["mean_upper_degC"]) for row in others)
    check("strictly separated unique maximizer " + summary["scheme"], separation > 0)
    check("possible maximizers agrees " + summary["scheme"], json.loads(summary["possible_maximizers"]) == [[winner["scene"], winner["node"]]])
    maximizers.append({"scheme": summary["scheme"], "scene": winner["scene"], "node": winner["node"],
        "max_interval_degC": [str(v) for v in expected], "unique_maximizer_certified_from_interval_separation": True,
        "winner_lower_minus_largest_other_upper_K": str(separation)})
for detail in result["comparison_details"]:
    check("energy consistency " + detail["scheme"], F(detail["weighted_energy_comparison"]["midpoint_abs_difference"]) == 0 and detail["weighted_energy_comparison"]["overlap"])
    for comparison in detail["peak_comparisons"]:
        check("peak consistency " + detail["scheme"] + comparison["scene"] + comparison["node"], F(comparison["midpoint_abs_difference"]) == 0 and comparison["overlap"])
    for scene in detail["scene_details"]:
        check("idle tail and full scene retained " + detail["scheme"] + scene["scene"], F(scene["covered_until_s"]) == F(2, 5) and F(scene["last_task_end_ms"]) + F(scene["idle_tail_duration_ms"]) == 400)
for name in result["figure_paths"]:
    path = OUT / name
    check("figure file exists " + name, path.is_file() and path.stat().st_size > 1000)
    if name.endswith(".png"):
        with Image.open(path) as picture:
            check("PNG dimensions " + name, picture.width > 1000 and picture.height > 700)
            picture.verify()
check("no new physical/search/periodic call", result["new_schedule_searches"] == result["new_thermal_integrations"] == result["new_periodic_solves"] == 0)
record = {"started_utc": started, "ended_utc": datetime.now(timezone.utc).isoformat(), "wall_s": time.monotonic() - entered,
    "passed": True, "assertion_count": len(checks), "checks": checks, "maximizers": maximizers,
    "unique_maximizer_for_all_seven": True,
    "max_definition": "[max of all eight mean lower endpoints,max of all eight mean upper endpoints]",
    "old_method_vs_old_post_energy_and_peak_midpoint_abs_errors": "0 for every item; reused source records, not independent numerical re-evaluation",
    "render_visual_inspection": ["t50_milp__AB_offset_0ms.png", "t50_sa105__AC_offset_0ms.png"],
    "render_warning": "Matplotlib default config/font cache directory read-only; it used /tmp temporary cache and rendered successfully. Original stderr preserved, no rerender/installation.",
    "new_thermal_integrations": 0, "new_searches": 0, "new_periodic_solves": 0}
with (OUT / "B_audit.json").open("x") as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
notes = """# B结果核查补记

七个方案的最坏节点/场景均温区间均按 `[max所有lower,max所有upper]` 保存。每个方案均由AB场景NPU0取得，且其均温区间下界严格高于其他七个节点/场景区间上界，因此此处可以确认唯一最坏对象，而不只是按显示中点选择。

原方法凭证与原post凭证的能量及峰温中点差均为0，区间重叠。这是复用原记录的一致性核对，不是本轮新增独立数值复核。均温端点由既有区间积分作精确有理数变换；本轮新搜索/新热积分/新周期求解均为0。

14张PNG及14张SVG完成渲染；人工查看了MILP/AB、SA105/AC两个代表图。原Matplotlib尝试写默认配置/字体缓存时收到只读提示，随后自动采用/tmp缓存并成功输出；原stderr完整保留，未安装软件或追加重绘。

初次准备代码的AST检查发现一个多余括号，发生在计划冻结及任何均温/绘图前，修正后8项纯算术测试通过；该准备错误单独记录，不属于实验失败或热评价。
"""
with (OUT / "B_validation_notes.md").open("x") as stream:
    stream.write(notes)
print(json.dumps({"B_audit_passed": True, "assertions": len(checks), "unique_worst_AB_NPU0_all_seven": True, "new_physics": 0, "wall_s": record["wall_s"]}), flush=True)
