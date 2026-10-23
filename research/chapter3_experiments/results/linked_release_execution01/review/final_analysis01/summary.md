# K176两次调用独立只读结论

终态：COMPLETED；有效可比较SAFE：2/2。

|版本|完整安全U/J|第一阶段后U/J|第二阶段后U/J|方法实际/s|P1/s|P2/s|MATLAB启动/s|
|---|---:|---:|---:|---:|---:|---:|---:|
|C|0.999661967|0.999661967|0.999661967|285.281|155.219|125.547|18.609|
|conditional_release|0.999661967|0.999661967|0.999661967|274.063|139.141|132.297|7.657|

同fresh S0：True；同完整S1：True。
新版相对原C：OVERLAPPING_INTERVALS。归因范围：same full S1; one independent call per arm, includes selection/search trajectory and numerical variation。

各臂相对自身S1的净改善、选择触发/耗时、P2选项/变量/行数与过滤证据见facts、models、schedules；rootlp为已保存回调首次观测，未证明MILP全局最优。
native求解时间、方法根时长、构模和传输存在嵌套，不能相加。预算后归档的response仅提取时间与内部状态，不据其x接纳新U。
本次两臂各一开发调用，只能判本配对表现，不支持稳定加速或总体排名。
读取证据前后hash不变：True；只读警告：0；新优化/热积分/候选评价均0。
