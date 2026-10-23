# H02同真值H/R响应消融：阶段A

状态：**薄接口、静态合同及mock预检完成；正式研究调用0，新真实SAFE 0。阶段B未授权。**

本目录位于独立实现分支`codex/h02-stage-a`，固定主线`20fb232a81d69782b8ebd1fc1972a6bc96fff09e`、探索协议`f63cc4f8c5ceb7161a15ce55c6cf610081482f30`。不包含真实HEFT／MILP／热评价执行入口，不修改主线物理参数或数学核心。

## 三个接口

| 接口 | 已实现范围 |
| --- | --- |
| `paired_response_input_view(problem_id, source_sha)` | 仅从冻结H/base构造R1/R2；真H、规划H、规划R为独立副本；精确Fraction重算R；逐字段白名单、支持和物理投影审计 |
| `paired_heuristic_entry(packet, MockBackend, registry, slot, truth_sha)` | 只接受显式mock后端；R loader仅捕获公开R字节；固定HEFT／auto-L／seed=None参数；核对原Recorder.best；冻结唯一候选和身份 |
| `truth_H_post_audit(token, truth, binding, MockAuditBackend, registry)` | 单次mock后验；根预算先于哈希、解析；候选不修复、不移位；完整场景／热能量回执检查；异常锁STOP且禁止回传规划 |

`StageARegistry.bind_pair(pair)`从固定源码重新核对真值，并把公开packet与实际P1/P2静态合同绑定；不能自行改参数、重算hash后绕过。Registry只在控制端，不能传入R搜索器。全部mock输出带`MOCK_ONLY`、`usable_as_research_evidence=false`；模拟`TRUE_H_SAFE`不是新科研SAFE。

## 可复跑检查

在本独立工作树根目录，使用Python标准库：

```powershell
python -B research/chapter3_experiments/h02_pair_preflight/run_precheck.py
```

入口执行纯输入／代数核对及121项unittest。真实搜索、调度合法性计算、热传播、下界和求解器函数均受阻断守卫保护；测试原始`execute_heuristic`时显式替换search、validator、evaluator及两个下界别名。所有失败、通过和人工中断的预检记录均在`evidence/precheck_attempts/`保留，不将旧PASS当新结果。

R-only子进程测试独立目录／空缓存、拒绝读取封存H和原配置、拒绝真实算法导入及H后验反馈。**这是Python应用层访问守卫，不是OS安全沙箱。** 测试不等于已验收真实研究工作进程。

## 证据入口

优先看[evidence/stageA_review.md](evidence/stageA_review.md)。A6七项工件均在`evidence/`：源码身份、输入差异、静态合同、mock测试、适配器源码清单、内部审查报告、零调用账本。`protocols/`保存三份已核原文的精确字节快照。

## 完成边界

阶段A只核对静态／mock合同。未运行真实HEFT、真实连续热评价、MILP或任何节能实验；未取得研究安全方案、节能率或算法排名。后续须由用户安排外部独立协议审查，并另行批准阶段B四槽及预算；真实backend、计费内输入构造／交接、实际墙钟监督及worker权限仍须在该阶段冻结，不能把本目录mock后端直接当正式执行链。
