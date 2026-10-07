# 四Stage任务首轮验证（55号）

独立入口`run_stage55`，MATLAB R2023b。输入仅为`research/stage53_design/inputs_v1.json`和`rules_v1.json`；严格核对53号固定哈希。旧入口及其研究案例不改变。

PowerShell示例（仅首次实施／明确复核时运行，不为超时扩大预算重复运行）：

```powershell
$env:MATLAB_PREFDIR='F:\by\11111\.runtime\matlab_prefs'
& 'F:\Matlab2023\Program_Files\MATLAB_R2023b\bin\matlab.exe' -batch "addpath('F:/by/11111/research/matlab_config_value_src'); run_stage55('precheck');"
```

预检输出`stage55_reports/precheck_<时间戳>/receipt.mat`。当前66项预检全部通过后，以实际绝对路径替换下列占位符（本次正式计算启动时为65项；第66项为导出故障后的回归检查）：

```matlab
addpath('F:/by/11111/research/matlab_config_value_src');
run_stage55('frozen','<通过预检且源码哈希匹配的receipt.mat绝对路径>');
```

`frozen`拒绝失败或源码／输入／旧依赖哈希不匹配的凭据。每方法独立枚举，不共享库；先保存全部无热与完整后缀基线，再运行热参考。60 s是包含生成、排序、选择及热评价的协作式预算检查；不可中断调用可能略超时，返回后记未决，不把其新结果当预算内证明，也不宣传硬实时看门狗。

实现模块：

- `s55_load/schedule/validate`：显式八Stage链、合法模式、动态设备、S3完成及完整／部分检查。
- `s55_enumerate/sort`：有限网格完整枚举、固定锚点能量层、规范排序；不热剪枝、不CPU标签去重、不删高能量模式。
- `s55_energy/thermal`：事件积分／活动求和双算；按实际CPU／NPU注热，复用原`thv_build/step`连续段内峰值。
- `s55_method`：独立无热、每初始动作单代表完整热复核、同域热参考。没有读取参考文件或共享候选缓存。
- `s55_tests`：独立笛卡尔积、设备／域／非整数边界、旧47见证、连续峰值与ODE、动作／并列、超时和资源异常等夹具。
- `s55_export`：执行后的独立评价与图表，不补搜索、不修复方案。
- `s55_finish_saved`：只读已保存的完整30次方法结果，核对原计算源码未变，允许导出器／测试修复后另建后处理目录；不调用枚举器或方法，不重跑案例。

输出保存在唯一时间戳目录：输入／源码／环境与哈希、预检凭据、逐方法JSON、results.mat、summary.csv、schedules.csv、代表尝试CSV、参考配置CSV、postchecks.csv、时间表／温度图和日志。Inf／NaN在JSON中可能为null，完整数值与状态以MAT及CSV为准；必须同时读取状态字段。

完整配置以每Stage本地choice编码，解码表在同次inputs.mat中；时间表另外保存实际unit、mode、时长和活动功率。参考state：0未检查，1已有安全见证，2全部排除，3含未分辨。见证不证明所有时序安全；能量最优性和配置集合完整性分开。

`no_safe_representative`只表示单代表基线覆盖不足；`timeout/resource_unresolved`不代表实例不可行。无热结果的上下界属于无热问题，不能当作已热可行上界。部分枚举没有精确代表，不参与H52反例判定。

案例属于L3条件性输入，不是Lite0设备性能复现；本轮工作量、模式、预算和参数不因输出变化。正式结果和实施失败记录以55号报告为准。

本次计算全部保存后，CSV导出器的空结构体初始化失败。原`frozen_20260925_173727_619`目录及其results.mat／失败日志保留；修复只涉及`s55_export`和导出回归测试。新预检凭据为`precheck_20260925_175437_374/receipt.mat`，恢复仅运行：

```matlab
s55_finish_saved('<原frozen目录绝对路径>','<修复后precheck凭据绝对路径>');
```

恢复结果位于原目录的`postprocess_<时间戳>/`，包含完整CSV、图表、事后检查及零方法重跑审计。不要因根目录保留failure.txt就重跑30个方法；应阅读后处理audit.json确认恢复状态。
