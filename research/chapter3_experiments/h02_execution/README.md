# K177 H02一次性执行入口

`launcher.py`只监督已获授权的固定B0四槽：R1/H、R1/R、R2/R、R2/H。规划4×120秒，真实H复核最多4×60秒，研究与复核总上限720秒；整批日历上限1200秒。日历余量不能增加研究调用或单次研究预算。

根会话冻结声明、源文件SHA和B0同一授权后，使用`--declaration`与`--declaration-sha`执行。输出固定为`results/response_information_execution01`；监督记录独立保存在同级`response_information_execution01_supervision`，不提前创建B0输出目录。

固定全局claim在进程创建前排他写入；无论成功、异常或超时，已消费入口均不能重跑。进程失败不重试、不修复候选，日历截止只终止当前自有进程树。监督器不产生科学候选或能量上界，完整结果由原B0控制器归档。

纯测试入口：`python -B -m h02_execution.test_launcher --out <新目录>`。测试只使用临时目录和假时钟、假进程，不启动HEFT、MATLAB、优化求解或热评价。
