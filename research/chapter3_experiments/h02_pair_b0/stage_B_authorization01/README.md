# H02阶段B唯一执行授权

用户已明确批准原四槽，顺序R1/H、R1/R、R2/R、R2/H。每槽120秒；仅完整合格最终方案可另用一次60秒H复核；上限720预算秒。故障即停、不补跑、不延长。

本目录保存直接授权、H05快照、原B0关闭元数据和新授权运行清单。Python、物理输入、算法、槽位、预算均不变；仅按用户授权更新开关、授权身份和对应hash。B0原始报告与清单是历史封版证据，原runtime_freeze字节另存于本目录，仍可在f68787e复现。

执行入口：从research/chapter3_experiments目录运行`F:/Anaconda3/python.exe -B -m h02_pair_b0.controller --execute <user_authorization.json中的allowed_run_directory>`。禁止更换输出路径重用授权。
