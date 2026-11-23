"""Offline comparison with the reused matched Kim and ideal-reference archives."""
import csv,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_preserve import HERE,OLD,read

def csv_out(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,separators=(',',':')) if isinstance(v,(list,dict)) else v for k,v in r.items()})

def main():
    result=read(HERE/'results.json');old=read(OLD/'results.json');assert read(HERE/'verification.json')['status']=='PASS'
    index={(r['case_id'],r['setting'],r['strategy']):r for r in old}
    comparison=[]
    for r in result:
        k=index[r['case_id'],r['setting'],'kim'];zero=index[r['case_id'],'ideal','kim'];ideal=index[r['case_id'],'ideal','ideal_fixed_busy']
        old_h=index[r['case_id'],r['setting'],'predictive']
        c=dict(r,kim_matched_j=k['energy_J'],kim_zero_j=zero['energy_J'],ideal_fixed_busy_j=ideal['energy_J'],
            saving_j=k['energy_J']-r['energy_J'],saving_pct=100*(k['energy_J']-r['energy_J'])/k['energy_J'] if r['SAFE'] else None,
            saving_vs_zero_kim_pct=100*(zero['energy_J']-r['energy_J'])/zero['energy_J'] if r['SAFE'] else None,
            ideal_saving_pct=100*(zero['energy_J']-ideal['energy_J'])/zero['energy_J'],
            ideal_headroom_retained_pct=100*(zero['energy_J']-r['energy_J'])/(zero['energy_J']-ideal['energy_J']),
            prior_busy_H_predictive_j=old_h['energy_J'],prior_busy_H_saving_pct=100*(k['energy_J']-old_h['energy_J'])/k['energy_J'],
            idle_saving_j=sum(k['idle_J'])-sum(r['idle_J']),
            compute_activity_saving_j=sum(k['activity_J'])-k['switch_energy_j']-sum(r['activity_J'])+r['switch_energy_j'],
            leakage_saving_j=sum(k['leakage_J'])-sum(r['leakage_J']),
            incremental_switch_cost_j=r['switch_energy_j']-k['switch_energy_j'],
            peak_upper_c=max(r['peak_upper_c']),kim_peak_upper_c=max(k['peak_upper_c']))
        assert abs(c['saving_j']-sum([c['idle_saving_j'],c['compute_activity_saving_j'],c['leakage_saving_j'],-c['incremental_switch_cost_j']]))<1e-8
        comparison.append(c)
    csv_out('comparison.csv',comparison)
    cases=list(dict.fromkeys(r['case_id'] for r in result));summaries=[]
    for case in cases:
        rows={r['setting']:r for r in comparison if r['case_id']==case};m=rows['medium']
        summaries.append(dict(case_id=case,kim_medium_j=m['kim_matched_j'],new_medium_j=m['energy_J'],
            ideal_saving_pct=m['ideal_saving_pct'],low_saving_pct=rows['low']['saving_pct'],
            medium_saving_pct=m['saving_pct'],high_saving_pct=rows['high']['saving_pct'],
            medium_peak_c=m['peak_upper_c'],min_slack_ms=min(r['min_slack_ms'] for r in rows.values()),
            all_SAFE=all(r['SAFE'] for r in rows.values())))
    csv_out('summary.csv',summaries)
    labels=[c.replace('original','原始').replace('_',' ').replace('C','℃') for c in cases]
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,
        'svg.fonttype':'none','svg.hashsalt':'gpu-idle-preserve','axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(9.5,4.8));x=np.arange(len(cases));width=.18
    for offset,field,label,color in [(-1.5,'ideal_saving_pct','零开销理想参照','#BBBBBB'),
        (-.5,'low_saving_pct','10 µs / 1 µJ','#228833'),(.5,'medium_saving_pct','100 µs / 10 µJ','#4477AA'),
        (1.5,'high_saving_pct','500 µs / 100 µJ','#CC6677')]:
        ax.bar(x+offset*width,[r[field] for r in summaries],width=width,label=label,color=color)
    ax.set(xticks=x,xticklabels=labels,ylim=(0,3.7),ylabel='相对对应Kim的完整系统净节能率 (%)',title='保留Kim计算频率，只对空闲窗口调频')
    ax.legend(loc='upper center',ncol=2,frameon=False,fontsize=9)
    fig.text(.5,.03,'18/18 SAFE；计算阶段频率和时间轴均保持；切频参数为假设值，非硬件实测。',ha='center',fontsize=10)
    fig.subplots_adjust(left=.09,right=.98,top=.9,bottom=.17)
    fig.savefig(HERE/'net_savings.png',dpi=180,facecolor='white');fig.savefig(HERE/'net_savings.svg',metadata={'Date':None});plt.close(fig)
    path=HERE/'net_savings.svg';path.write_text('\n'.join(s.rstrip() for s in path.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
    table=['| 工况 | 理想零开销 | 10 µs / 1 µJ | 100 µs / 10 µJ | 500 µs / 100 µJ | 中档峰温 °C |',
           '|---|---:|---:|---:|---:|---:|']
    for r,label in zip(summaries,labels):table.append(f"| {label} | {r['ideal_saving_pct']:.3f}% | {r['low_saving_pct']:.3f}% | {r['medium_saving_pct']:.3f}% | {r['high_saving_pct']:.3f}% | {r['medium_peak_c']:.3f} |")
    example=next(r for r in comparison if r['case_id']=='original_25C' and r['setting']=='medium')
    env=read(HERE/'environment.json');batch=read(HERE/'receipt.json')
    min_gain=min(r['saving_pct'] for r in comparison);max_gain=max(r['saving_pct'] for r in comparison)
    lines=f"""# 保留Kim计算频率的空闲降频：最后一项补充对照

**确认有净节能：三档非零假设开销下，完整系统总能耗降低{min_gain:.3f}%–{max_gain:.3f}%，18/18全部SAFE。** 原始/B负载约2.74%–3.07%，A负载约1.37%–1.53%。上一轮负结果主要来自把原本可用L的计算阶段改成H，不能用来否定空闲管理。

本轮只补一个策略，直接复用原Kim部署X4139374、四场景计算频率L/L/H/H与上一轮空闲窗口规则。没有重新设计算法或调整参数。执行冻结：[aba1c4c](https://github.com/YBEMR/paper/commit/{env['execution_commit']})；基准2a70dda7，独立分支codex/gpu-idle-preserve。所有旧文件保持不变。

## 六工况结果

{chr(10).join(table)}

表中每个非零节能率均以同工况、同切频开销的Kim恒频结果为分母；Kim自身的场景切频也付费。零开销列复用上一轮理想结果。相对历史零开销Kim的节能率同时保存在[comparison.csv](comparison.csv)，没有用不同域或不同负载能耗混比。

全部18个策略的500请求均在40 ms内完成，最小期限裕量均为**0.731332 ms**；连续峰温上界最高为**{max(r['peak_upper_c'] for r in comparison):.6f}°C**。不仅满足期限，全部计算阶段的起止时间、频率和活动功率都逐行等于原Kim记录，没有通过缩短任务或牺牲期限取得收益。

![三档非零开销下的净节能](net_savings.png)

## 能量来自哪里

原始25°C、100 µs/10 µJ的匹配对照：

| 指标 | 结果 |
|---|---:|
| Kim全窗能耗 | {example['kim_matched_j']:.9f} J |
| 保留计算频率＋空闲降频 | {example['energy_J']:.9f} J |
| 净节省 | {example['saving_j']:.9f} J（{example['saving_pct']:.3f}%） |
| 空闲截距能量节省 | {example['idle_saving_j']:.9f} J |
| 计算活动能耗变化 | 0 J（核验误差≤1.85e-13 J） |
| 温度相关漏电节省 | {example['leakage_saving_j']:.9f} J |
| 比Kim多付的切换能量 | {example['incremental_switch_cost_j']:.9f} J |

与上一轮同档“忙时全H”的预测策略比较，其能耗为{example['prior_busy_H_predictive_j']:.9f} J，较Kim反而增加{-example['prior_busy_H_saving_pct']:.3f}%。现在唯一调整是保留原计算频率，净节能由负转正。转换能量已注入GPU热节点并进入活动能量，分解时拆出一次，不重复加总；开销增加也减少L驻留并改变漏电，已完整重算。

三档开销下保留了各自零开销理想能量差的{min(r['ideal_headroom_retained_pct'] for r in comparison):.2f}%–{max(r['ideal_headroom_retained_pct'] for r in comparison):.2f}%。这支持冻结模型内空闲管理的实用价值，不能视为设备上的实测收益。

## 机制与取舍

1. **是否兑现了此前发现的空间？** 是。在声明切频假设下，大部分理想收益可以保留；原始/B工况仍接近3%，A约1.4%–1.5%。
2. **是否证明新的预测机制？** 没有。直接复用上一轮规则，没有新增预测方法；利用冻结请求和阶段就绪时间提前恢复H，属于确定性已知时间轴上的空闲控制。没有测试在线预测误差或完全反应式的保留频率控制器。
3. **是否是热状态驱动的收益？** 不是。25/30°C动作完全相同，决策不读取温度；普通空闲功率下降与后续漏电减少可以解释全部收益。连续热模型负责完整能量与80°C认证。
4. **是否值得继续？** 值得保留为运行时功率管理组件，当前证据仍不足以将其单独作为第三/四章新的热感知主算法。要主张独立算法贡献，仍缺与常规GPU动态调频策略的公平比较及可信切频参数依据；本轮不自动追加这些工作。

## 核验与复算

新增18次完整热回放，整批{batch['total_wall_s']:.2f}秒完成。上轮Kim各档、零开销理想、忙时全H结果直接复用，未重跑旧78次。所有新策略调用原dispatch/certify，保留全部事件、4节点连续热、10.04秒全窗系统能量及原峰温界精度。

[核验](verification.json)通过：117个执行来源/输入哈希，18份SAFE证书、9,000条请求完成记录、63,000个阶段、3,600次切换；GPU阶段频率与起止逐条相同，切频不与GPU计算重叠，热状态逐段继承，活动计算能量误差≤1.85e-13 J。物理模型仍是冻结合成平台，切频10/100/500 µs和1/10/100 µJ均是假设，不是板端测量。

交付：[协议](PROTOCOL.md)、[配置](config.json)、[适配源码](preserve.py)、[完整CSV](comparison.csv)、[六工况表](summary.csv)、[原始证书和温度轨迹](raw/)、[可编辑SVG](net_savings.svg)、[复算说明](REPRODUCE.md)。本轮到此结束，不追加算法或实验。
"""
    (HERE/'README.md').write_text(lines,encoding='utf-8',newline='\n')
    print(json.dumps(summaries,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
