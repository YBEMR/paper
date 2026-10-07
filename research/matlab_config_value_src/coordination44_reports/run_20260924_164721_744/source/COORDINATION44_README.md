# Coordination44: fixed CPU units and shared-frequency coordination

Run MATLAB R2023b with this directory on the path: `run_coordination44`.
Use a workspace-local MATLAB_PREFDIR if the default preference directory is not writable.

Inputs: frozen coordination43-v1 JSON (8 main, 2 domain diagnostics). SI units internally.
Cases are abstract; no real device calibration. No parameter tuning or extra scan points.

New c44 modules add per-stage units and shared-frequency compatibility. The previous
cv_validate, thv_evaluate and h37_partial assume serial CPU execution and are not called
for the new parallel schedules. The unchanged cv_response, cv_energy, thv_build,
thv_step and thv_trace are reused through compatible interfaces.

c44_library enumerates all 4 mode pairs, 4 labelled CPU assignments and legal start
grid times (no symmetry elimination). C0/C1 each build their own library inside the
60 s total budget. Filtering by committed prefix and exact current launch set implements
the specified no-thermal conditional optimization; it is not a new search algorithm.
Incomplete enumeration cannot be used to claim an exact action ranking.

C1 checks the entire launch group plus committed trajectory through the common window.
No unstarted future work is injected. No thermal reference file, witness or suffix is
available to the policies. All policies finish before the reference phase begins.

Reference checks energy layers, retaining witnesses and distinguishing exclusion,
unresolved thresholds and budget exhaustion. First-loss diagnostics, when needed,
share the same reference budget. CPU mode names LL/LH/HL/HH are ordered A then B.
Canonical schedule keys use stage order A1,B1,A2,B2; CPU units 1,2 and NPU 3;
CPU modes L=1,H=2 and the fixed NPU key=0. Energy layers use the frozen tolerance.

Each run saves frozen inputs/source/rules, environment, hashes, MAT/CSV, complete
decision attempts, checks and preselected plots S1_cold/S1_hot/S2_hot. Failed runs
remain in their timestamped directories. Test fixtures are separate from research cases.
