"""Read terminal K184 archives only; no scientific module, evaluation or repair.

Usage: python -B analyze.py --out analysis01
The output must be a new direct child of this script's directory. The old
failed R1/C slot is never imported to complete a four-arm comparison.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE = HERE.parent / "resume_execution01"
EXPECTED = [("base__R1", a) for a in ("HEFT", "SINGLE", "PAIR")] + [
    ("base__R3", a) for a in ("PAIR", "SINGLE", "HEFT", "C")]


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8-sig"))


def interval(value):
    if isinstance(value, dict):
        value = [value["lower"], value["upper"]]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    lo, hi = (F(str(x)) for x in value)
    if lo > hi:
        raise ValueError("Reversed archived interval")
    return [str(lo), str(hi)]


def relation(left, right):
    if left is None or right is None:
        return "MISSING_ELIGIBLE_PAIR"
    if F(left[1]) < F(right[0]):
        return "LEFT_STRICTLY_LOWER"
    if F(right[1]) < F(left[0]):
        return "RIGHT_STRICTLY_LOWER"
    return "OVERLAPPING_INTERVALS"


def semantic(candidate, instance):
    """Normalize row order and rational spelling, without recomputing legality."""
    if not candidate:
        return None
    identifiers = {s["id"]: {r["id"]: r["shared_stage_id"]
        for r in s["stage_instances"]} for s in instance["scenarios"]}
    rows, deployment, opps, starts = {}, {}, {}, {}
    for sid, entries in sorted(candidate["scenes"].items()):
        normalized = []
        for entry in sorted(entries, key=lambda v: v["stage_id"]):
            iid = entry["stage_id"]
            shared = identifiers[sid][iid]
            unit = entry["unit"]
            if shared in deployment and deployment[shared] != unit:
                raise ValueError("Archived shared deployment contradicts itself")
            deployment[shared] = unit
            normalized.append({"stage_id": iid, "unit": unit,
                "opp": entry["opp"], "start_ms": str(F(entry["start_ms"]))})
        rows[sid] = normalized
        opps[sid] = {r["stage_id"]: r["opp"] for r in normalized}
        starts[sid] = {r["stage_id"]: r["start_ms"] for r in normalized}
    return {"candidate_sha256": canonical(candidate),
        "semantic_sha256": canonical(rows), "deployment_sha256": canonical(deployment),
        "opp_sha256": canonical(opps), "starts_sha256": canonical(starts),
        "shared_deployment": deployment, "scenes": rows}


def gain(before, after):
    if before is None or after is None:
        return None
    # Arithmetic on archived enclosures only; no new energy computation.
    lo, hi = F(before[0]) - F(after[1]), F(before[1]) - F(after[0])
    return {"difference_J": [str(lo), str(hi)],
        "strictly_improved": lo > 0,
        "conservative_percent": str(100 * lo / F(before[1])) if F(before[1]) > 0 else None}


def initial_record(arm, result, instance):
    if arm == "HEFT":
        complete = (result.get("reason") == "DECLARED_SEARCH_COMPLETED" and
            (result.get("search") or {}).get("status") == "BOUNDED_SEARCH_COMPLETED")
        candidate, receipt = result.get("safe_candidate"), result.get("evaluation") or {}
        label = "same-call full HEFT best; never search.local_base_candidate"
    elif arm in ("SINGLE", "PAIR"):
        snap = result.get("initial_safe_snapshot")
        complete = (isinstance(snap, dict) and snap.get("accepted_safe") is True and
            snap.get("phase") == "initialization" and
            (result.get("initialization") or {}).get("status") == "BOUNDED_SEARCH_COMPLETED")
        if snap:
            candidate, receipt = snap["candidate"], snap["receipt"]
        else:
            observed = [r for r in result.get("evaluations", []) if
                r.get("phase") == "initialization" and r.get("accepted_safe") is True]
            best = min(observed, key=lambda r: F(r["energy"]["upper"])) if observed else {}
            candidate, receipt = best.get("candidate"), best.get("receipt") or {}
        label = "same-call HEFT best frozen" if complete else "partial initialization best only"
    else:
        condition = result.get("condition") or {}
        candidate, receipt = condition.get("seed_candidate"), condition.get("seed_receipt") or {}
        complete, label = bool(candidate and receipt), "original C constructor; not HEFT initialization"
    return {"complete": complete, "kind": label,
        "initialization_return_status": (result.get("initialization") or result.get("search") or {}).get("status"),
        "energy_J": interval(receipt.get("weighted_energy_J")),
        "formed_at_s": receipt.get("completed_at_elapsed_s"),
        "candidate": semantic(candidate, instance) if candidate else None}


def component_totals(receipt, instance):
    """Weight already archived scene component enclosures, no physics call."""
    totals = {}
    weights = {s["id"]: F(s["weight"]) for s in instance["scenarios"]}
    for sid, scene in (receipt.get("scenes") or {}).items():
        for component, value in (scene.get("energy_components_J") or {}).items():
            iv = interval(value)
            if iv is None:
                raise ValueError("Archived energy component interval required")
            sums = totals.setdefault(component, [F(0), F(0)])
            sums[0] += weights[sid] * F(iv[0])
            sums[1] += weights[sid] * F(iv[1])
    return {k: [str(x) for x in v] for k, v in totals.items()}


def resource_order(candidate, sid, unit):
    return [r["stage_id"] for r in sorted(candidate["scenes"][sid],
        key=lambda r: (F(r["start_ms"]), r["stage_id"])) if r["unit"] == unit]


def pair_improvement_evidence(pair_result, single_result, instance):
    """Explain accepted graph changes using archived rows only."""
    initial = pair_result.get("initial_safe_snapshot") or {}
    observations = pair_result.get("evaluations") or []
    known = {r["candidate_sha256"]: r for r in observations if r.get("candidate_sha256")}
    if initial:
        known[initial["candidate_sha256"]] = initial
    single_trials = [r for r in single_result.get("evaluations", []) if r.get("phase") == "refinement"]
    single_semantics = {semantic(r["candidate"], instance)["semantic_sha256"] for r in single_trials}
    rows = []
    for proposal in pair_result.get("graph_proposals", []):
        if proposal.get("strict_accepted") is not True:
            continue
        base = known.get(proposal.get("base_candidate_sha256"))
        after = known.get(proposal.get("candidate_sha256"))
        if not base or not after:
            rows.append({"error": "ACCEPTED_PROPOSAL_ARCHIVE_ROW_MISSING", "proposal": proposal})
            continue
        left, right = base["candidate"], after["candidate"]
        changes = []
        for sid, entries in left["scenes"].items():
            before_rows = {r["stage_id"]: r for r in entries}
            after_rows = {r["stage_id"]: r for r in right["scenes"][sid]}
            for iid in sorted(before_rows):
                old, new = before_rows[iid], after_rows[iid]
                changed = {k: {"before": old[k], "after": new[k]}
                    for k in ("unit", "opp", "start_ms")
                    if (F(old[k]) != F(new[k]) if k == "start_ms" else old[k] != new[k])}
                if changed:
                    changes.append({"scene_id": sid, "stage_id": iid, "changed": changed})
        before_components = component_totals(base["receipt"], instance)
        after_components = component_totals(after["receipt"], instance)
        component_differences = {k: gain(before_components[k], after_components[k])
            for k in before_components if k in after_components}
        sid = proposal["scene_id"]
        units = sorted({r["unit"] for r in left["scenes"][sid]})
        orders = {}
        for unit in units:
            old, new = resource_order(left, sid, unit), resource_order(right, sid, unit)
            if old != new:
                seen_orders = sorted({tuple(resource_order(r["candidate"], sid, unit)) for r in single_trials})
                orders[unit] = {"before": old, "after": new,
                    "SINGLE_archived_refinement_orders": [list(order) for order in seen_orders],
                    "reversed_order_observed_in_SINGLE": tuple(new) in seen_orders}
        rows.append({"scene_id": sid, "selected_stages": proposal.get("selected_stages"),
            "orientation": proposal.get("orientation"), "template": proposal.get("template"),
            "proposed_at_s": proposal.get("proposed_at_s"),
            "receipt_formed_at_s": after["receipt"].get("completed_at_elapsed_s"),
            "candidate_semantic_sha256": semantic(right, instance)["semantic_sha256"],
            "same_semantics_was_evaluated_by_SINGLE": semantic(right, instance)["semantic_sha256"] in single_semantics,
            "changes": changes, "resource_orders_changed": orders,
            "weighted_components_before_J": before_components,
            "weighted_components_after_J": after_components,
            "weighted_component_decreases_J": component_differences,
            "complete_gain": gain(interval(base["energy"]), interval(after["energy"])),
            "evidence_scope": "archive comparisons only; SINGLE absence is not global impossibility"})
    return rows


def c_phases(result):
    records, updates = [], result.get("global_updates") or []
    for phase in result.get("phases") or []:
        index = phase["phase_index"]
        applicable = [u for u in updates if u.get("phase_index", 1) <= index]
        last = applicable[-1] if applicable else {}
        scenes = []
        for sid, record in phase.get("scenes", {}).items():
            model = record.get("model_summary") or {}
            scenes.append({"scene_id": sid, "reason": record.get("reason"),
                "model_completed_at_s": record.get("model_completed_at_s"),
                "search_started_at_s": record.get("search_started_at_s"),
                "search_returned_at_s": record.get("search_returned_at_s"),
                "model": {k: model.get(k) for k in ("options", "variables", "binary_variables", "rows")},
                "solver_summary": {k: (record.get("solver_result") or {}).get(k) for k in
                    ("state", "reason", "elapsed_s", "exitflag", "solver_reported", "first_safe_at_s")},
                "preprocessing": record.get("preprocessing")})
        start, end = phase.get("started_at_s"), phase.get("completed_at_s")
        records.append({"phase_index": index, "name": phase.get("name"),
            "started_at_s": start, "completed_at_s": end,
            "wall_s": end - start if start is not None and end is not None else None,
            "complete_energy_after_J": interval(last.get("weighted_energy_J")),
            "anchor_sha256": (phase.get("condition") or {}).get("warm_candidate_sha256"),
            "opened_by_scene": (phase.get("condition") or {}).get("opened_by_scene"),
            "scenes": scenes})
    return records


def analyze(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("Output must be a new direct child of resume_analysis01")
    terminal_path = source / "batch_terminal.json"
    if not terminal_path.is_file():
        raise ValueError("Wait for the actual batch terminal before analysis")
    hashes = {}

    def get(path, optional=False):
        if optional and not path.is_file():
            return {}
        value = read(path)
        hashes[str(path.relative_to(source)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
        return value

    declaration = get(source / "declaration.json")
    terminal = get(terminal_path)
    slots = declaration["slots"]
    if [(s["case_id"], s["arm"]) for s in slots] != EXPECTED:
        raise ValueError("Only the declared seven unstarted continuation slots are supported")
    rows, raw = [], {}
    for slot in slots:
        folder = source / "calls" / slot["slot_id"]
        result = get(folder / "result.json", True)
        audit = get(folder / "audit.json", True)
        post = get(folder / "post_return.json", True)
        done = get(folder / "terminal.json", True)
        identity = get(folder / "worker_identity.json", True)
        returned = get(folder / "worker_return.json", True)
        supervisor = get(folder / "supervisor_method.json", True)
        consumed = (folder / "slot.claim.json").is_file()
        binding_errors = []
        if result:
            result_hash = hashes[str((folder / "result.json").relative_to(source)).replace("\\", "/")]
            if audit.get("result_sha256") != result_hash:
                binding_errors.append("AUDIT_RESULT_HASH")
            if post and post.get("result_after_sha256") != result_hash:
                binding_errors.append("POST_RESULT_HASH")
            if post and post.get("candidate_sha256") != audit.get("candidate_sha256"):
                binding_errors.append("POST_CANDIDATE_HASH")
        eligible = (not binding_errors and audit.get("eligible_for_post") is True and
            post.get("passed") is True and post.get("energy_reproduced") is True and
            done.get("post_passed") is True and done.get("continue_allowed") is True)
        arm = slot["arm"]
        timing = result.get("timing") or {}
        phases = timing.get("phases_exclusive_s") or {}
        instance = get(folder / "input_instance.json", True)
        raw[(slot["case_id"], arm)] = (result, instance)
        initialization = initial_record(arm, result, instance) if result and instance else None
        own_interval = interval(audit.get("admitted_interval")) if eligible else None
        initial_interval = initialization.get("energy_J") if initialization else None
        evaluations = result.get("evaluations") or []
        if arm == "C":
            strict_times = [u.get("committed_at_s") for u in result.get("global_updates", [])
                if initial_interval and u.get("weighted_energy_J") and
                F(u["weighted_energy_J"][1]) < F(initial_interval[0]) and u.get("committed_at_s") is not None]
            first_strict = min(strict_times) if strict_times else None
        else:
            first_strict = result.get("first_graph_strict_improvement_at_s")
        status = ("NOT_STARTED" if not consumed else "COMPLETE_SAFE_POST_PASSED" if eligible else
            "NORMAL_NO_SAFE" if audit.get("normal_no_safe") and done.get("continue_allowed") else
            "TECHNICAL_OR_INCOMPLETE")
        rows.append({"slot_id": slot["slot_id"], "case_id": slot["case_id"], "arm": arm,
            "consumed": consumed, "status": status, "classification": audit.get("classification"),
            "reason": result.get("reason"), "audit_errors": audit.get("errors"),
            "binding_errors": binding_errors, "input_sha256": audit.get("input_sha256"),
            "config_sha256": audit.get("config_sha256"),
            "source_manifest_sha256": canonical(identity["source_sha256"]) if identity.get("source_sha256") else None,
            "raw_result_sha256": audit.get("result_sha256"),
            "final_candidate": semantic(result.get("safe_candidate"), instance) if result and instance else None,
            "comparison_energy_J": own_interval, "reported_U_J": result.get("safe_upper_bound_J"),
            "initialization": initialization,
            "gain_from_own_initialization": gain(initial_interval, own_interval),
            "first_SAFE_s": result.get("first_safe_at_s"),
            "first_strict_after_initialization_s": first_strict,
            "method_elapsed_s": timing.get("method_elapsed_s"),
            "worker_root_to_return_s": returned.get("method_root_elapsed_s"),
            "process_wall_s": supervisor.get("process_wall_seconds"),
            "post_elapsed_s": post.get("evaluation_elapsed_s"),
            "MATLAB_startup_s": phases.get("solver_startup"),
            "phase_exclusive_s": phases, "graph_proposals": len(result.get("graph_proposals") or []),
            "graph_strict_improvements": result.get("graph_strict_improvements"),
            "evaluations_recorded": len(evaluations), "cache_hits": result.get("cache_hits"),
            "initialization_evaluations": sum(r.get("phase") == "initialization" for r in evaluations),
            "refinement_evaluations": sum(r.get("phase") == "refinement" for r in evaluations),
            "C_phases": c_phases(result) if arm == "C" else [],
            "safe_updates": result.get("global_updates") if arm == "C" else result.get("events"),
            "independent_optimality_proved": False})
    attribution = []
    comparisons = []
    for case in ("base__R1", "base__R3"):
        by_arm = {r["arm"]: r for r in rows if r["case_id"] == case}
        for arm in ("SINGLE", "PAIR"):
            graph, baseline = by_arm[arm], by_arm["HEFT"]
            gi, hi = graph["initialization"] or {}, baseline["initialization"] or {}
            gc, hc = gi.get("candidate") or {}, hi.get("candidate") or {}
            same_semantic = bool(gc.get("semantic_sha256") and gc.get("semantic_sha256") == hc.get("semantic_sha256"))
            same_energy = bool(gi.get("energy_J") and gi.get("energy_J") == hi.get("energy_J"))
            all_complete = gi.get("complete") is True and hi.get("complete") is True
            source_same = bool(graph["source_manifest_sha256"] and graph["source_manifest_sha256"] == baseline["source_manifest_sha256"])
            valid = all(r["status"] == "COMPLETE_SAFE_POST_PASSED" for r in (graph, baseline))
            attribution.append({"case_id": case, "graph_arm": arm,
                "both_initializations_complete": all_complete, "same_best_SAFE_semantics": same_semantic,
                "same_best_SAFE_energy_interval": same_energy,
                "same_best_SAFE_energy_overlap": relation(gi.get("energy_J"), hi.get("energy_J")) == "OVERLAPPING_INTERVALS",
                "same_source_manifest": source_same,
                "same_start_comparison_supported": valid and all_complete and same_semantic and same_energy and source_same,
                "scope": "independent same-call initialization, never borrowed across methods"})
        keys = list(by_arm)
        for i, left in enumerate(keys):
            for right in keys[i + 1:]:
                comparisons.append({"case_id": case, "left": left, "right": right,
                    "relation": relation(by_arm[left]["comparison_energy_J"], by_arm[right]["comparison_energy_J"]),
                    "right_gain_vs_left": gain(by_arm[left]["comparison_energy_J"], by_arm[right]["comparison_energy_J"])})
    pair_explanations = {}
    for case in ("base__R1", "base__R3"):
        pair_result, instance = raw[(case, "PAIR")]
        single_result, _ = raw[(case, "SINGLE")]
        if pair_result and instance:
            pair_explanations[case] = pair_improvement_evidence(pair_result, single_result, instance)
    for name, expected in hashes.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Read source changed during archive analysis: " + name)
    facts = {"protocol": "K184-readonly-seven-slot-analysis-v1", "batch_terminal": terminal,
        "rows": rows, "initialization_attribution": attribution, "comparisons": comparisons,
        "accepted_pair_changes": pair_explanations,
        "initialization_completion_basis": "snapshot accepted_safe and phase initialization, plus returned HEFT status BOUNDED_SEARCH_COMPLETED; graph source freezes only after initializer returns and budget/context checks",
        "source_file_sha256": hashes, "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "research_calls": 0, "thermal_integrations": 0, "new_candidates_or_energy_evaluations": 0,
        "old_failed_R1_C_imported": False}
    output.mkdir()
    with (output / "facts.json").open("x", encoding="utf-8") as stream:
        json.dump(facts, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    def show(value, digits=6):
        return "—" if value is None else f"{float(F(str(value))):.{digits}f}"
    lines = ["# K.184：剩余七槽终态只读结果", "",
        "R1仅HEFT／SINGLE／PAIR；R3四法。旧R1/C启动故障不补成同轮结果。", "",
        "|问题|方法|状态|完整安全U/J|自身初始U/J|严格降低|方法/s|首SAFE/s|首严格改善/s|",
        "|---|---|---|---:|---:|---|---:|---:|---:|"]
    for r in rows:
        energy = r["comparison_energy_J"]
        init = (r["initialization"] or {}).get("energy_J")
        strict = (r["gain_from_own_initialization"] or {}).get("strictly_improved")
        lines.append("|" + "|".join([r["case_id"], r["arm"], r["status"], show(energy[1] if energy else None),
            show(init[1] if init else None), str(strict) if strict is not None else "—",
            show(r["method_elapsed_s"], 3), show(r["first_SAFE_s"], 3),
            show(r["first_strict_after_initialization_s"], 3)]) + "|")
    lines.extend(["", "初始化归因："])
    for a in attribution:
        lines.append(f"- {a['case_id']} {a['graph_arm']}：初始化均完成={a['both_initializations_complete']}；最佳SAFE语义一致={a['same_best_SAFE_semantics']}；区间完全一致={a['same_best_SAFE_energy_interval']}；可按同起点解释={a['same_start_comparison_supported']}。")
    lines.extend(["", "已接纳成对图变动："])
    for case, accepted in pair_explanations.items():
        if not accepted:
            lines.append(f"- {case}：未形成严格改善。")
        for row in accepted:
            change = row.get("complete_gain") or {}
            lo = (change.get("difference_J") or [None, None])[0]
            lines.append(f"- {case}：{row.get('orientation')}／{row.get('template')}，选中{row.get('selected_stages')}；严格下降下界{show(lo, 12)} J；同一完整方案曾在SINGLE中评价={row.get('same_semantics_was_evaluated_by_SINGLE')}。详细起点、设备／OPP和资源顺序、各能量分项差见facts.json。")
    lines.extend(["", "SINGLE／PAIR的初始项是各自独立HEFT过程的最佳完整SAFE；C是自己的构造初解，不能当成相同HEFT起点。未完成初始化或初始最佳方案不同，仅报告端到端结果，不把全部差异归因于图操作。",
        "", "首严格改善指超过自身完整初始能量区间的改善；HEFT单独运行未设置‘完成HEFT后的改进阶段’，该列为空。各题各方法一次，不作统计稳定性或全域最优结论。",
        "", "完整部署、工作点与起点语义hash、原C两阶段、计时、提案／复核／缓存数及原始证据文件hash见facts.json。本文只读归档并作有理数区间比较，无求解、热积分、候选复核或修复。"])
    with (output / "summary.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    return {"output": str(output), "rows": len(rows),
        "complete_safe_post_passed": sum(r["status"] == "COMPLETE_SAFE_POST_PASSED" for r in rows),
        "new_scientific_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=HERE / "analysis01")
    args = parser.parse_args()
    print(json.dumps(analyze(args.source, args.out), ensure_ascii=False))
