"""Collect every original .npz byte-for-byte into a separate ZIP64 download."""
import argparse
import csv
import gzip
import hashlib
import zipfile
from batch import ROOT,RAW

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("destination")
    args=parser.parse_args()
    with zipfile.ZipFile(args.destination,"x",compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
        for manifest in sorted((ROOT/"data/evidence").glob("V*/traces.csv.gz")):
            case=manifest.parent.name
            folder,=RAW.glob("lane*/engine/physical/evidence/"+case)
            with gzip.open(manifest,"rt",newline="") as f:
                for row in csv.DictReader(f):
                    plan=row["plan"]
                    data=(folder/plan/"trace.npz").read_bytes()
                    if hashlib.sha256(data).hexdigest()!=row["npz_file_sha256"]:
                        raise ValueError("original event checksum mismatch: "+plan)
                    archive.writestr(case+"/"+plan+"/trace.npz",data)
            archive.write(manifest,case+"/traces.csv.gz")
    print("packed all original event files",flush=True)

if __name__=="__main__":
    main()
