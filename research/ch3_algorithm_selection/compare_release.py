"""Compare the public JEDI ReLU cfg projection to the frozen per-block descriptions.

Input directory contains the four official cfg files and release metadata (assets.json).
Only fields present in the synthetic graph can be compared by this program.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from records import ROOT,csv_table


def sections(path):
    rows=[]
    for line in path.read_text(encoding="utf8").splitlines():
        line=line.split("#")[0].strip()
        if not line: continue
        if line.startswith("["):
            rows.append((line.strip("[]"),{}))
        else:
            name,value=line.split("=",1)
            rows[-1][1][name.strip()]=value.strip()
    return rows


def block(kind,cfg):
    if kind=="convolutional":
        if cfg["activation"] not in {"relu","linear"}:
            raise ValueError(cfg["activation"])
        return ["conv",int(cfg["filters"]),int(cfg["size"]),int(cfg["stride"]),cfg["activation"]=="relu"]
    if kind=="maxpool":
        return ["pool",int(cfg["size"]),int(cfg["stride"])]
    if kind=="route":
        return ["route",*map(int,cfg["layers"].split(","))]
    if kind=="shortcut":
        return ["shortcut",int(cfg["from"])]
    if kind in {"reorg","upsample"}:
        return [kind,int(cfg["stride"])]
    if kind in {"region","yolo"}:
        return [kind]
    raise ValueError(kind)


def main(folder):
    ref=json.loads((ROOT/"research/kim_synthetic_platform_v1/platform.json").read_bytes())["architecture_reference"]
    assets={r["name"]:r for r in json.loads((folder/"assets.json").read_bytes())}
    rows=[]
    for i,stem in enumerate(["yolo2","yolo2tiny","yolo3tiny","yolo3"]):
        name=stem+"_relu.cfg"
        cfg=folder/name
        meta=assets[name]
        weight=assets[stem+"_relu.zip"]
        sec=sections(cfg)
        projected=[block(k,row) for k,row in sec[1:]]
        frozen=ref["graphs"][str(i)]["blocks"]
        # Negative and absolute Darknet route references can describe the same dependency.
        def normalized(j,b):
            if b[0] in {"route","shortcut"}:
                return [b[0],*[j+x if x<0 else x for x in b[1:]]]
            return b
        differences=[j for j in range(max(len(projected),len(frozen)))
                     if j>=len(projected) or j>=len(frozen) or normalized(j,projected[j])!=normalized(j,frozen[j])]
        rows.append(dict(app=i,asset=name,cfg_url=meta["browser_download_url"],cfg_sha256=sha256(cfg.read_bytes()).hexdigest(),
                         public_width=sec[0][1]["width"],public_height=sec[0][1]["height"],
                         public_blocks=len(projected),frozen_blocks=len(frozen),different_block_indices=differences,
                         weight_url=weight["browser_download_url"],release_weight_bytes=weight["size"],
                         release_reported_weight_digest=weight.get("digest"),weight_locally_validated=False))
    csv_table("release_graphs",rows)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    main(parser.parse_args().folder)
