# AC RelativeGapTolerance 单因素诊断

**正gap与最优状态冲突仍存在，不能仅归因于RelativeGapTolerance恰为0。**

## 条件与唯一变化

参考任务ac_direct_repro_20261106T152351Z：原生R2023b直接调用，同一301407b6优化轮AC请求。矩阵MAT逐字节相同，SHA256 `bde54760351d94569dbc7524dd7fc1e30eb1efe5fa97d9e9a59938fe7ec44af7`，x0未替换或修复。监督脚本字节相同，MATLAB脚本差异只有RelativeGapTolerance从0到1e-8，见single_factor.patch。真实选项差异={'RelativeGapTolerance': {'reference': 0, 'test': 1e-08}}；精确符合计划=True。

MaxTime仍300秒，MaxFeasiblePoints仍Inf；原双单纯形、两项预处理none、ConstraintTolerance=1e-9、IntegerTolerance=1e-6、AbsoluteGapTolerance=0及其他选项不变。总保护420秒，保留2GiB、用户取消、安全stop和原20/40清理。一次启动、一次调用，不自动重试。本轮是诊断，不能替代原零容差基线。

## 实际执行与结果

根开始2026-11-06T23:36:35.029876+08:00，MATLAB启动2026-11-06T23:36:35.648422+08:00，结束含清理2026-11-06T23:39:25.104038+08:00。总耗时170.078秒，原生调用137.0018641秒。rootlp事件time=135.8345681秒，done.time=136.3292696秒，二者差=0.4947014999999908秒。

exitflag=1；fval=1.115526056796232；absolutegap=0.352008；relativegap=16.63925（原始字段为百分数）；numnodes=0；numfeaspoints=1。消息：找到最优解。

Intlinprog 在根节点处停止，因为目标值在最佳值的间隙容差范围内，options.RelativeGapTolerance = 1e-08。intcon 变量是容差范围内的整数，options.IntegerTolerance = 1e-06。。

返回14014维，位级等于参考x0=True。原始MAT的gap/计数与JSON一致=True。所有观察回调stop=false=True。实际容差下仍有最优状态与gap冲突=True。判据是exitflag1且绝对gap超过实际绝对容差、relativegap/100也超过实际相对容差；不能只因显示的微小非零gap就认定冲突，不能从显示舍入为0得到独立证书。

最小可用内存2.791431GiB，清理=graceful_closed，已记录身份退出核验=True，可见MATLAB余留=[]。输入不变=True，冻结源漂移=[]。

## 解释边界

本次仅区分一个相对gap容差边界，不代表某个求解器内部故障已定位。若矛盾消失，也可能是有限精度停止路径或输出更新对设置敏感，不等于新设置已获独立最优证明；若仍矛盾，不能据一次对照排除所有其他数值因素。没有新的原物理问题SAFE认证；返回初解不属于优化改善，不做算法性能比较。

## 命令与证据

```powershell
& '${PYTHON_EXE}' -B -u .\run_once.py > .\execution.log 2>&1
```

完整argv在LAUNCH.json；实际参数与回调在native/startup.json、native/native_result.json；原始MAT在native/native_result.mat；控制台native/matlab.log；内存memory.jsonl；清理native/closed.json。IDENTITY.json、REFERENCE.json、SOURCE_FREEZE.json和single_factor.patch绑定参考与改动；RESULT.json和AUDIT.json汇总所有状态。未改正式基线、历史文件、未推送或继续其他测试。
