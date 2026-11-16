# Core-mask study — what pinning NPU cores buys on RK3588

Measured 2026-11-02 with rk-bench v0.3.0 (`--core-mask`, recorded in each
report's protocol block), same frozen protocol as the leaderboard
(priming + 3 independent sessions, median p50, PERF_RUN timing). FP
models, RK3588 (driver 0.9.8, librknnrt 2.3.2). "default" is the
leaderboard row — `rknn_set_core_mask` never called.

| Model | default | core 0 only | cores 0_1 | cores all (0_1_2) |
| --- | ---: | ---: | ---: | ---: |
| YOLOv8n | 37.50 ms | 37.52 ms | 35.65 ms | 35.62 ms |
| YOLO11n | 43.67 ms | 44.20 ms | 42.51 ms | 41.58 ms |
| YOLOv8s-seg | 104.53 ms | 114.55 ms | 102.15 ms | 100.62 ms |

All runs `NPU_ONLY`; session spreads were tight (≤1 ms except one
107 ms outlier session inside the seg core-0 median, which the median
absorbed).

## Reading the table

- **Pinning to a single core is free for small detectors and costly for
  the big one.** YOLOv8n/YOLO11n are unchanged within noise; YOLOv8s-seg
  gets 9.6% *slower*. If you pin cores to isolate workloads, the largest
  model is the one that pays.
- **Two cores capture nearly everything.** Going 0_1 → all adds one more
  core and buys 0.1–2.3% — the third core is mostly decoration for these
  single-stream models.
- **The gain over default is real but small:** −5.0% (YOLOv8n), −4.8%
  (YOLO11n), −3.7% (seg) at `all`. The runtime's default assignment is
  apparently not already spreading one model's graph across all three
  cores, but explicitly asking for them is a single-digit-percent lever.
- **It is not the lever that matters.** INT8 quantization on the same
  board is a 1.4–2.0× lever. Core assignment is what you tune after
  precision, not instead of it.

## Practical guidance

- Running several models concurrently? Pin each to its own core(s) for
  isolation — just don't pin a heavy model to exactly one core and
  expect default performance.
- Single-model latency chasing? `--core-mask all` is worth its ~5%, and
  `rkbench run --core-mask <x>` now measures your model under any mask
  with the mask recorded in the report, so the claim stays auditable.

Raw reports: produced by the commands in the v0.3.0 release notes;
reproduce with any RK3588 board and the models from the RKNN Model Zoo.
