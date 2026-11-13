"""Pinned direct Git binary. Raw subprocess evidence survives every failure; no science."""
from pathlib import Path
import hashlib,math,subprocess,time
from core import read,save,sha,IntegrityError,WindowExpired,error_record

class GitIdentityError(IntegrityError):pass

def require_control_only(approval,plan_hash):
    expected=dict(protocol='D285-CONTROL-ENTRY-ONLY-v1',decision='CONTROL_ONLY',plan_sha256=plan_hash,
                  maximum_scientific_workers=0,maximum_solve_calls=0)
    if any(approval.get(k)!=v for k,v in expected.items()):raise PermissionError('Control-only entry approval absent')
    commit=approval.get('frozen_commit','')
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise PermissionError('Control commit identity')
    return True

def identity_files(here,plan,plan_path):
    return [('plan.json',Path(plan_path))]+[(name,Path(here)/name) for name in plan['code_hashes']]

def verify_commit(root,here,plan,approval,evidence,clock,plan_path=None,runner=subprocess.run):
    """Every git process has one attempt, <=5 seconds and the existing 550 cutoff."""
    evidence=Path(evidence);spec=plan['control_git'];exe=Path(spec['path'])
    record=dict(protocol='D285-pinned-git-identity-v1',started_elapsed_s=clock.elapsed,executable=str(exe),
                expected_executable_sha256=spec['sha256'],checks=[],passed=False)
    current=None
    try:
        clock.check(550)
        if not exe.is_absolute() or not exe.is_file():raise GitIdentityError('Pinned Git executable missing or not absolute')
        record['observed_executable_sha256']=sha(exe)
        if record['observed_executable_sha256']!=spec['sha256']:raise GitIdentityError('Pinned Git executable identity drift')
        prefix=plan['repository_package']+'/'
        for i,(name,path) in enumerate(identity_files(here,plan,plan_path or Path(here)/'plan.json'),1):
            clock.check(550);begin=clock.elapsed;stem='entry_git_%03d'%i
            command=[str(exe),'--no-optional-locks','-c','core.longpaths=true','-C',str(Path(root)/'work/publish_repo'),
                     'show',approval['frozen_commit']+':'+prefix+name]
            timeout=min(5.,550-begin)
            raw_out=b'';raw_err=b'';error=None;returncode=None
            try:
                result=runner(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW)
                raw_out=result.stdout or b'';raw_err=result.stderr or b'';returncode=result.returncode
            except BaseException as e:
                error=error_record(e)
                raw_out=getattr(e,'stdout',None) or getattr(e,'output',None) or b''
                raw_err=getattr(e,'stderr',None) or b''
            if isinstance(raw_out,str):raw_out=raw_out.encode('utf-8')
            if isinstance(raw_err,str):raw_err=raw_err.encode('utf-8')
            # Raw bytes first; JSON is supplementary, never the only error record.
            for suffix,data in (('stdout.bin',raw_out),('stderr.bin',raw_err)):
                with (evidence/(stem+'.'+suffix)).open('xb') as f:f.write(data);f.flush()
            current=dict(name=name,command=command,timeout_s=timeout,started_elapsed_s=begin,
                returned_elapsed_s=clock.elapsed,returncode=returncode,error=error,
                stdout_file=stem+'.stdout.bin',stderr_file=stem+'.stderr.bin',
                stdout_sha256=hashlib.sha256(raw_out).hexdigest(),stderr_sha256=hashlib.sha256(raw_err).hexdigest(),
                expected_blob_sha256=sha(path),stdout_bytes=len(raw_out),stderr_bytes=len(raw_err))
            current['matches']=error is None and returncode==0 and current['stdout_sha256']==current['expected_blob_sha256']
            save(evidence/(stem+'.json'),current);record['checks'].append(current)
            clock.check(550)
            if not current['matches']:
                raise GitIdentityError('Git committed identity read failed: '+name+
                    '; returncode='+str(returncode)+'; raw stderr retained in '+current['stderr_file'])
        clock.check(550)
        if sha(exe)!=spec['sha256']:raise GitIdentityError('Git executable changed during identity read')
        record['passed']=True
    except BaseException as e:
        record['error']=error_record(e)
        raise
    finally:
        record['completed_elapsed_s']=clock.elapsed
        save(evidence/'entry_git_summary.json',record)
    return record

