"""Offline archive integrity, scope and credential-pattern checks; no experiment."""
import ast
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[3]
started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
read=lambda p:json.loads(p.read_text())
save=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
session=read(OUT/'session_start.json');files=[]
for name in session['scope']:
    p=REPO/name
    files.extend([p] if p.is_file() else sorted(f for f in p.rglob('*') if f.is_file()))
files=sorted(set(files));identities={};sizes={};hits=[];unusual=[]
patterns={
    'private-key-header':rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----',
    'github-classic-token':rb'gh[pousr]_[A-Za-z0-9]{30,}',
    'github-fine-token':rb'github_pat_[A-Za-z0-9_]{40,}',
    'aws-access-key':rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
    'openai-token':rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}',
    'bearer-value':rb'(?i)authorization[\s\x22\x27:=]+bearer[ ]+[A-Za-z0-9_.-]{24,}',
    'credentialed-http-url':rb'https?://[^\s/@:]{2,80}:[^\s/@]{6,120}@',
}
compiled={k:re.compile(v) for k,v in patterns.items()}
for p in files:
    if p.is_symlink():raise AssertionError('SYMLINK_IN_SCOPE:'+str(p))
    data=p.read_bytes();name=p.relative_to(REPO).as_posix()
    identities[name]=hashlib.sha256(data).hexdigest();sizes[name]=len(data)
    if len(data)>=100*1024*1024:raise AssertionError('GITHUB_FILE_LIMIT:'+name)
    for rule,pattern in compiled.items():
        n=sum(1 for _ in pattern.finditer(data))
        if n:hits.append({'path':name,'rule':rule,'matches':n})
    if p.name.startswith('.env') or p.suffix in ('.key','.pem','.pfx','.p12') or p.name in ('credentials','id_rsa','id_ed25519'):
        unusual.append(name)
cache=dict(identities);manifest_checks=[]
def sha(relative):
    if relative not in cache:cache[relative]=hashlib.sha256((REPO/relative).read_bytes()).hexdigest()
    return cache[relative]
for stage in ('main_comparison_20261108','c01_migration_20261108','c01_lifecycle_20261108','c01_formal_20261108'):
    root=Path('research/chapter4_scheduler/results')/stage
    r=read(REPO/root/'completion_record.json')
    formal=stage=='c01_formal_20261108';key='complete_result_file_manifest_sha256' if formal else 'new_artifacts_sha256'
    checked=0
    for relative,expected in r[key].items():
        name=relative if formal else (root/relative).as_posix()
        assert sha(name)==expected,('COMPLETION_MANIFEST_DRIFT',name);checked+=1
    sources=r.get('new_comparison_source_sha256',r.get('source_sha256',{}))
    for relative,expected in sources.items():assert sha(relative)==expected,('SOURCE_DRIFT',relative)
    manifest_checks.append({'stage':stage,'artifact_hashes_verified':checked,'active_source_hashes_verified':len(sources)})
formal_plan=read(REPO/'research/chapter4_scheduler/results/c01_formal_20261108/execution/plan.json')
for group in ('source_sha256','protected_sha256'):
    for relative,expected in formal_plan[group].items():assert sha(relative)==expected,('FROZEN_DRIFT',relative)
    manifest_checks.append({'formal_group':group,'hashes_verified':len(formal_plan[group])})
ignored=subprocess.check_output(['git','ls-files','--others','--ignored','--exclude-standard','--',*session['scope']],cwd=REPO,text=True).splitlines()
assert not ignored,('IGNORED_FILES_IN_SCOPE',ignored)
assert not hits and not unusual,('SENSITIVE_PATTERN_REVIEW_REQUIRED',hits,unusual)
active_sources=[]
for directory in ('c01','comparison'):
    for p in sorted((REPO/'research/chapter4_scheduler'/directory).glob('*.py')):
        ast.parse(p.read_text());active_sources.append(p.relative_to(REPO).as_posix())
index=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=REPO,text=True)
assert not index,'PREEXISTING_STAGED_FILES'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==session['subject_before']
assert subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip()==session['branch']
assert subprocess.check_output(['git','rev-list','--left-right','--count','HEAD...origin/'+session['branch']],cwd=REPO,text=True).split()==['0','0']
for stage in ('main_comparison_20261108','c01_lifecycle_20261108','c01_formal_20261108'):
    batch=read(REPO/'research/chapter4_scheduler/results'/stage/'execution/batch_return.json')
    assert batch['completed'] and not batch['error'],stage
record={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-clock,
    'passed':True,'files_scanned':len(files),'bytes_scanned':sum(sizes.values()),'file_sha256':identities,
    'sizes_bytes':sizes,'files_over_50_MiB':{k:v for k,v in sizes.items() if v>50*1024*1024},
    'completion_manifest_checks':manifest_checks,'credential_patterns_checked':list(patterns),
    'credential_pattern_hits':hits,'credential_filenames':unusual,'ignored_files':ignored,
    'active_Python_AST_checks':active_sources,'new_experiments_or_integrations':0,
    'scope_review':'Only four authorized completed stages, active comparison/C01 code, prior status update and publication provenance. Historical bytes preserved.',
    'limitations':'Pattern scan is a targeted credential check, not a proof that all possible sensitive content is absent. No source/result rewrites or research reruns.'}
save(OUT/'prepublish_audit.json',record)
print(json.dumps({k:record[k] for k in ('passed','files_scanned','bytes_scanned','wall_s','completion_manifest_checks','credential_pattern_hits','ignored_files')},ensure_ascii=False),flush=True)
