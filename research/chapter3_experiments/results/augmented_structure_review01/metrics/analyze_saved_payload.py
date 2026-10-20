"""Read existing K135 arrays/receipts only; never call repository code or a solver.

Outputs are new derived descriptions, not new performance/thermal results.
Run once. Exclusive output creation prevents overwriting either old or new records.
"""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import numpy as np
from scipy.io import loadmat
from scipy.sparse import issparse

OUT = Path(__file__).resolve().parent
SRC = OUT.parents[1] / "augmented_quality_pair01"
METHODS = ("old_n1", "augmented_all_opp_start")
SCENES = ("AB_offset_0ms", "AC_offset_0ms")

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def relative(path):
    return path.relative_to(SRC).as_posix()

def snapshot(paths):
    return {relative(p): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                          "size_bytes": p.stat().st_size} for p in paths}

def write_json(name, value):
    with (OUT / name).open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

def bounds_counts(data, n=None):
    lb, ub = data["lb"].ravel(), data["ub"].ravel()
    n = len(lb) if n is None else n
    lb, ub = lb[:n], ub[:n]
    # Serialized MAT uses MATLAB one-based intcon, per *.input.json.
    idx = data["intcon"].ravel().astype(int) - 1
    idx = np.unique(idx[idx < n])
    integer = np.zeros(n, dtype=bool)
    integer[idx] = True
    binary = integer & (lb >= 0) & (ub <= 1)
    fixed = lb == ub
    return {"variables": n, "integer_variables": int(integer.sum()),
            "binary_variables_from_intcon_and_bounds": int(binary.sum()),
            "general_integer_variables": int((integer & ~binary).sum()),
            "continuous_variables": int((~integer).sum()),
            "fixed_bound_columns": int(fixed.sum()),
            "fixed_integer_columns": int((fixed & integer).sum()),
            "fixed_continuous_columns": int((fixed & ~integer).sum()),
            "unfixed_binary_columns": int((binary & ~fixed).sum()),
            "continuous_bounded_0_1_columns": int(((~integer) & (lb >= 0) & (ub <= 1)).sum())}

def matrix_stats(data):
    a, ae = data["A"], data["Aeq"]
    values = a.data if issparse(a) else a.ravel()
    av = np.abs(values[values != 0])
    return {"inequality_rows": int(a.shape[0]), "equality_rows": int(ae.shape[0]),
            "total_rows": int(a.shape[0] + ae.shape[0]),
            "inequality_nonzeros": int(a.count_nonzero()),
            "equality_nonzeros": int(ae.count_nonzero()),
            "A_abs_nonzero_min": float(av.min()) if len(av) else None,
            "A_abs_nonzero_max": float(av.max()) if len(av) else None,
            "A_abs_nonzero_max_min_ratio": float(av.max() / av.min()) if len(av) else None}

def has_x(event):
    return "x" in event and np.asarray(event["x"]).size > 0

def same_float64_bits(a, b):
    a = np.ascontiguousarray(a, dtype=np.float64)
    b = np.ascontiguousarray(b, dtype=np.float64)
    return a.shape == b.shape and a.tobytes() == b.tobytes()

