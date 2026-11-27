"""Read pinned local checkouts and find complete historical SAFE witnesses."""
import csv, gzip, hashlib, io, json, os, tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTERNAL = Path(os.environ.get("E3_SOURCES", ROOT.parent))
DATA = HERE / "inputs"
def sha(b): return hashlib.sha256(b).hexdigest()
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
def scan_parts(folder,case):
    spec=json.loads((folder/"manifest.json").read_bytes())[case]
    chunks=[]
    for part in spec["parts"]:
        b=(folder/part["name"]).read_bytes()
        assert sha(b)==part["sha256"]
        chunks.append(b)
    data=b"".join(chunks)
    assert sha(data)==spec["sha256"]
    plans={};certs={}
    with tarfile.open(fileobj=io.BytesIO(data),mode="r|xz") as tar:
        member=next(iter(tar));paths=json.load(tar.extractfile(member))
        wanted={}
        for path,meta in paths.items():
            if "/plans/" in path and path.endswith(".json.gz") or "/certificates/" in path and path.endswith(".json"):
                wanted[meta["sha256"]]=path
        for member in tar:
            h=Path(member.name).name
            if h not in wanted:continue
            path=wanted[h];b=tar.extractfile(member).read();assert sha(b)==h
            key=Path(path).name.split('.')[0]
            if "/plans/" in path:
                b=gzip.decompress(b);assert sha(b)==key;plans[key]=b
            else:certs[key]=(b,path)
    return [(key,plans[key],b,path) for key,(b,path) in certs.items() if key in plans]
def scan_nt(folder):
    plans={};certs={}
    with tarfile.open(folder,"r|xz") as tar:
        for m in tar:
            k,name=m.name.split("/");b=tar.extractfile(m).read()
            if name=="plan.json":
                assert sha(b.strip())==k;plans[k]=b
            elif name=="certificate.json":certs[k]=b
    return [(k,plans[k],b,k+"/certificate.json") for k,b in certs.items() if k in plans]
def main():
    DATA.mkdir(exist_ok=True)
    rows=[]; extra={}
    for case in ["D1","D2","C10"]:
        if case!="C10":
            pools={s:scan_parts(folder,case) for s,folder in [
                ("chapter3",HERE.parent/"chapter3_final_evaluation/archive"),
                ("chapter4",EXTERNAL/"fourth/research/chapter4_cross_analysis_v5_execution/checkpoints/windows_26200/archive")]}
            inp=HERE.parent/"chapter3_final_evaluation/instances"/(case+".csv")
        else:
            pools={s:scan_nt(next((EXTERNAL/root/"research"/sub/"data/evidence").glob("C10*/physical.tar.xz")))
                   for s,root,sub in [("M1-i","nt","m1i_generalization"),("M1-j","m1j","m1j_retention")]}
            aud=json.load(gzip.open(next((EXTERNAL/"m3a/research/m3a_quota_distribution/data").glob("C10*/audit.json.gz"))))
            phys=list(aud["physical"].values())
            extra["M3-a"]=list({str(sorted(x.keys())) for x in phys})
            m3=[x for x in phys if x.get('certificate',{}).get('metrics',{}).get('status')=='SAFE']
            if m3:extra['M3-a_min']=min(x['certificate']['metrics']['E_J'] for x in m3)
            inp=next((EXTERNAL/"nt/research/m1i_generalization/registration/inputs").glob("F10*.csv"))
        best=None
        for source,items in pools.items():
            for key,plan,cert,path in items:
                m=json.loads(cert)["metrics"]
                rows.append([case,source,key,m['status'],m['E_J'],path])
                if m['status']=='SAFE' and (best is None or m['E_J']<best[0]):
                    best=(m['E_J'],key,plan,cert,path,source)
        energy,key,plan,cert,path,source=best
        if case=="C10": assert extra["M3-a_min"] >= energy
        dest=DATA/case;dest.mkdir(exist_ok=True)
        (dest/'requests.csv').write_bytes(inp.read_bytes())
        (dest/'original.json').write_bytes(plan)
        (dest/'original_certificate.json').write_bytes(cert)
        dump(dest/'identity.json',dict(historical_plan=key,energy_J=energy,source=source,member=path,
             request_sha256=sha(inp.read_bytes()),original_sha256=sha(plan),certificate_sha256=sha(cert)))
        print(case,energy,source,key,flush=True)
    with gzip.open(DATA/'historical_certificates.csv.gz','wt',newline='') as f:
        w=csv.writer(f);w.writerow(['case','source','plan','status','energy_J','certificate_path']);w.writerows(rows)
    dump(DATA/'additional_inventory.json',extra)
if __name__=="__main__":main()
