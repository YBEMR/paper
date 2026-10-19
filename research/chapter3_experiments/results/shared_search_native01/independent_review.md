# K115 独立终审

结论：通过。属于内部静态与已保存档案审查，**非主线⑥**；未执行新测试、构模、热评价、求解或 Git 操作。

最终 mock04 为 57/57 PASS（52 单测＋5 完整性，6.219 秒），唯一 native01 为 13/13 PASS。28 项当前源码、mock04 快照和 native01 快照逐项 SHA256 一致；声明、准入 gate、独占 claim 和原生验收记录使用同一源码映射。原 24 档案及固定配置字节未变。旧 K113 gate 仅复用 22 项未变表达／数值相关文件，partial_method、bridge、worker 三项改动已由本轮验证，不能称旧整包当前通过。

| 原生请求 | 已保存证据 | 结论边界 |
|---|---|---|
| 1 | 声明／分配／实际 MaxTime 均为 1e-6 秒；native.mat 同值，response_deadline_shortened=0；exitflag=0，原文明确时间限制；x 为空 | 实际覆盖时间限停分支。原生调用实际 1.5857151 秒，软上限不是硬墙钟停止保证；无可接纳候选 |
| 2 | 默认请求无新增 cap 字段，MaxTime=160.5367906998901；正常返回 exitflag=1，99 维向量可接纳；exact schedule 合法 | 仅 SCHEDULE_VALID_THERMAL_UNCHECKED，热／能量均 NOT_EVALUATED；不构成 SAFE、独立最优或节能证据 |

两次请求复用同一已构建小模型，c/A/b/Aeq/beq/lb/ub/intcon 完全相同；native.mat 的最终向量和退出码与原始 response、Python return 一致。固定 runner 只构造一次 MatlabSession，同一工作进程 PID47560 顺序处理两请求，未继承第一请求 cap；ready 正常，closed.returncode=0。绝对截止时间均为 1884116.453；两次响应完成于 1883955.781、1883956.531，均在截止前。180 秒总钟包含输入、构模、启动、导出、传输和回执读取，方法耗时 20.093 秒；清理另记 8.766 秒，不接收新证据。

本次输入为已有两场景各 A.pre、起点 0 的正确性夹具，实际构模仅首个 AB 场景、A.pre=CPU1（99 变量／286 行／3 选项）。auto-L 配置只改三项策略声明；平台参数、400ms 窗口、50°C 入口和80°C 温限保留。本次 0 次连续热评价、0 次研究调用；未实跑 16 条件外层、完整三 Stage、真实跨场景 SAFE 更新或60秒搜索片，未验证原规模性能，也未适配生产 HEFT/SA 和旧下界入口。

开发记录完整保留：mock01 有7个错误与1个断言失败，mock02 有8个汇总错误，原失败记录均未改写；mock03 虽55/55通过，独立审查后仍修正了初始化池严格改善判据、A.pre/A.main/A.post 规范排序键及 Recorder／BuildObserver 引用环。mock04 含区间反例、精确顺序及禁用循环 GC 的 weakref 检查。构模快照保存后解绑，既有 SAFE／违规诊断保留。全部为已存记录与源码核查，未增加原生调用。

SHA256 绑定：

- mock04 checks.json：`999fc8e01560ec3e55c39165a502c52aede0b56ff4c84ba34fc5d3d12982a03a`
- native verification.json：`72852a1bbf6573da65ce8674e0c91bfee1912094c06da8675805974e90a2abe8`
- 全部54项 native 档案及相关 mock／claim／旧 gate／历史基准清单：`6cd9d398ef27330bcbc28525e9a481b57376d6f1d7fa9b9ba9fb9ec1b4586966`

逐项检查与完整哈希映射见 independent_review.json。两份审查文件自身排除在绑定清单外，避免循环哈希。未发现未关闭的阻断。