def main():
    names = ("facts.json", "counts.csv", "callback_candidates.csv", "hashes_before.json",
             "hashes_after.json", "summary.md")
    if any((OUT / name).exists() for name in names):
        raise FileExistsError("Derived outputs already exist; refusing overwrite")
    paths = set()
    for method in METHODS:
        base = SRC / method
        paths.add(base / "result.json")
        for i in range(2):
            paths.add(base / f"build_scene_{i:03d}.jsonl")
            req = f"request_{i + 1:06d}"
            for suffix in (".mat", ".input.json", ".response.json"):
                paths.add(base / "matlab" / (req + suffix))
            paths.update((base / "matlab").glob(req + ".event_*.json"))
            if method.startswith("augmented"):
                q = base / f"scene_{i}" / "augmented_requests" / req
                paths.update(q / name for name in ("labels.json", "mapping.json", "matrix_identities.json"))
    paths = sorted(paths)
    before = snapshot(paths)
    write_json("hashes_before.json", before)
    rows, callbacks, details = [], [], []
    for method in METHODS:
        base = SRC / method
        result = read_json(base / "result.json")
        for i, scene in enumerate(SCENES):
            saved = result["scenes"][scene]
            model = saved.get("model_summary", {})
            construction = saved.get("construction", {})
            req = f"request_{i + 1:06d}"
            matpath = base / "matlab" / (req + ".mat")
            data = loadmat(matpath, variable_names=["c", "A", "Aeq", "lb", "ub", "intcon", "x0"])
            row = {"method": method, "scene": scene, "request": req,
                   "original_variables": model.get("variables"), **bounds_counts(data), **matrix_stats(data),
                   "retained_options": model.get("options"),
                   "logical_binary_variables_recorded": model.get("logical_binary_variables"),
                   "events_recorded": construction.get("events_per_scene", {}).get(scene),
                   "control_intervals_recorded": construction.get("scene_control_intervals_begun", {}).get(scene),
                   "state_kernels_completed_recorded": construction.get("coefficient_state_kernels_completed"),
                   "thermal_conditional_row_calls_recorded": construction.get("construction_components", {}).get("thermal_conditional_rows", {}).get("calls"),
                   "original_inequality_rows": model.get("rows"),
                   "original_inequality_nonzeros": construction.get("nonzeros_in_rows"),
                   "added_continuous_complements": 0, "added_link_equalities": 0,
                   "physical_rows_rewritten": None, "physical_rows_retained": None,
                   "condition_gate_w_columns_recorded": None}
            extra = {"source_mat": relative(matpath),
                     "metadata_locator": relative(base / "result.json") + f"#/scenes/{scene}/model_summary",
                     "missing_fields_are_null": True,
                     "original_coefficient_scale": "unavailable separately: original new-model A not archived as a MAT" if method.startswith("augmented") else "same as native MAT",
                     "fixed_bound_columns_included_in_variables": True}
            if method.startswith("augmented"):
                q = base / f"scene_{i}" / "augmented_requests" / req
                mapping = read_json(q / "mapping.json")
                labels = read_json(q / "labels.json")
                ids = read_json(q / "matrix_identities.json")
                name_counts = dict(Counter(n.split(":", 1)[0] for n in labels["names"]))
                tag_counts = dict(Counter(t.split(":", 1)[0] for t in labels["row_tags"]))
                row.update({"original_variables": mapping["original_n"],
                            "added_continuous_complements": mapping["new_variables"],
                            "added_link_equalities": mapping["new_link_equalities"],
                            "physical_rows_rewritten": mapping["physical_rows_rewritten"],
                            "physical_rows_retained": len(mapping.get("exact_row_selection", {}).get("retained_nonrepresentable_physical_rows", [])),
                            "condition_gate_w_columns_recorded": name_counts.get("w")})
                extra.update({"original_bounds_counts_from_stored_unchanged_prefix": bounds_counts(data, mapping["original_n"]),
                              "original_structure_from_stored_identities": {k: ids["original"][k] for k in ("A", "Aeq")},
                              "variable_prefix_counts_from_original_labels": name_counts,
                              "row_tag_counts_from_original_labels": tag_counts,
                              "labels_locator": relative(q / "labels.json"),
                              "mapping_locator": relative(q / "mapping.json"),
                              "exact_row_selection_fields": {k: len(v) if isinstance(v, list) else v for k, v in mapping.get("exact_row_selection", {}).items()}})
            response = read_json(base / "matlab" / (req + ".response.json"))
            events = [(p, read_json(p)) for p in sorted((base / "matlab").glob(req + ".event_*.json"))]
            root = [(p, e) for p, e in events if e.get("values", {}).get("phase") == "rootlp"]
            row.update({"rootlp_first_native_time_s": root[0][1]["values"].get("time") if root else None,
                        "rootlp_first_fval_solver_reported": root[0][1]["values"].get("fval") if root else None,
                        "native_call_s": response.get("phase_seconds", {}).get("intlinprog_call"),
                        "native_max_time_s": response.get("solver_max_time_s_declared"),
                        "response_numfeaspoints": response.get("output", {}).get("numfeaspoints"),
                        "response_numnodes": response.get("output", {}).get("numnodes"),
                        "exitflag": response.get("exitflag"), "callback_nonempty_x_publications": 0})
            for path, event in events:
                if event.get("kind") == "callback" and has_x(event):
                    x = np.asarray(event["x"]).ravel()
                    x0 = data["x0"].ravel()
                    n = row["original_variables"]
                    same = len(x) >= n and same_float64_bits(x[:n], x0[:n])
                    callbacks.append({"method": method, "scene": scene, "event_source": relative(path),
                                      "native_time_s": event.get("values", {}).get("time"),
                                      "fval_solver_reported": event.get("values", {}).get("fval"),
                                      "original_prefix_bit_equal_x0": bool(same), "published_x_length": len(x)})
                    row["callback_nonempty_x_publications"] += 1
            extra["native_options"] = {k: response.get("options", {}).get(k) for k in ("IntegerPreprocess", "LPPreprocess", "CutMaxIterations", "RootLPAlgorithm", "ConstraintTolerance", "IntegerTolerance")}
            extra["callback_count_note"] = "Use immutable event x, not response callback summaries. Empty/root LP vectors are not integer candidate publications."
            extra["response_final_original_prefix_bit_equal_x0"] = bool(same_float64_bits(np.asarray(response["x"]).ravel()[:row["original_variables"]], data["x0"].ravel()[:row["original_variables"]])) if has_x(response) else None
            extra["response_final_vector_length"] = int(np.asarray(response.get("x", [])).size)
            details.append({"method": method, "scene": scene, **extra})
            rows.append(row)
    after = snapshot(paths)
    write_json("hashes_after.json", after)
    assert before == after, "An inspected original changed during read-only analysis"
    facts = {"status": "ANALYZED", "research_calls": 0, "solver_calls": 0, "model_builds": 0,
             "heat_evaluations": 0, "source_root": str(SRC), "original_files_checked": len(paths),
             "original_hashes_unchanged": before == after,
             "scope": "K135 existing payload arrays and stored metadata only; no new performance outcome",
             "rows": rows, "nonempty_callback_candidates": callbacks, "details": details,
             "limitations": ["No native LP completion inferred from a missing rootlp event.",
                             "Counts retain fixed-bound columns; logical binaries include relaxed auxiliaries and are not intcon counts.",
                             "New original A matrix coefficients are not separately recomputed or reconstructed.",
                             "Structure and timings are associated observations, not a single-factor causal attribution.",
                             "No claim that shorter proposed future slices retain the observed late improvements."]}
    write_json("facts.json", facts)
    for name, values in (("counts.csv", rows), ("callback_candidates.csv", callbacks)):
        with (OUT / name).open("x", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    lines = ["# K136：已有载荷结构与原生事件只读核查", "",
             "仅分析K135已保存数组和回执；零求解、构模、热评价。新文件为派生统计，不是新性能结果。", "",
             "| 方法／场景 | 原→发送变量 | 整数／连续 | 固定界列 | 不等式＋等式 | 非零元A＋Aeq | options | 事件／区间 | rootlp原生自报秒 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"|{r['method']}／{r['scene'][:2]}|{r['original_variables']}→{r['variables']}|{r['integer_variables']}／{r['continuous_variables']}|{r['fixed_bound_columns']}|{r['inequality_rows']}＋{r['equality_rows']}|{r['inequality_nonzeros']}＋{r['equality_nonzeros']}|{r['retained_options']}|{r['events_recorded']}／{r['control_intervals_recorded']}|{r['rootlp_first_native_time_s'] if r['rootlp_first_native_time_s'] is not None else '未发布'}|")
    lines += ["", "上述整数全为[0,1]界整数，普通整数为0。固定界列仍包含在变量总数中。新版补变量均连续，整数坐标保持；新版AB／AC分别新增2400／7196个补变量及链接等式。logical_binary_variables为逻辑标签统计，不能等同于求解器整数维数。", "",
              "新版条件门w为2400／7196列；原标签thermal_propagation与complete_energy条件行见facts.json细分。AB改写24000行、保留非无损物理行0；AC改写71958行、保留2行。旧版无归档labels，条件行类别计数留空；其热条件构造调用1311／1481已原样登记，不能冒充逐行标签核计。", "",
              "| 方法／场景 | 非空callback事件 | 原生time／s | solver fval | 原前缀与本次x0逐bit相同 |", "|---|---|---:|---:|---|"]
    for c in callbacks:
        lines.append(f"|{c['method']}／{c['scene'][:2]}|{Path(c['event_source']).name}|{c['native_time_s']}|{c['fval_solver_reported']}|{c['original_prefix_bit_equal_x0']}|")
    lines += ["", "旧AB首次异于种子的发布为48.9199128秒，旧AC为60.2881668秒；因此把60秒直接对半分配不保证保留原改善。AC的后者超过声明MaxTime，仍是原300秒方法证据窗内保存的回执，不能改称严格60秒内形成。新版AB最终原前缀仍为x0；新版AC无非空候选发布，缺rootlp事件不能填0、认定完成或推断无解。", "",
              "发送矩阵系数绝对值范围、固定界类型、原生实际耗时与声明限额见counts.csv；新版原矩阵系数范围未单独存MAT，本次不重建。连续补变量满足v=1−w，精确算术下只是坐标扩展，不能声称增强LP松弛；本表也不能把rootlp耗时差单因果归于变量／条件行增多。", "",
              f"原始输入范围限定{len(paths)}个实际读取文件，SHA-256与大小前后完全相同；见hashes_before.json／hashes_after.json。未改写MAT或历史输出。", "",
              "出处：`augmented_quality_pair01/<method>/matlab/request_000001.mat`为AB，`request_000002.mat`为AC；对应`.response.json`登记原生实际耗时、options、最终向量；`.event_*.json`登记实际发布向量与time。`<method>/result.json#/scenes/<scene>/model_summary`与`construction`给出options、逻辑标签、事件／区间及核计。新版`scene_0/augmented_requests/request_000001`与`scene_1/augmented_requests/request_000002`中的mapping／labels／matrix_identities给出改写与原矩阵身份。全部相对路径、字段定位与前后哈希见facts.json及hashes文件。"]
    with (OUT / "summary.md").open("x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({"status": "ANALYZED", "files_checked": len(paths), "hashes_unchanged": True,
                      "count_rows": len(rows), "nonempty_callbacks": len(callbacks)}))

if __name__ == "__main__":
    main()
