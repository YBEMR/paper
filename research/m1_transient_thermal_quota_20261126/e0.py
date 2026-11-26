import json
from zipfile import ZipFile
from mechanism import ROOT, ORDER, WINDOW, Case, archive_means, p1, np
from heat import integrate


def main():
    out = ROOT/"data/e0"
    assert not (out/"gate.json").exists(), "preserve E0"
    out.mkdir(parents=True,exist_ok=True)
    records,calibration = [],[]
    with ZipFile(ROOT.parent/"ch4_thermal_evidence.zip") as z:
        for label in ORDER:
            c = Case(label,out)
            p = c.p
            starts = list(range(0,p.horizon,WINDOW))
            for name in z.namelist():
                if not name.endswith("/plan.json") or "/"+label+"/" not in name:
                    continue
                if "/original_v1/" in name and not any(x in name for x in ("10fe04cc","47962734")):
                    continue
                plan = json.loads(z.read(name))
                ref = json.loads(z.read(name.replace("plan.json","certificate.json")))
                cfg = bytes(k+(10 if u==3 else 0) for u,k,_ in plan["rows"][1::3])
                cert,trace = c.certify(cfg,causal=False)
                m,m0 = cert["metrics"],ref["metrics"]
                assert cert["plan_sha256"]==ref["plan_sha256"] and m["status"]==m0["status"]
                assert abs(m["E_J"]-m0["E_J"])<1e-8 and max(abs(np.array(m["peak_hi"])-m0["peak_hi"]))<1e-6
                assert m["min_deadline_slack_ms"]>=0
                ledger = c.ledger(cfg,0,p.horizon,WINDOW,True,True,False)
                # Add observation boundaries only. Event powers and all actions remain fixed.
                split = []
                for row in trace[:,:14]:
                    s,e = map(int,row[:2])
                    points = [s,*range((s//WINDOW+1)*WINDOW,e,WINDOW),e]
                    for lo,hi in zip(points,points[1:]):
                        split.append([lo,hi,*row[2:]])
                ev = np.array(split)
                full = integrate(ev,p.initial,p.G,p.cap,35.,np.array([],np.int64),True)
                assert abs(m["E_J"]-full[0])<1.e-7
                assert np.max(abs(full[10][1:,:4]-full[10][:-1,4:8]))<1.e-12
                running = p.initial.copy()
                for j,s in enumerate(starts):
                    e = min(s+WINDOW,p.horizon)
                    mean = archive_means(ev,s,e)
                    assert np.max(abs(mean-ledger[8][j]))<1.e-10
                    mask = (ev[:,0]>=s)&(ev[:,1]<=e)
                    rows = full[10][mask]
                    truth = rows[-1,4:8]
                    pred = c.propagate(rows[0,:4],mean,(e-s)/10000)
                    running = c.propagate(running,mean,(e-s)/10000)
                    flat = np.array([[s,e,*mean,*[0.]*4]])
                    oracle = integrate(flat,rows[0,:4],p.G,p.cap,35.,np.array([],np.int64),True)
                    assert max(abs(pred-oracle[10][-1,4:8]))<1.e-9
                    calibration.append(dict(case=label,plan=ref["plan_sha256"],start_tick=s,end_tick=e,
                         true_end=truth,from_actual=pred,from_recursive=running.copy(),true_peak_hi=rows[:,8:12].max(axis=0)))
                # Test search-time, causal prefix statistics against its final event ledger.
                causal_cert,physical = c.certify(cfg,causal=True)
                for j in range(c.windows):
                    s,e=j*WINDOW,(j+1)*WINDOW
                    end_idx = c.release.searchsorted(e)
                    piece = c.ledger(cfg[:end_idx],s,e,2500,j==c.windows-1)
                    for b,mean in enumerate(piece[8]):
                        assert np.max(abs(mean-archive_means(physical,s+b*2500,s+(b+1)*2500)))<1.e-10
                records.append(dict(case=label,plan=cert["plan_sha256"],status=m["status"],E_J=m["E_J"],
                          peak_hi=max(m["peak_hi"]),causal_fixture=causal_cert["plan_sha256"]))
    assert len(records)==7
    p1.put(out/"window_calibration.json",calibration)
    p1.put(out/"gate.json",dict(status="PASS",records=records,windows=len(calibration),
                                tolerance={"E_J":1e-8,"peak_C":1e-6,"mean_power_or_slope":1e-10}))
    print("E0 PASS:",len(records),"certificates,",len(calibration),"windows",flush=True)


if __name__=="__main__":
    main()
