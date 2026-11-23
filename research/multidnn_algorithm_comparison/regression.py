"""Fixed physics witnesses and domain/operator checks; no search pilot."""
import os
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[key]="1"
import csv
import random
from collections import Counter
from time import perf_counter
from common import *

def main():
    begin=perf_counter()
    refs={r["case_id"]:r for r in csv.DictReader((ROOT/"research/multidnn_diagnostics/summary.csv").open())}
    specs=[
      ("balanced_forward_reference_start","D005",["LLL","LLL","LHL","LHL"]),
      ("concurrent_forward_preheated","D017",["LLL","LHH","LHH","LHH"]),
      ("concurrent_reverse_reference_start","D000",["LLL"]*4),
      ("asymmetric_reverse_preheated","D000",["LHL","LHL","LLL","LLL"])]
    rows=[]
    for name,dep,opps in specs:
        instance=Instance(name)
        domain=domain_for(instance)
        ev=Physical(instance,domain)
        indices=[ev.opp_index[o] for o in opps]
        adapted=ev.replay(dep,indices)
        proof=ev.evidence(dep,indices)
        direct=instance.replay(dep,opps)
        assert ev._physical[dep,tuple(indices)]==direct
        if dep==refs[name]["best_safe_deployment"] and "/".join(opps)==refs[name]["best_safe_opps"]:
            assert abs(adapted.energy_j-float(refs[name]["best_safe_j"]))<1e-7
            assert abs(max(adapted.upper)-float(refs[name]["best_safe_peak_c"]))<=5.1e-4
            assert adapted.slack_ms==float(refs[name]["best_safe_deadline_slack_ms"])
        rows.append(dict(case_id=name,dep=dep,opps=opps,status=adapted.status,completed=adapted.completed,
                         energy_j=adapted.energy_j,slack_ms=adapted.slack_ms,peak_upper_c=adapted.upper,
                         exact_replay_equal=True))
    # Concrete-domain operators, with original Kim RNG consumption.
    a,b=random.Random(7),random.Random(7)
    ca,cb=Counter(),Counter()
    for dep in domain.order:
        assert domain.ident(domain.raw(dep))==dep
        assert domain.child(dep,"C",a,ca)==domain.old_search.child(dep,"C",b,cb)
        for child,_ in domain.neighbors(dep,32,random.Random(9)):
            assert child in domain.rank
    assert ca==cb and a.getstate()==b.getstate()
    # Old 500-request proxy replay is numerically unchanged.
    from physical import Physical as Old
    instance=Instance("balanced_forward_reference_start")
    instance.bind()
    old=Old(ROOT,"forward_flat_25C",domain.stages)
    ev=Physical(instance,domain_for(instance))
    proxy_errors=[]
    for j,opp in enumerate(("LLL","LLL","LHL","LHL")):
        i=search.OPPS.index(opp)
        proxy_errors.append(abs(ev.proxy("C",j,i)-old.proxy("C",j,i)))
    assert max(proxy_errors)<1e-10
    # Reject incomplete declared workload, not merely thermal-safe bounds.
    try:
        Result("SAFE",500,1.,1.,(30.,)*4,(30.,)*4,required=750)
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete 750-request certificate accepted")
    assert energy_explorer().__name__=="Explorer"
    report=dict(status="PASS",role="fixed witnesses only; no algorithm pilot",wall_s=perf_counter()-begin,
                witnesses=rows,domain_count=81,kim_operator_rng_equal=True,
                old_proxy_errors_j=proxy_errors,incomplete_declared_stream_rejected=True)
    (HERE/"regression.json").write_bytes(encoded(report)+b"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    main()
