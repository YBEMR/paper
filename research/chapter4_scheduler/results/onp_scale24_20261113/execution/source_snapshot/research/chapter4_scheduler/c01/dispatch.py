"""C01 input-to-lifecycle bridge; no workload selection or execution budget."""
from .heft_lifecycle import execute_heft


def dispatch(arm, loader, workdir, budget, *, seed=None, bindings=None):
    if arm not in ("HEFT","ON","SA") or (arm!="SA" and seed is not None):
        raise ValueError("C01_HEFT_ON_SA_AND_SA_ONLY_SEED_REQUIRED")
    if arm=="SA":
        from research.chapter4_scheduler.validation.sa_adapter import execute_sa
        return execute_sa(loader,workdir,seed=seed,budget=budget,bindings=bindings)
    if bindings is None:
        from research.chapter4_scheduler.blocking.method import Bindings
        from heft_method import run_heft
        from thermal import evaluate_candidate
        bindings=Bindings(run_heft,evaluate_candidate,"REAL_CORE")
    if arm=="HEFT":
        return execute_heft(loader,workdir,bindings=bindings,budget=budget)
    from research.chapter4_scheduler.blocking.method import execute_reconstruction
    return execute_reconstruction(loader,workdir,bindings=bindings,budget=budget,
        seconds=budget.seconds,allow_blocking_edges=True)
