# 78号输入与运行记录

本目录为入口热压力扩展，原53号与77号文件不覆盖。输入、规则和66次调用顺序在任何新增求解前冻结。

- 发现性诊断：P_high、6 ms、共同初温79.45°C，两方法各一次；不计入主组。
- 主组：原P_low/P_high与6/10 ms四种组合，各取78、79、79.5、79.75°C，共16项。
- 主组重复两次；第一遍原no-good先运行，第二遍热反馈先运行。每调用独立60 s。
- 仅改变初温与标识，其余物理量、工作量、启动域及求解器设置保持原值。
- 温度范围来自距80°C上限的裕量2、1、0.5、0.25°C，不是实测分布。诊断点来自历史轨迹解析关系，不能包装为盲测。

入口为run_pressure78；当前代码只新增p78包装与预检、导出模块，原b68/f77算法不变。正式两方法不接收发现性时间表、历史答案或预制热行。

~~~matlab
addpath('F:/by/11111/research/matlab_config_value_src');
p=run_pressure78('precheck');
run_pressure78('frozen',fullfile(p,'receipt.mat'));
~~~

本轮正式前预检通过284项。初次预检在零时刻指数区间的非负域检查处中止，failure记录保留；同时修正编码比较中的案例标识归一化。两项均为新预检实现修正，未改冻结数值或原方法。

首选时间表的1 ms点证书与替代安排的全窗口证书只在预检文件中保存。入口79.45°C下，独立点区间约[80.02748339927437,80.02748339928272]°C；替代安排的保守全窗口上界小于79.954687847549°C。该关系不预言其他初温点的安全状态。

原始结果以MAT为主，JSON非有限值可能为null。导出summary仅使用经过共同预算审计的U，原始晚轨迹留作诊断，不恢复到排名。

已完成66次冻结调用，正式目录为：

research/matlab_config_value_src/pressure78_reports/frozen_20260928_183250_962

正式组原no-good为26/32次安全，热反馈30/32；两方共同成功时能量相同。结果、逐例两遍计时、反馈证书及局限见[78号报告](../78_入口热压力下连续热反馈对照.md)。58份安全输出独立复核通过；没有扩预算或重跑超时调用。

保存数据复核及作图（不执行求解或热仿真）：

~~~powershell
python research/pressure78_design/postcheck78.py research/matlab_config_value_src/pressure78_reports/frozen_20260928_183250_962
python research/pressure78_design/plot_saved78.py research/matlab_config_value_src/pressure78_reports/frozen_20260928_183250_962
~~~

122份正式源码／输入快照匹配。3,212份保护文件中3,206未变，6个LaTeX编译产物在正式前发生变化，初次只读核对失败及前后哈希已保留；实验文件和LaTeX源文未变，不覆盖这些编译产物。
