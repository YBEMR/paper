"""Audit each endpoint against its own launch environment and construct A–E paired tables."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import median
import sys
import tempfile

from attempt_inventory import attempts
from recover_26300 import RECOVERY, validate_recovery, verified_receipts
from release_continuation import group_name, interval_text, mechanism_summary
from windows_26300 import CHECKPOINT, CHECKPOINT_SHA, STAGE, SUBJECT, audit, cross, digest, require


def evidence_archive(run, repo, out):
    sys.path.insert(0, str(repo / "research/chapter3_final_evaluation/analysis"))
    import archive_batch as codec
    codec.OUT, codec.DEST = run, out
    out.mkdir()
    groups = defaultdict(list)
    for stage in (STAGE, RECOVERY):
        for path in sorted((run / stage).rglob("*")):
            if path.is_file():
                groups[group_name(path.relative_to(run))].append(path)
    manifest = {}
    for group, files in sorted(groups.items()):
        manifest[group] = codec.pack(group, files)
        codec.verify_archive(group, manifest[group])
    cross.write(out / "manifest.json", manifest)
    return sum(g["files"] for g in manifest.values())


def checkpoint_rows(arms, tags):
    for n in range(1, min(len(a["mechanism"]) for a in arms) + 1):
        vals = [audit.checkpoint(a, rounds=n)["J"] for a in arms]
        yield checkpoint_delta(tags, "round", n, vals)
    for seconds in (30, 60, 120, 300, 600):
        scores = [audit.checkpoint(a, t=seconds) for a in arms]
        if any(s is None for s in scores):
            yield dict(**tags, axis="config_elapsed_s", checkpoint=seconds, status="CENSORED")
        else:
            yield checkpoint_delta(tags, "config_elapsed_s", seconds, [s["J"] for s in scores])


def checkpoint_delta(tags, axis, checkpoint, vals):
    a, b, c, d = vals
    return dict(**tags, axis=axis, checkpoint=checkpoint, status="OBSERVED",
                A_B_mJ=1000*(a-b), C_D_mJ=1000*(c-d), interaction_mJ=1000*(a-b-c+d))


def summarize(pairs):
    rows = []
    for case in cross.CASES:
        group = [r for r in pairs if r["case"] == case]
        row = dict(case=case, registered_pairs=3, valid_pairs=len(group),
                   same_build_CD_pairs=sum(r["C_build"] == r["D_build"] for r in group))
        if group:
            for phase in ("configuration", "final"):
                for contrast in ("A_B", "C_D", "A_C", "B_D", "interaction"):
                    name = f"{phase}_{contrast}_mJ"
                    values = [r[name] for r in group]
                    row.update({name+"_median": median(values), name+"_min": min(values), name+"_max": max(values)})
            values = [r["final_D_E_mJ"] for r in group]
            row.update(final_D_E_mJ_median=median(values), final_D_E_mJ_min=min(values), final_D_E_mJ_max=max(values))
        rows.append(row)
    return rows


def report(out, state, pairs, physical):
    count = len(pairs)
    wins = {key: sum(r["final_"+key+"_verdict"] == "A_HIGHER" for r in pairs)
            for key in ("A_C", "B_D", "C_D")}
    matches = [r for r in audit.csvread(out / "matched_rounds.csv") if r["pair"] == "CD"]
    outside = [r for r in matches if r["realized_outside_ordinary"]]
    exact = [r for r in outside if r["ordinary_solver"] == r["feedback_solver"] == "EXACT_REFERENCE"]
    mechanism_note = [f"在 {len(matches)} 个同前态、同目标、同规模的 C/D 匹配轮次中，"
                      f"反馈在 {len(outside)} 轮实际改动了普通邻域以外的补偿请求。"]
    if exact:
        r = exact[0]
        mechanism_note.append(f"例如 {r['case']} 种子 {r['seed']} 第 {r['round']} 轮，两侧都精确完成各自邻域的参考目标搜索。"
                              f"反馈改动了普通邻域以外的请求 {r['realized_outside_ordinary']}，"
                              f"该轮普通邻域的轮末 SAFE 能耗减去反馈的轮末 SAFE 能耗为 {float(r['delta_mJ']):.4f} mJ。"
                              "这项比较只覆盖该轮搜索的两个邻域。")
    lines = ["# 第四章 A–E 交叉验证", "",
             f"四个工况、三个种子共登记 24 个 C/D 单元。本次核实 {state['audited_CD']}/24 个 C/D 终点和 {len(pairs)}/12 对结果，另核实 24 个历史 A/B 终点与四个确定性 E 参照。", "",
             "A、B 采用第三章初解，C、D 采用第四章容量规划初解。A、C 使用普通邻域，B、D 使用关键区间反馈。E 使用第四章 ThermalUnion，每个工况复用一个经认证的终点。", "",
             f"固定普通邻域后，换用第四章容量规划初解（Q4）在 {wins['A_C']}/{count} 个配对中降低了最终认证能耗。"
             f"固定关键区间反馈后，换用 Q4 在 {wins['B_D']}/{count} 个配对中降低了最终认证能耗。"
             f"从同一 Q4 初解出发，反馈在 {wins['C_D']}/{count} 个配对中优于普通邻域，收益大小随工况变化。", "",
             "## 同种子的最终能耗差", "",
             "单位为 mJ。各列为工况内有效配对的中位数及范围。正的 A−B 或 C−D 表示反馈方法更省电，负的 D−E 表示 D 更省电。", "",
             "| 工况 | 配对 | A−B | C−D | A−C | B−D | D−E |", "|---|---:|---:|---:|---:|---:|---:|"]
    for case in cross.CASES:
        rows = [r for r in pairs if r["case"] == case]
        vals = [interval_text(rows, "final_"+key+"_mJ") if rows else "—" for key in ("A_B", "C_D", "A_C", "B_D", "D_E")]
        lines.append("| " + " | ".join([case, f"{len(rows)}/3", *vals]) + " |")
    lines += ["", "## 初解与反馈分别改变了多少能耗", "",
              "A−C 固定普通邻域，B−D 固定反馈邻域。两者为正时，换用 Q4 初解后最终能耗下降。"
              "交互差为 (A−B)−(C−D)，每个种子先作差，再在工况内取中位数。正值表示反馈在第三章初解上的收益更大，负值表示反馈在 Q4 上的收益更大。",
              "", "| 工况 | Q4 使普通邻域终点更省电 | Q4 使反馈终点更省电 | 配置阶段交互差中位数（mJ） | 最终交互差中位数（mJ） |",
              "|---|---:|---:|---:|---:|"]
    for case in cross.CASES:
        rows = [r for r in pairs if r["case"] == case]
        if not rows:
            lines.append(f"| {case} | — | — | — | — |")
            continue
        count = len(rows)
        ac = sum(r["final_A_C_verdict"] == "A_HIGHER" for r in rows)
        bd = sum(r["final_B_D_verdict"] == "A_HIGHER" for r in rows)
        interaction = [median(r[phase + "_interaction_mJ"] for r in rows) for phase in ("configuration", "final")]
        lines.append(f"| {case} | {ac}/{count} | {bd}/{count} | {interaction[0]:.4f} | {interaction[1]:.4f} |")
    lines += ["", "各工况只有三个登记种子。表中次数按两端认证区间可区分的方向统计，区间重叠时不计入节能次数。"
              "固定初解的独立检查发现，F1 同一组 69 个单请求节能动作在第三章初解上全部产生虚拟超期，在 Q4 上全部满足虚拟期限。"
              "F2 的 60 个共同动作中，引起超期的动作则从 0 个增加到 24 个。"
              "这些结果说明初解会改变反馈可介入的机会，具体节能量取决于后续限时搜索和认证终点。[逐动作核对](../fixed_initial/README.md)"]
    lines += ["", "## 系统版本与配对", "",
              "续跑使用同一台 Windows 实验机，系统内部版本由 26200 更新为 26300。Python、六项依赖、76 份冻结文件、200 个求解器运行文件和物理核顺序复核一致。26300 批次独立通过两臂预检，重新生成其使用的共享 Q4 初解池。", "",
              "| C / D 内部版本 | 有效配对 | D 更省电 | C 更省电 | 认证区间重叠 |", "|---|---:|---:|---:|---:|"]
    for builds in sorted({(r["C_build"], r["D_build"]) for r in pairs}):
        rows = [r for r in pairs if (r["C_build"], r["D_build"]) == builds]
        verdict = Counter(r["final_C_D_verdict"] for r in rows)
        lines.append(f"| {builds[0]} / {builds[1]} | {len(rows)} | {verdict['A_HIGHER']} | {verdict['B_HIGHER']} | {verdict['INTERVAL_OVERLAP']} |")
    mixed = [f"{r['case']} 种子 {r['seed']}（C 为 {r['C_build']}，D 为 {r['D_build']}）" for r in pairs if r["C_build"] != r["D_build"]]
    de = Counter(r["final_D_E_verdict"] for r in pairs)
    lines += ["", "跨版本的 C/D 配对为 " + "、".join(mixed) + "。" if mixed else "当前有效 C/D 配对均为同版本。",
              "系统变化可能影响限时搜索的轨迹和终点。A/B 来自原批次，E 缺少本次同机计时。各组的时间记录用于描述运行过程。", "",
              f"D 低于 E 的有 {de['B_HIGHER']} 对，高于 E 的有 {de['A_HIGHER']} 对，认证区间重叠 {de['INTERVAL_OVERLAP']} 对。", "",
              "[逐种子结果及认证区间](paired.csv) · [各工况的配置与最终交互差](paired_summary.csv) · [分版本终点与证书核对](inventory.csv)", "",
              *mechanism_summary(out, pairs, cross.CASES),
              "".join(mechanism_note), "",
              "配置阶段按共同轮次和 30、60、120、300、600 秒检查点比较。在最后有记录的轮次之后，超出的时间检查点记为截尾。[共同检查点](common_checkpoints.csv) · [固定初解的目标与超期分层](../fixed_initial/README.md)", "",
              "## 计费与证据", ""]
    for build in ("26200", "26300"):
        records = [r for r in physical if r["windows_build"] == build]
        good = [r for r in records if r["status"] == "COMPLETE"]
        lost = [r for r in records if r["status"] == "NO_RECEIPT"]
        lines.append(f"- Windows {build} 有 {len(records)} 次正式启动，{len(good)} 份完成回执累计计费 {sum(r['charged_s'] for r in good):.2f} 秒，"
                     f"{len(lost)} 次无回执中断已记录至少 {sum(r['last_recorded_s'] for r in lost):.2f} 秒。")
    lines += ["", "每个正式单元的 900 秒上限包括本版本该工况共享初解构造的实测用时。中断、预检和初解构造单独保留。离线核对使用已存储的计划、证书和每轮接受记录。", "",
              f"本批 {state['new_raw_files']} 个原始文件均经逐字节还原核对。"
              " [26300 分片清单](archive/manifest.json) · [26200 原始证据](../checkpoints/windows_26200/README.md) · [实际启动记录](attempts.csv) · [审计结果](audit.json)"]
    if state["recovery_roster"]:
        lines += ["", "## 中断与补测", "",
                  "26300 原批次截止后，同时缺少结果和回执的位置按事先登记的规则单独补测。"
                  + "原批次缺少终点 " + "、".join(state["pre_recovery_missing"]) + "。"
                  + "补测获得正式终点 " + str(len(state["recovered"])) + " 个。",
                  "", "补测前可用 " + str(state["pre_recovery_pairs"]) + " 对。"
                  + "[补测前按工况汇总](paired_summary_before_recovery.csv) · [补测记录规则](../recovery_protocol.md)"]
    if state["missing"]:
        lines += ["", "尚缺完整终点的登记单元为 " + "、".join(state["missing"]) + "。"]
    (out / "README.md").write_text("\n".join(lines)+"\n", encoding="utf8", newline="\n")


def analyze(repo, run, out):
    old = run / "continuation_04/formal"
    stage = run / STAGE
    new = stage / "formal"
    source = cross.read(CHECKPOINT)
    reg = cross.read(stage / "registration.json")
    start = cross.read(new / "batch_start.json")
    end = cross.read(new / "batch_end.json")
    check = cross.read(stage / "check.json")
    require(digest(CHECKPOINT) == CHECKPOINT_SHA == reg["source_audit_sha256"] and reg["source_commit"] == SUBJECT, "Source checksum")
    require(digest(old / "batch_progress.json") == source["source_progress_sha256"] and
            start["registration_sha256"] == digest(stage / "registration.json") and
            start["smoke_gate_sha256"] == digest(stage / "smoke/smoke_gate.json") and
            start["pool_sha256"] == digest(new / "pool_receipts.json"), "Registration or receipts changed")
    require(reg["environment"] == check["current_environment"] == source["current_environment"]
            and not check["versions_match"] and check["bundle_sha256"] == cross.check_bundle()
            and check["runtime_errors"] == [] and cross.read(stage / "smoke/smoke_gate.json")["status"] == "PASS", "Build verification")
    new_ids = {r["id"] for r in reg["roster"]}
    require(start["roster"] == reg["roster"] and new_ids == {x["cell"] for x in source["missing"]}, "Scope")
    history = repo / "research/chapter3_final_evaluation"
    require(audit.blob((history / "execution_lock.json").read_bytes()) == audit.LOCK_BLOB and
            digest(history / "results/endpoints.csv") == audit.ENDPOINTS_SHA, "Historical lock")
    historical = {(r["case"], r["method"], int(r["seed"])):r for r in audit.csvread(history / "results/endpoints.csv")
                  if r["mode"] == "T3" and r["case"] in cross.CASES and r["method"] in ("AB", "Proposed")}
    require(len(historical) == 24, "Historical roster")
    records = [{**r, "windows_build": "26200"} for r in attempts(run)]
    extra = attempts(run, formal_roots=(STAGE + "/formal",))
    require(len(extra) == len({r["cell"] for r in extra}) and {r["cell"] for r in extra} == new_ids, "New launch inventory")
    records.extend({**r, "windows_build": "26300"} for r in extra)
    accepted = {r["cell"] for r in extra if r["status"] == "COMPLETE"}
    actual_receipts = {p.parent.name:cross.read(p) for p in (new / "cells").glob("*/receipt.json")}
    require({r["id"]:r for r in end["receipts"]} == actual_receipts and end["completed"] == len(accepted)
            and set(end["missing"]) == new_ids - accepted, "Stage closure")
    first_missing = set(end["missing"])
    recovered = set()
    retry_ids = set()
    if (run / RECOVERY).exists():
        retry, retry_reg = validate_recovery(run)
        retry_ids = {r["id"] for r in retry_reg["roster"]}
        retry_end = cross.read(retry / "batch_end.json")
        retry_receipts = verified_receipts(retry, retry_reg)
        recovered = {r["id"] for r in retry_receipts if r["status"] == "COMPLETE"}
        retry_launches = attempts(run, formal_roots=(RECOVERY + "/formal",))
        require(retry_ids <= first_missing and {r["cell"] for r in retry_launches} == retry_ids
                and retry_end["receipts"] == retry_receipts and retry_end["registered"] == len(retry_ids)
                and retry_end["completed"] == len(recovered) and set(retry_end["missing"]) == retry_ids - recovered,
                "Recovery closure")
        records.extend({**r, "windows_build": "26300"} for r in retry_launches)
    missing = first_missing - recovered
    accepted.update(recovered)
    ids, refs = cross.identities(), audit.read_e()
    inventory, pairs, mechanisms, matches, checkpoints = [], [], [], [], []
    out.mkdir()
    for case in cross.CASES:
        model = audit.model_for(repo, case)
        for seed in cross.SEEDS:
            group, builds = {}, {}
            for arm, method in (("A","AB"), ("B","Proposed"), ("C","AB"), ("D","Proposed")):
                key = f"{case}_{method}_T3_{seed}"
                ab = arm in ("A","B")
                current = not ab and key in new_ids
                build = "26300" if current else "26200"
                builds[arm] = build
                base = (history / "formal") if ab else (new if current else old)
                if not ab and key in recovered:
                    base = retry
                folder = base / "cells" / key
                label = dict(case=case, seed=seed, arm=arm, windows_build=build,
                             source="historical" if ab else base.parent.name)
                if current and key not in accepted:
                    inventory.append(dict(**label, status="MISSING_FINAL_RECEIPT"))
                    continue
                pool = None if ab else cross.read(base / "pool_receipts.json")[case]["charged_s"]
                v = audit.audit_cell(folder, case, method, seed, ids[case, "G2" if ab else "Q4"], model,
                                    historical[case,method,seed] if ab else None, pool)
                group[arm] = v
                fin = v["final"]
                inventory.append(dict(**label, status="AUDITED_SAFE", initial_J=v["initial"]["J"], configuration_J=v["configuration"]["J"],
                                      final_J=fin["J"], lo_J=fin["bounds"][0], hi_J=fin["bounds"][1], plan=fin["plan"],
                                      charged_s=v["receipt"]["charged_s"], prior_charge_s=v["receipt"]["prior_charge_s"],
                                      configuration_rounds=len(v["configuration_rounds"]), post_rounds=v["post_rounds"],
                                      certificates_checked=v["plan_certificates_checked"], receipt_sha256=digest(folder/"receipt.json")))
                mechanisms.extend({**label, **r} for r in v["mechanism"])
            for left, right in (("A","B"),("C","D")):
                if left in group and right in group:
                    for i, (a,b) in enumerate(zip(group[left]["configuration_rounds"],group[right]["configuration_rounds"]), 1):
                        match = audit.matched(a,b)
                        if match is not None:
                            matches.append(dict(case=case, seed=seed, pair=left+right, round=i,
                                                left_build=builds[left], right_build=builds[right], **match))
            if len(group) == 4:
                tags = dict(case=case, seed=seed, A_build=builds["A"], B_build=builds["B"], C_build=builds["C"], D_build=builds["D"])
                for arm, method in (("C","AB"), ("D","Proposed")):
                    pos = f"{case}_{method}_T3_{seed}"
                    tags[arm+"_source"] = RECOVERY if pos in recovered else (STAGE if pos in new_ids else "continuation_04")
                arms = [group[arm] for arm in "ABCD"]
                pairs.append(dict(**tags, **audit.compare_pair(*arms, refs[case])))
                checkpoints.extend(checkpoint_rows(arms, tags))
    original_pairs = [r for r in pairs if RECOVERY not in (r["C_source"], r["D_source"])]
    for name, data in (("inventory",inventory),("paired",pairs),("paired_summary",summarize(pairs)),
                       ("paired_summary_before_recovery",summarize(original_pairs)),("round_mechanisms",mechanisms),
                       ("matched_rounds",matches),("common_checkpoints",checkpoints),("attempts",[{**r,"copies":json.dumps(r["copies"])} for r in records])):
        audit.table(out / (name+".csv"), data)
    n = sum(r["arm"] in ("C","D") and r["status"]=="AUDITED_SAFE" for r in inventory)
    require(n == 14+len(accepted) and len(inventory)==48 and len(pairs) == sum(all(f"{c}_{m}_T3_{s}" not in missing
            for m in ("AB","Proposed")) for c in cross.CASES for s in cross.SEEDS), "Pair count mismatch")
    state = dict(outcome="ALL_ENDPOINTS_AUDITED_ACROSS_TWO_BUILDS" if n==24 else "INCOMPLETE", audited_CD=n, registered_CD=24,
                 historical_AB_raw=24, deterministic_E_cases=4, complete_pairs=len(pairs), old_CD=14, new_CD=len(accepted),
                 missing=sorted(missing), pre_recovery_missing=sorted(first_missing), pre_recovery_pairs=len(original_pairs),
                 recovered=sorted(recovered), recovery_roster=sorted(retry_ids), physical_attempts=len(records),
                 new_raw_files=evidence_archive(run,repo,out/"archive"),
                 registration_sha256=digest(stage/"registration.json"), old_archive_commit=SUBJECT)
    cross.write(out / "audit.json", state)
    report(out,state,pairs,records)
    print(json.dumps(state), flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("repo","run","out"):
        parser.add_argument("--"+arg, type=Path, required=True)
    a=parser.parse_args()
    out=a.out.resolve()
    require(not out.exists() and not out.is_relative_to(a.run.resolve()), "Output must be new and outside raw evidence")
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        stage=Path(tmp)/"results"
        analyze(a.repo.resolve(),a.run.resolve(),stage)
        stage.rename(out)
