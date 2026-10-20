"""Read-only K130 evidence summary. No worker, model or heat operation."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
REPO=Path(__file__).resolve().parents[1]
BASE=REPO/'research/chapter3_experiments/results'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
    final=BASE/'runtime_io_probe05';gate=read(BASE/'runtime_io_precheck02/checks.json')
    assert gate['passed'] and gate['count']==129
    assert all(sha(REPO/name)==h for name,h in gate['source_sha256'].items())
    rows=[];hashes={}
    for number in range(1,6):
        folder=BASE/f'runtime_io_probe{number:02d}';d=read(folder/'checks.json');declaration=read(folder/'declaration.json')
        hashes[f'{folder.name}/checks.json']=sha(folder/'checks.json')
        assert d['solver_requests']==0 and d['research_calls']==0 and d['source_unchanged']
        assert d['cache_bytes_unchanged']
        assert all(sha(folder/'source_snapshot'/name)==h for name,h in declaration['sources_sha256'].items())
        ready=[e for e in d['events'] if e['stage']=='native_ready']
        closed=[e for e in d['events'] if e['stage']=='native_closed']
        rows.append({'probe':folder.name,'passed':d['passed'],'elapsed_s':d['elapsed_s'],
            'context':declaration.get('execution_context_declared_by_launcher','workspace_sandbox'),
            'ready_workers':len(ready),'closed_receipts':[e['cleanup'] for e in closed],
            'published_worker_pids':[e['metadata']['pid'] for e in ready],
            'cache_bytes_unchanged':d['cache_bytes_unchanged'],
            'error':d.get('native_error')})
    d=read(final/'checks.json')
    assert d['passed'] and d['constructor_attempts']==2 and d['native_startups_completed']==2
    for c in d['cleanups']:
        assert c['observed_tree_verified_terminated'] and c['observed_tree_identity_count']>=2
        assert c['process_tree_verification']['verified_terminated']
        assert all(x['state'] in ('EXITED','PID_REUSED_ORIGINAL_EXITED') for x in c['process_tree_verification']['identities'])
    original=read(BASE/'fixed_unit_precheck04/checks.json')
    core=['config_v01.json','inputs.py','milp.py','milp_coefficients.py','schedules.py','thermal.py','solve_model.m']
    unchanged={name:sha(BASE.parent/name)==original['source_sha256']['research/chapter3_experiments/'+name] for name in core}
    assert all(unchanged.values())
    historical=read(BASE/'runtime_io_probe03/environment_audit.json')
    facts={'scope':'K130 runtime diagnosis; no research solver calls or new safety/energy evidence',
        'gate':{'path':'runtime_io_precheck02/checks.json','count':129,'passed':True,'source_files':len(gate['source_sha256'])},
        'probes':rows,'total_ready_workers':sum(x['ready_workers'] for x in rows),
        'total_technical_program_wall_s':sum(x['elapsed_s'] for x in rows),
        'wall_scope':'program clocks only; excludes analysis/editing/review','research_calls':0,'solver_requests':0,
        'core_model_unchanged':unchanged,'historical_metadata':historical,'raw_check_hashes':hashes,
        'original_K129_failure_unchanged':True,'Errno22_reproduced':False,
        'Errno22_root_cause_proven':False,'current_verified_host_lifecycle':True,
        'unresolved_natural_shutdown_latency':True,'cache_modified_by_diagnostic':False,
        'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    save(final/'facts.json',facts)
    total=facts['total_technical_program_wall_s']
    lines=['# K.130：运行故障排查与生命周期修复','',
        '**当前启动／读写／清理链路验收通过，可以回到新版质量验证；历史Errno22的直接根因尚未证实。** 本轮未生成研究候选或调用优化器，旧K129失败不补写结果。','',
        '## 1．已定位的实际问题','',
        '原K129档案mtime显示：Python失败在01:56:38.553 UTC，MATLAB缓存警告在01:56:45.527，READY在01:56:55.516。后来有READY不等于Python当时成功握手；缓存警告晚于失败。报错路径103字符、无非法名，磁盘约124 GB可用；无法据此把原异常归为永久路径／空间故障。mtime是在本机原文件上捕获，见runtime_io_probe03/environment_audit.json。',
        '实际无求解检查复现两类清理问题：受限执行上下文中taskkill被拒，真实子进程残留；在获批host上下文中taskkill成功后父退出1，原判断仍记失败。此外，父正常退出0时一个子进程稍后才退出，立即核验也会误报未决。这些清理问题已定位；不能据此断言它们与原Errno22同根。','',
        '## 2．最小修复','',
        'READY、close开始及强制前保存本次launcher与子进程的PID／创建时间；最终只核这些所属身份。共享原40秒清理上限，最后最多等待10秒确认已有子进程退出。正常退出、强制且已确认退出、未决分列，保留原退出码／taskkill回执／耗时。权限不足、PID身份不符、子仍活或证据缺失均不放行，不向复用PID发信号。',
        'N1生命周期、固定设备配对入口及技术探针统一使用cleanup_is_complete。强制清理完成仍保存session_cleanup；原启动／读写／求解错误、归档失败及已成SAFE不被覆盖。没有放宽热安全或接纳超预算候选。','',
        '## 3．真实检查与失败记录','',
        '| 记录 | READY数 | 墙钟/s | 原状态与含义 |','|---|---:|---:|---|']
    meanings=['通过：单次启动／I/O／正常退出',
        '失败：受限上下文清理被拒，停止第二次启动',
        '失败保留：host强杀成功，但旧规则因exit1停止',
        '失败保留：父exit0、子稍后退，即时确认过早',
        '通过：修复后同Python进程连续两次完整生命周期']
    for row,meaning in zip(rows,meanings):lines.append(f"| {row['probe']} | {row['ready_workers']} | {row['elapsed_s']:.3f} | {meaning} |")
    lines+=['',f"共{facts['total_ready_workers']}次技术READY，五个诊断程序累计{total:.3f}秒；不含编码分析。每组预先声明限制，出错即停，没有补跑原研究。最终129项回归通过，{len(gate['source_sha256'])}项源与快照匹配；包含15项bridge fake边界及10项方法归档／清理用例，另核旧默认／N1模型数组等价。",'',
        '所有技术组均做200次不存在文件读取、200轮JSON原子发布／回读，每个READY后另100次发布；没有复现Errno22。用户工具箱缓存各组前后SHA相同，未删除或重建缓存，未改全局配置。MATLAB关闭有时仍需强制收尾，原因未深挖，次数和成本原样保留。',
        '', '最终两个worker的清理：']
    for index,c in enumerate(d['cleanups']):lines.append(f"- worker{index}：{c['cleanup_status']}，原退出码{c['returncode']}，{c['observed_tree_identity_count']}个已观察身份均退出，清理{c['cleanup_wall_seconds']:.3f}秒。")
    lines+=['','## 4．后续口径','',
        'MATLAB原生调用使用已验收、能管理本次进程树的执行上下文；普通文件分析仍可在原工作区执行。后续所有比较方法统一上下文、统一预算，启动仍计入方法时间，清理继续单列。原02／03／04及K129失败保持，不改绿、不补U。',
        '本轮不再加环境组合、温度扫描或求解调用。下一项是按原模型冻结新版质量验证；若再发生Errno22或清理未决，保存原始异常和所属进程证据，停止受影响调用，不用重试制造成功。',
        '', '代码、检查与来源：run_runtime_io_probe.py；runtime_io_precheck02/checks.json；本目录checks.json／facts.json；只读核查MathWorks R2023b的[-batch入口](https://www.mathworks.com/help/releases/R2023b/matlab/ref/matlabwindows.html)及[路径缓存说明](https://www.mathworks.com/help/releases/R2023b/matlab/matlab_env/toolbox-path-caching-in-the-matlab-program.html)。未因缓存警告修改用户缓存。']
    (final/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (final/'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'ready':facts['total_ready_workers'],'technical_wall_s':total,'final_passed':True,'core_unchanged':True}))
if __name__=='__main__':main()
