"""Repeatable input, boundary, certificate and attribution interface checks."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import json
import math
import sys
import time
from unittest.mock import patch
import diagnostic as d


def midpoint(pair): return (float(pair[0])+float(pair[1]))/2


def rk4(platform,segments,initial,sensitivity=False):
    """Independent float ODE crosscheck only; never used as error certificate."""
    n=len(initial); z=list(map(float,initial))+[0.]
    def rhs(seg,state):
        theta=[state[k]-float(platform['ambient_C']) for k in range(n)] if not sensitivity else state[:n]
        lam=list(map(float,seg['leak_W_per_K']))
        power=[lam[k]*theta[k] for k in range(n)]
        if not sensitivity:
            power=[v+float(seg['base_W'][k])+float(seg['activity_W'][k])+lam[k]*(float(platform['ambient_C'])-float(platform['leak_reference_C'])) for k,v in enumerate(power)]
        flow=[(power[k]-sum(float(g)*theta[j] for j,g in enumerate(platform['G_W_per_K'][k])))/float(platform['C_J_per_K'][k]) for k in range(n)]
        energy=sum(lam[k]*theta[k] for k in range(n))
        if not sensitivity: energy+=sum(float(v) for v in seg['base_W'])+sum(float(v) for v in seg['activity_W'])+float(platform['external_power_W'])+sum(lam)*(float(platform['ambient_C'])-float(platform['leak_reference_C']))
        return flow+[energy]
    for seg in segments:
        t=float((seg['end_us']-seg['start_us'])/1000000)
        count=max(1,math.ceil(t/.00005)); h=t/count
        for _ in range(count):
            k1=rhs(seg,z); k2=rhs(seg,[v+h*k/2 for v,k in zip(z,k1)])
            k3=rhs(seg,[v+h*k/2 for v,k in zip(z,k2)]); k4=rhs(seg,[v+h*k for v,k in zip(z,k3)])
            z=[v+h*(a+2*b+2*c+e)/6 for v,a,b,c,e in zip(z,k1,k2,k3,k4)]
    return z


def run(folder):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    checks=[]; artifacts={}
    def check(name, fn):
        try:
            ok=bool(fn()); checks.append(dict(name=name,pass_=ok))
        except Exception as exc: checks.append(dict(name=name,pass_=False,error=type(exc).__name__+': '+str(exc)))
    def raises(fn,text):
        try: fn()
        except Exception as e: return text in str(e)
        return False
    x=d.load(); p=x['problem']; before=d.identities()
    check('CP1源SHA及共同问题／证明材料完整身份',lambda:d.cp.sha(d.SOURCE)==d.SOURCE_SHA)
    check('完整合法响应14行，没有删除选项',lambda:sum(len(s['options']) for m in p['modes'].values() for s in m['stages'])==14)
    check('两路径及既有共同窗口和权重',lambda:[q['trace']['id'] for q in p['evaluation']['paths']]==['F1','F2'] and all(q['trace']['window_us']==80000 for q in p['evaluation']['paths']) and p['evaluation']['weights']==[F(1,2),F(1,2)])
    for a,b in [('a0','b0'),('a0','b1'),('a1','b0'),('a1','b1')]:
        bundle=d.candidate(x,a,b)
        check(a+b+'精确合法模式、依赖、资源及非整数结束',lambda b=bundle:d.v1.validate_plans(b['candidate']) is None)
        check(a+b+'联合入口范围绑定',lambda b=bundle:bool(d.joint.validate_bundle(b,d.Budget())))
        sx=d.joint.safety_input(bundle)
        proof=d.v2.verify(sx,bundle['candidate']['semantics'],d.Budget(seconds=20))
        artifacts[a+b+'_certificate']=proof
        check(a+b+'期限及8片段共同盒持续安全',lambda r=proof:r['status']=='sustained_safe')
        for path in bundle['evaluation']['paths']:
            xx,tr,prefix,state,rows,segments=d.path_parts(bundle,path); label=a+b+tr['id']
            check(label+'转换前CPU-L/NPU-H、无旧工作',lambda s=state:s['held_opps']=={'C0':'L','N0':'H'} and not s['unfinished'])
            check(label+'新模式释放无候选相关延迟',lambda rows=rows,tr=tr:sorted(set(r['start_us'] for r in rows if r['stage']=='B0'))==[F(tr['switch_requests'][0]['time_us']),F(tr['switch_requests'][0]['time_us'])+20000])
            check(label+'公共窗口功率分段无缺口',lambda ss=segments:sum(s['end_us']-s['start_us'] for s in ss)==80000)
            if b=='b1':
                cut=F(tr['switch_requests'][0]['time_us'])
                check(label+'B0结束至B2开始CPU仍保持H',lambda ss=segments,c=cut:all(s['opps']['C0']=='H' for s in ss if c+1000<=s['start_us']<c+1250))
    bundle=d.candidate(x,'a0','b0'); path=bundle['evaluation']['paths'][0]
    bad=deepcopy(path['trace']); bad['window_us']=45000
    check('45ms独立W1必须拒绝，不能移动54ms原期限',lambda:raises(lambda:d.v1.expand(bundle['candidate'],bad,d.Budget()),'W1_incompatible'))
    prefix=d.prefix_score(bundle,path); artifacts['prefix']=prefix
    check('45ms合法前缀精确到切点，仅评分',lambda:prefix['result']['covered_until_us']==45000 and prefix['prefix_role']=='score_only_not_complete_U1_or_U')
    xx,tr,ss,state,rows,segments=d.path_parts(bundle,path)
    ode=rk4(xx['platform'],ss,[30,30])
    check('前缀温度与能量独立RK4交叉核对',lambda:all(abs(a-midpoint(b))<1e-8 for a,b in zip(ode[:2],prefix['result']['end_temperature_C'])) and abs(ode[-1]-midpoint(prefix['result']['energy_J']))<1e-10)
    ref=d.b_reference(bundle,35000); artifacts['reference']=ref
    check('B参考完整两轮及尾段',lambda:ref['result']['covered_until_us']==35000 and ref['result']['complete'])
    check('B参考公共功率只计一次',lambda:d.box(ref['result']['external_J']).lo==F(35000,1000000)*F(1,2))
    for j in range(2):
        tangent=rk4(xx['platform'],ref['segments'],[int(j==k) for k in range(2)],True)[-1]
        check('g坐标'+str(j)+'独立齐次ODE核对',lambda t=tangent,j=j:abs(t-midpoint(ref['g_J_per_K'][j]))<1e-10)
    zero=deepcopy(xx['platform'])
    ss0=deepcopy(ref['segments'])
    for s in ss0: s['leak_W_per_K']=[0,0]
    gz=d.sensitivity(zero,ss0,d.Budget())
    check('零漏电时入口能量敏感度包含零',lambda:all(d.box(g).lo<=0<=d.box(g).hi for g in gz))
    check('精确并列全保留',lambda:d.retained({'a':d.I(1),'b':d.I(1)})==['a','b'])
    check('重叠区间不能破并列或判严格优势',lambda:d.retained({'a':d.I(1,2),'b':d.I('1.5','2.5')})==['a','b'])
    check('确定劣者排除',lambda:d.retained({'a':d.I(1,2),'b':d.I(3,4)})==['a'])
    check('无有效完整能量不得汇总／推断选择',lambda:d.summarize(x,{'local_cartesian':['a0b0']},{'a0b0':{'result':{'status':'unresolved','certified_candidate_energy':{'status':'unavailable'}}}})['conclusion']=='unresolved_or_invalid')
    exhausted=d.joint.evaluate_bundle(bundle,d.Budget(seconds=0))
    check('预算中断不得接纳完整安全能量',lambda:exhausted['certified_candidate_energy']['status']=='unavailable')
    joint=d.joint.evaluate_bundle(bundle,d.Budget(seconds=20)); artifacts['one_joint_interface']=joint
    check('单组合预检联合安全证书和能量接线',lambda:joint['status']=='certified_candidate' and joint['certified_candidate_energy']['status']=='available')
    check('安全输入完整同源身份',lambda:d.joint.binding(bundle)==joint['binding'])
    check('旧源与依赖未改',lambda:before==d.identities())
    report=dict(material_passport={'id':'HT1-precheck','type':'implementation fixture checks','status':'VERIFIED' if all(c['pass_'] for c in checks) else 'FAILED'},
                all_pass=all(c['pass_'] for c in checks),checks=checks,sources=d.identities(),
                numerical_crosscheck='RK4 is implementation evidence only, interval Taylor remains certificate',
                research_run=False)
    d.write(folder/'artifacts.json',artifacts); d.write(folder/'precheck.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: precheck.py NEW_OUTPUT_FOLDER')
    sys.exit(0 if run(sys.argv[1])['all_pass'] else 1)
