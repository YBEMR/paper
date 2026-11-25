"""Audit all frozen run, phase, local and auxiliary deadlines from their receipts."""
import gzip
import json
from datetime import datetime
from settings import ROOT,read,write

def inspect():
    execution=read(ROOT/"execution.json")
    maxima={};over=[];accounted=0
    def limit(kind,seconds,cap,**origin):
        maxima[kind]=max(maxima.get(kind,0),seconds)
        if seconds>cap+1e-6:
            over.append(dict(kind=kind,seconds=seconds,cap=cap,extra_s=seconds-cap,**origin))
    for spec in execution["runs"]:
        if spec["status"]!="COMPLETE":continue
        tag=spec["tag"];folder=ROOT/"runs"/tag;z=read(folder/"summary.json")
        limit("owner_numerical_endpoint",z["elapsed_s"],1800,run=tag)
        file_s=(folder/"summary.json").stat().st_mtime-datetime.fromisoformat(spec["utc"]).timestamp()
        limit("required_endpoint_file",file_s,1800,run=tag)
        limit("process_exit_observed",spec["observed_exit_s"],1800,run=tag)
        for ph in z["phases"]:
            limit("phase_end_relative_to_cutoff",ph["actual_end"]-ph["scheduled_end"],0,run=tag,cycle=ph["cycle"],phase=ph["phase"])
        with gzip.open(folder/"events.jsonl.gz","rb") as f:
            for line in f:
                v=json.loads(line)
                if v["event"]!="subproblem":continue
                accounted+=1;info=dict(run=tag,cycle=v["cycle"],iteration=v["it"],adopted=v["adopted"])
                limit("local",v["elapsed"],30,**info)
                for stage,status,elapsed in v["phases"]:
                    if stage=="auxiliary":
                        limit(stage,elapsed,11,status=status,**info)
    write(ROOT/"timing.json",dict(subproblems=accounted,maxima=maxima,overruns=over))
    return accounted,maxima,over

def annotate():
    accounted,maxima,over=inspect()
    p=ROOT/"decision.md";text=p.read_text(encoding="utf8")
    a=read(ROOT/"audit.json");a["timing_overruns"]=len(over)
    numerical=[v for v in over if v["kind"]!="process_exit_observed"]
    a["local_or_phase_overruns"]=len(numerical)
    if numerical and a["verified"]==12:
        if a["title"]=="D3 达到后续验证条件":
            old=a["title"];a["title"]="D3 能耗与机制条件满足，完整预算门控待定"
            text=text.replace("**"+old+"。**","**"+a["title"]+"。**").replace("证据支持后续消融和其他工况验证。","过程记录有计时越界，严格门控留待判读。")
    text+="\n## 逐项截止核对\n\n"
    text+=f"复核 {accounted} 次正式联合子问题。最长本地用时 {maxima.get('local',0):.4f} s，最长辅助阶段 {maxima.get('auxiliary',0):.4f} s。"
    if over:
        text+=f"局部、阶段、数值终点及必要结果文件共记录 {len(numerical)} 项越界。另有 {len(over)-len(numerical)} 次监管进程观察到退出时已超过 1800 s；该观测包含退出清理和轮询延迟。最晚必要终点文件的写入时刻为 {maxima.get('required_endpoint_file',0):.4f} s（文件系统时间相对启动 UTC）。"
    else:text+="全部已记录的分阶段、局部及进程截止均在规定预算内。"
    text+="逐项记录见 [timing.json](timing.json)。\n"
    p.write_bytes(text.encode())
    write(ROOT/"audit.json",a)
