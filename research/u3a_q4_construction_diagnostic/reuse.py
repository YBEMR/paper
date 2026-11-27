"""Import only the specified historical plans and complete traces; never execute a solver."""
import csv
import gzip
import io
import tarfile
import zlib
from runtime import *

def extract(obj):
    code=obj["case"].split("_")[0]
    src=INPUTS/"u2/research/u2_adaptive_groups/results"/code
    dest=OUTPUT/code
    manifest=read(src/"archive.json")
    allparts=[]
    for part in manifest["parts"]:
        b=(src/part["name"]).read_bytes()
        assert sha(b)==part["sha256"] and len(b)==part["bytes"]
        allparts.append(b)
    blob=b"".join(allparts)
    assert sha(blob)==manifest["sha256"]
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(blob)),mode="r:") as tar:
        def get(path):
            return tar.extractfile(code+"/"+path).read()
        index={x["path"]:x for x in json.loads(get("event_index.json")) if "blocks" in x}
        def copy_record(branch,key):
            path=f"r1/{branch}/evidence/{obj['case']}/{key}"
            out=dest/"evidence"/obj["case"]/key
            out.mkdir(parents=True,exist_ok=True)
            plan=get(path+"/plan.json")
            cert=get(path+"/certificate.json")
            assert sha(plan.strip())==key==json.loads(cert)["plan_sha256"]
            ix=index[path+"/trace.npz"]
            blocks=[]
            for h in ix["blocks"]:
                block=zlib.decompress(get("event_blocks/"+h))
                assert sha(block)==h
                blocks.append(block)
            full_bytes=b"".join(blocks)
            assert sha(full_bytes)==ix["sha256"]
            array=np.frombuffer(full_bytes,dtype="<f8").reshape(ix["shape"])
            # Native and causal archives can store the identical plan with distinct measured runtimes.
            if not (out/"plan.json").exists():
                (out/"plan.json").write_bytes(plan)
                (out/"certificate.json").write_bytes(cert)
                np.savez_compressed(out/"trace.npz",events=array)
            else:
                assert (out/"plan.json").read_bytes()==plan
                assert read(out/"certificate.json")["metrics"]==json.loads(cert)["metrics"]
            return dict(key=key,source=path,trace=ix["sha256"],certificate_sha256=sha(cert),
                        source_kernel_s=json.loads(cert)["cert_s"])
        meta=json.loads(get("r1/Q4/construction.json"))
        info=dict(case=obj,archive_sha256=manifest["sha256"],construction=meta)
        if "failed_scene" not in meta:
            first=json.loads(get("r1/Q4/certs.jsonl").splitlines()[0])
            audit=json.loads(get("r1/Q4_causal_audit/audit.json"))[0]
            assert first["plan"]==audit["native"] and audit["kind"]=="Q4"
            info.update(native=copy_record("Q4",first["plan"]),causal=copy_record("Q4_causal_audit",audit["causal"]),first=first)
        if code in ("A06","B07","C10","C11"):
            calls=[json.loads(line) for line in get("r1/NT/certs.jsonl").splitlines() if line.endswith(b"}")]
            best=u.best(calls)
            assert best and best["status"]=="SAFE"
            info.update(nt=copy_record("NT/search/physical",best["plan"]),nt_call=best)
        save(dest/"history.json",info)
    reg=HERE/"registration"/"inputs"/obj["input"]
    reg.parent.mkdir(parents=True,exist_ok=True)
    b=(u.REG/"inputs"/obj["input"]).read_bytes()
    assert sha(b)==obj["input_sha256"]
    reg.write_bytes(b)

if __name__=="__main__":
    start=times()
    assert (INPUTS/"u1/research/u1_unified_diagnostic/interface.py").read_bytes()==(INPUTS/"u2/research/u1_unified_diagnostic/interface.py").read_bytes()
    for obj in u.CASES:
        extract(obj)
        print("Imported",obj["case"],flush=True)
    save(HERE/"registration/cases.json",u.CASES)
    save(OUTPUT/"preparation.json",duration(start))
