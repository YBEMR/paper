# B.pre completed results: 600-second comparison and 300-second diagnostic

This release contains every method from the completed seven-method batch and the one separate 300-second diagnostic. The later online-HEFT-initialized MILP variant is excluded. No experiment was rerun to build this release.

| Method | Independently SAFE upper bound (J, rounded) |
|---|---:|
| Whole MILP | 1.0539219348938598 |
| Enhanced HEFT | 0.9201954999839609 |
| SA101 | 0.8883834605098007 |
| SA102 | 0.8726890958467755 |
| SA103 | 0.8743205716563893 |
| SA104 | 0.8743439227420916 |
| SA105 | 0.8763774502465844 |

Exact decimal/rational strings and full final safety evaluations are in `formal600/methods/`. All seven final schedules passed the original full evaluator and the saved postcheck. Postchecks never create a new method result. The original MILP retained its freshly constructed initial witness and did not improve it before the cutoff. SAFE does not mean optimal.

The formal controller ran 2026-11-04 14:09:17.983119–15:15:59.539739 UTC (4001.556667 s). Each method had its own 600 s end-to-end root budget. Parent preparation, worker startup, input loading, construction, initialization, solving and evaluation were counted. Cleanup is separate. Parent-origin clock contracts supersede legacy raw wording about imports. HEFT finished its declared bounded one-pass search in 32.094 s.

The separate diagnostic ran 2026-11-04 16:34:35.319619–16:40:07.234680 UTC (331.915437 s including controller overhead and cleanup). Its admitted SAFE U was again 1.0539219348938598 J. A native objective 0.8611053534251862 was first externally observed after both the 600 s and 300 s cutoffs, with native timing also exceeding the request budget; both native vectors matched. Neither late candidate was independently SAFE-certified, evaluated after cutoff, accepted or used as a new initializer. The 300 s observer first completely read that event at root 301.125 s. This is an observation timestamp, not proof of publication/discovery time.

MATLAB R2023b intlinprog and the original model/options were used. Native cleanup was forced_closed: 20.5 s for formal MILP and 20.484 s for the diagnostic. These are not graceful exits. The original strict identity/all-processes-exited/no-errors predicate passed within the original 20 s grace / 40 s total policy; native exit code 1 is preserved.

## Files and reproduction

- `inputs/` contains byte-identical config, instance, static size and domain identity. Recovered B.pre R1 has deadlines 90/115/90 ms, 7 executions, 3 dependencies, 523 legal options, 8887 variables and 56320 rows. It is not claimed byte-identical to an unavailable older ZIP.
- `protocol/frozen_plan.json` preserves the full source manifest, protocol and hashes with personal/executable paths redacted. Original local subject: e0c4d2858e386e16348955f7c4f7f430a11fc2fd. Remote baseline: 2b18f3cdf97939ec2dc5d58d3a863a8ddc55a0c5. Sanitized files have different delivery hashes.
- `reproduction/scientific_fixes.patch` is the exact four-file patch relative to the remote baseline. It fixes recorder default binding and test isolation; the mathematical model is unchanged.
- `reproduction/entry_references/` preserves controller/entry/test references with local path placeholders, intentionally as `.txt`. They are not immediately executable. Reproduction requires a fresh baseline checkout plus the scientific patch, resolved local paths on a licensed MATLAB R2023b computer, the supplied exact inputs/accuracy/native options, and a new run record with independent root deadlines. Do not reuse old claims, extend cutoffs, change solver or initialize from late candidates.
- `formal600/comparison.csv`, full final method receipts, full postcheck evaluations and execution records cover all seven methods. Duplicate candidate/evaluation copies are omitted from postcheck files.
- Native logs preserve statuses, objective/bound/timing information. Duplicate vectors are omitted with length and canonical JSON SHA; original file SHA is retained in `MANIFEST.json`. Native objectives are not independently certified SAFE energy.
- `MANIFEST.json` maps selected original files to delivered hashes and names each transformation. Full redundant search histories remain locally. This is a concise archival release, not every original file.

This is one instance with five SA seeds, not cross-instance evidence of general superiority. Original MILP and HEFT/SA initial schedules differed slightly; do not claim identical initial points.

See [REPRODUCTION.md](REPRODUCTION.md) for complete source-difference coverage and fresh-machine admission prerequisites.
