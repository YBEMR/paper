# Scope40 frozen execution rules, v1

Run in MATLAB R2023b: `addpath('research/matlab_config_value_src'); run_scope40`.

The 60 cases are exactly protocol 39: L3-Q/S, rho={1,1.5,2,3,4,6}, headroom={.05,.25,.5,.75,1}. Starts use a 1 ms grid; stage durations and deadlines are not rounded. Horizon is 60 ms. All values remain synthetic. Fifteen original cases are a separate regression group.

All policy executions precede classification. `s40_config` returns only modes, durations and increments. `h37_policy` is reused unchanged. Each case/version has 60 s including planning and all tied modes. The reference has its own 60 s including no-heat planning. No rerun with an enlarged budget.

No-heat reference enumerates four mode combinations and all CPU/NPU orders, with each start rounded UP after dependency/resource release. Earliest scheduling suffices without heat because fixed-mode energy does not depend on time. Thermal classification considers all legal starts, not just earliest schedules.

Modes are ordered by energy then numeric L/H codes (L=1,H=2). Resource orders and start ticks ascend deterministically. Optimal modes require an all-safe proof or both safe/unsafe witnesses; nonoptimal modes need existence/exclusion to locate the thermal energy optimum. A safe witness does not imply A. A mode with threshold-unresolved candidates cannot be excluded. Exhaustion, early evidence stop and timeout are distinct. Same-domain energy lower/upper bounds and unresolved tied members are retained.

Two sufficient, continuous-time all-schedule certificates are fixed BEFORE running:

1. Uniform invariant upper temperature b=max(T0, Ta+p_max,n/g_env,n). At the maximum-temperature node coupling cannot add heat. If b is below both limits minus the numerical band, all schedules are safe.
2. Let M=max_n(T_n-Ta), gamma=min_n(g_env,n/C_n), b0=max_n(p_idle,n/C_n). The upper Dini derivative obeys D+M <= -gamma M+b0+sum(active increments)/min(C). Integration and exp(-gamma t)<=1 give M(t)<=max(M(0),b0/gamma)+E_activity/min(C). This is conservative: it adds ALL stage activity energies, including NPU, and does not claim physical calibration. If the bound is below the limits, all schedules are safe. No fitted constants or result-dependent tuning.

Both certificates assume this positive RC network, nonnegative inputs, and T0>=Ta. The second is a proof aid, not a new scheduling algorithm. Bound failure implies nothing about infeasibility.

Continuous peaks use the existing exact-segment evaluator with internal stationary points and full idle tail. Temperature band=1e-6 C; time tolerance=1e-9 s; energy tolerance=max(1e-10 J,1e-8*energy scale). No heat safety claim beyond 60 ms.

Outputs separate model class, optimal-mode-set survival, thermal optimum bounds, and P0/P1 performance. In C, fixed-M0 policies cannot succeed by definition; this is not evidence of a dispatch defect. Failure with a safe same-mode witness is compared at the first differing start decision, without claiming that witness is the unique optimal continuation.

Software fixtures are separate from research cases. Corrections may trigger a same-input rerun; failures and snapshots are retained. No new research points, thermal parameters, or policy priorities are selected after seeing results.
