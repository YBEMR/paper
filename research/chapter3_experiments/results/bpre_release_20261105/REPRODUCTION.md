# Reproduction scope and prerequisites

This release preserves scientific inputs, final results, source identities and execution evidence. It is not a portable, pre-authorized launcher. A new machine must form new environment and process-isolation evidence; replacing placeholder paths alone is insufficient.

## Complete baseline-to-subject difference coverage

Remote baseline: `2b18f3cdf97939ec2dc5d58d3a863a8ddc55a0c5`. Original local subject: `e0c4d2858e386e16348955f7c4f7f430a11fc2fd`. The independently checked Git difference is exactly 12 files:

| Original change | Delivery |
|---|---|
| `formal_milp.py` | Exact `reproduction/scientific_fixes.patch` |
| `test_formal_milp.py` | Same exact patch |
| `test_formal_driver.py` | Same exact patch |
| `test_formal_continuation.py` | Same exact patch |
| `bpre_formal_entry.py` | Full `reproduction/entry_references/bpre_formal_entry.py.txt`, local paths replaced |
| `test_bpre_formal_entry.py` | Full corresponding `.txt` reference, local paths replaced |
| `results/bpre_formal_preparation_20261104/input_config.json` | Byte-identical `inputs/input_config.json` |
| `results/bpre_formal_preparation_20261104/input_instance.json` | Byte-identical `inputs/input_instance.json` |
| `results/bpre_formal_preparation_20261104/static_size.json` | Byte-identical `inputs/static_size.json` |
| `results/bpre_formal_preparation_20261104/domain_identity.json` | Byte-identical `inputs/domain_identity.json` |
| `results/bpre_formal_preparation_20261104/plan.json` | `protocol/frozen_plan.json`; private executable paths replaced; all 3185 source/input hashes retained |
| `results/bpre_formal_preparation_20261104/approval_template.json` | Intentionally omitted: old execution-authority template, not a scientific dependency |

Paths in the first six rows are relative to `research/chapter3_experiments/`. Mathematical model, evaluator, native solver and numerical-representation adapter/helper sources otherwise come from the baseline checkout. Their exact identities are in the frozen source map; no representation/model delta is hidden in this release.

Additional external execution code is supplied as source references: `cleanup_admission.py`, its tests, `run_frozen_batch.py`, `diagnostic_300.py` and its tests. The original-to-delivery SHA mapping explicitly identifies any path redaction. These external lifecycle changes are distinct from the four-file scientific/test patch. No sanitized reference is claimed byte-identical or directly executable.

## Fresh-machine steps

1. Checkout the baseline into a new copy. Check/apply the four-file patch. Recover the supplied B.pre inputs without changing their bytes, and place/adapt the two new entry source references. Compare scientific source identities with the preserved manifest; document every necessary local-path adaptation separately.
2. Use licensed MATLAB R2023b with Optimization Toolbox/intlinprog and the recorded compatible Python/dependency versions. Re-run a new bounded native smoke probe and verify original options/version. `bpre_formal_entry.py` reads an original `bridge_e2e.../worker_session/ready.json` and `request_000001.response.json`; those old host-specific admission files are not distributed as reusable authorization. A new probe must produce new evidence.
3. Recreate source identity, current resource availability and cleanup admission. `run_frozen_batch.py` originally consumed `identity.json`, `resource_recheck.json`, `reconciliation.json`, and `validation01/02/result.json`. Those old runtime gate records are not a portable permit and are not supplied for reuse. Regenerate equivalent probes on the new computer, including complete captured-process cleanup evidence under the original 20/40 s policy.
4. Freeze a new environment-specific execution record, input/source hashes and output directory. Use one 600 s root per formal method (HEFT and SA101–105 included), or the separately labeled 300 s diagnostic scope. Include controller/worker preparation, input, construction, initialization, solving and full evaluation in the deadline. Do not recycle consumed claims or tokens, historical candidates, caches, late vectors or old resource gate results.
5. Preserve every outcome, including failures, initial-only results and forced cleanup. Accept only complete original independent SAFE evidence formed before the deadline. Keep the separately timed postcheck distinct from method results and report native objective/bounds separately from certified energy.

These steps describe reproduction requirements. No new experiment or probe was run while preparing this GitHub release. The source patch can be applied directly; the environment-specific entry references require the explicitly documented setup above.
