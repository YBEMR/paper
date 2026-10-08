# K.31状态更新修订定向复审03

## Material Passport

2026-10-08；主线（6）；被审提交`1d61fdd0446c61bce3c85f44ac7fd0977a202631`，本地main引用与委托一致。仅复核save_state、claim／finally、既存状态预检及新准入绑定。只读源码、文件存在状态、保存结果与哈希；未运行预检／热评价／正式诊断，未操作Git，未修改其他文件。

## 结论

**本次状态更新缺陷已修复，定向复审通过，无新增必要修订。可将本审查及当前源码绑定到新ready02.json，按原授权执行一次TP-1诊断。** 当前尚未准入绑定：state仍awaiting_review、正式次数0、正式目录不存在；不得沿用旧ready.json。

本次确为上一轮未发现的实现缺陷：旧cp.save以`x`模式创建文件，原预检只在不存在的状态路径上调用claim，没有覆盖真实既存state.json。主线自查发现后保留记录并修复，未发生正式调用。此前通过结论不应掩盖这一遗漏。

## 核对结果

| 项目 | 判断 |
|---|---|
| 控制状态更新 | save_state在同目录独占创建state.json.tmp，完整写入并关闭后replace既存state.json；claim、正常完成及异常finally均改用该接口。消除了旧create-only写入既存状态的FileExistsError。 |
| 证据文件保护 | 输入快照、逐次结果、哈希和summary仍调用原create-only写入。状态更新接口没有替换研究证据文件的调用路径。 |
| 防重复执行 | 正式目录仍先以exist_ok=False独占创建，然后写running／次数1，再开始评价。并发第二个claim会因目录存在而拒绝；状态写入或进程失败即使残留目录，也不会自动重跑。临时文件已存在会拒绝覆盖，保留现场。 |
| 更新预检 | 新夹具先创建既存ready状态，再claim，核次数1；分别更新完成和失败状态，验证读取一致及完成后无临时文件；重复claim仍拒绝。该场景覆盖本次真实缺陷。 |
| 保存记录与绑定 | precheck04为28/28，全部保存依赖哈希与当前一致；入口已切换至precheck04及ready02.json。旧precheck02／03和ready.json保留，不覆盖为新版本。 |
| 上次R1 | 冲突跨外层超时保留及后续探针冲突判定未撤销，新记录继续通过相关检查；迟到U仍不可接纳。 |

文件存在状态独立核对：results/diagnostic01不存在，state.json.tmp不存在，旧ready.json存在，新ready02.json尚不存在。此时formal_run_count=0、revision_count=2，与主线自查说明一致。原物理参数、精度、28次独立20秒和不自动重跑边界未变。

## 审查绑定

- run.py：`0daea5cb8c52b18d71e2ba15109c930bc6a3f32e3978b1375a4450454cf6ab21`
- precheck.py：`2063d29746809d49d6a482b18eac1f7bb869627b25500c53f940f07cb3d906d3`

完成新准入记录及状态绑定后可按原协议执行一次；本复审不授权追加运行、更换结果目录绕过claim或扩预算。下一次审查针对实际保存结果。
