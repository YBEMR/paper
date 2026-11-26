"""Losslessly store original physical plans/certificates and event arrays after timing."""
import gzip
import hashlib
import io
import json
import sqlite3
import zlib
from pathlib import Path
import numpy as np
from design import sha

def database(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, body BLOB, certificate BLOB, event_sha TEXT, npz_sha TEXT, segments TEXT) WITHOUT ROWID")
    return db

def archive_run(c,dest,runfolder,physical_db,event_db):
    result=(dest/"run.json").read_bytes()
    run=json.loads(result)
    physical=database(physical_db)
    events=sqlite3.connect(event_db)
    events.execute("CREATE TABLE IF NOT EXISTS chunks (id BLOB PRIMARY KEY, payload BLOB) WITHOUT ROWID")
    added=0;checked=0
    for record in run["records"]:
        cert=record["cert"];pid=cert["plan_sha256"]
        path=dest/"physical/evidence"/c.label/pid
        plan_bytes=(path/"plan.json").read_bytes()
        cert_bytes=(path/"certificate.json").read_bytes()
        assert sha(plan_bytes.strip())==pid and json.loads(cert_bytes)==cert
        m=cert["metrics"];plan=json.loads(plan_bytes)
        assert len(plan["rows"])==c.p.n and plan["case"]==c.label
        cfg=bytes(k+10*(u==3) for u,k,_ in plan["rows"][1::3])
        assert sha(cfg)==record["id"]
        npz=path/"trace.npz"
        raw=npz.read_bytes();filehash=sha(raw)
        old=physical.execute("SELECT npz_sha FROM plans WHERE id=?",(pid,)).fetchone()
        if old:
            assert old[0]==filehash
        else:
            with np.load(io.BytesIO(raw),allow_pickle=False) as f:ar=f["events"]
            assert ar.dtype==np.float64 and ar.shape[1]==31
            assert ar[0,0]==0 and ar[-1,1]==c.p.horizon
            assert np.array_equal(ar[1:,0],ar[:-1,1]) and np.all(ar[:,1]>ar[:,0])
            assert np.array_equal(ar[0,14:18],c.p.initial)
            assert np.array_equal(ar[1:,14:18],ar[:-1,18:22])
            assert max(abs(ar[:,22:26].max(axis=0)-m["peak_hi"]))<1e-7
            assert abs(ar[:,26:30].sum()+m["external_J"]-m["E_J"])<1e-8
            assert abs(cert["E35_J"]+m["temperature_J"]-m["E_J"])<1e-8
            assert m["min_deadline_slack_ms"]>=0 and m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
            if m["status"]=="SAFE":assert max(m["peak_hi"])<=80 and min(m["minimum_lo"])>=20
            if m["status"]=="HOT":assert max(m["peak_lo"])>80
            seg=[]
            for part in np.split(ar,np.searchsorted(ar[:,0],np.arange(10000,c.p.horizon,10000))):
                body=part.tobytes()
                key=hashlib.sha256(body).digest()
                if not events.execute("SELECT 1 FROM chunks WHERE id=?",(key,)).fetchone():
                    events.execute("INSERT INTO chunks VALUES (?,?)",(key,zlib.compress(body,3)))
                seg.append(key.hex())
            physical.execute("INSERT INTO plans VALUES (?,?,?,?,?,?)",(pid,zlib.compress(plan_bytes),zlib.compress(cert_bytes),
                             sha(ar.tobytes()),filehash,json.dumps(seg)))
            added+=1
        checked+=1
    events.commit();physical.commit();events.close();physical.close()
    runfolder.mkdir(parents=True,exist_ok=True)
    with gzip.open(runfolder/"run.json.gz","wb",compresslevel=6) as f:f.write(result)
    assert gzip.decompress((runfolder/"run.json.gz").read_bytes())==result
    # Only this run's newly created staging copies are released after durable local archiving.
    for record in run["records"]:
        path=dest/"physical/evidence"/c.label/record["cert"]["plan_sha256"]
        for name in ("trace.npz","plan.json","certificate.json"):
            (path/name).unlink()
        path.rmdir()
    print("ARCHIVED",c.label,run["method"],checked,added,flush=True)
