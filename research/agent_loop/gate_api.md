# 审批门禁接口（v1）

本模块只验证审批、争用远端账本并返回已计费许可，不执行研究代码，不提供签名私钥、solver、后台重试或真实进程执行器。生产配置保持关闭；本轮验收数据全部为 `TEST_ONLY`。

## 调用顺序

```python
gate = Gate(repo_path, config_path, mode="real")
claim_id = gate.claim(review_json_path,
                      requested_action="与提案action_id相同",
                      requested_scope=["批准范围内的相对路径"])
# 只有REAL_EXPERIMENT类型的动作可能取得研究调用许可。
permit = gate.issue_permit(claim_id,
                           requested_action="与提案action_id相同",
                           requested_scope=["批准范围内的相对路径"],
                           budget_seconds=明确秒数)
# 本轮没有执行步骤。将来的受控执行器必须在实际启动点复核并落实超时。
gate.finish(claim_id, outcome="IMPROVED")
gate.close()
```

`finish` 的 outcome 必须明确为 `IMPROVED`、`NO_IMPROVEMENT` 或 `FAILURE`。门禁只计数，不判断研究是否改善。`stop(reason)` 只设置永久 STOP。没有 reset、退款、重试或自动恢复 API；意外残留 RUNNING 会阻断后续 claim。`ANALYSIS_ONLY` 必须分配零研究调用、零调用预算和零总调用预算，不允许申请调用 permit。

## 配置

配置原始 UTF-8 字节的 SHA256 必须等于外部环境 `AGENT_LOOP_TRUSTED_CONFIG_SHA256`。授权值须来自仓库之外的可信配置流程，执行代理不能把仓库里刚计算的摘要自行当作授权。生产 `mode="REAL"`、`test_only=null`，所有必要数值明确配置后才可能准入。缺失、null、布尔数值、NaN、重复 JSON 键均拒绝。

| 字段 | 契约 |
|---|---|
| schema_version / mode | `1` / `REAL` 或 `TEST_ONLY` |
| enabled | 默认 `false`；控制所有自动准入 |
| ALLOW_REAL_EXPERIMENTS | 默认 `false`；生产研究调用额外要求 true |
| activation | REAL 必须同时具备 `real_runner_installed`、`external_review_identity_verified`、`external_review_writeback_verified`，且值均为 true；生产默认 false，本轮未安装真实 runner |
| repository | `remote_url`；生产 `ledger_ref="refs/heads/codex/agent-loop-ledger"` |
| review_source | `source_id`、`key_id`、`public_key_ed25519_base64` 默认 null；`github_login` 仅描述来源，当前两方同为 YBEMR 不构成隔离 |
| limits | `max_rounds`、`max_calls`、`per_call_budget_seconds`、`total_budget_seconds`、`wall_clock_limit_seconds`、`deadline_utc`、`max_consecutive_failures`、`max_consecutive_no_improvement`；初始 null，当前以用户明确授权后的 config 为准，真实运行前提仍未通过 |
| allowed_scope | 非空、唯一、规范的仓库相对路径前缀；不允许尾斜杠、反斜杠、绝对路径、`..` 或 `.git` |
| test_only | 生产为 null；测试为 `{namespace:"TEST_ONLY-...",temporary_root:"专用测试子目录"}` |

生产 activation 标志只是额外前提，不能替代独立签名与受控执行器验收，也不证明其它旧 CLI 无法绕过。任何可能从执行端取得的审查私钥都不满足独立审查要求。代码没有能力证明某个公钥的私钥不存在于本机；密钥保管和外部配置锚属于运维信任边界。

## 固定 subject manifest

manifest 存在于完整 `subject_commit_sha` 对应的 commit 中；subject 必须为 commit 对象，不能用 tree SHA。manifest 自身原始字节 SHA256 存在审批中。字段：

```text
schema_version, mode, repository, config_sha256, round_id,
proposal_path, proposal_sha256, report_md_path, report_md_sha256,
evidence_class, source_files:{path:sha256}, evidence_files:{path:sha256},
proposed_action:{action_id,action_kind,allowed_scope,max_calls,
  per_call_budget_seconds,total_budget_seconds,wall_clock_limit_seconds}
```

`action_kind` 为 `ANALYSIS_ONLY` 或 `REAL_EXPERIMENT`；`evidence_class` 为生产 `REAL_REVIEW` 或模拟 `TEST_ONLY`。提案、研究报告、源码、输入和证据均核对 commit 字节及当前工作树字节；HEAD 仅新增审查文件不自动使 subject 过期。未列入 source_files/evidence_files 的文件不受摘要绑定，未来执行器必须保证实际用到的代码与输入已完整声明。

## 审批 JSON 与审查 Markdown

必需字段：

```text
schema_version, mode, repository, config_sha256, approval_id, round_id,
subject_commit_sha, manifest_path, manifest_sha256, proposal_sha256,
report_md_sha256, evidence_class, decision, approved_action, action_kind,
allowed_scope,max_calls,per_call_budget_seconds,total_budget_seconds,
wall_clock_limit_seconds,expiration,
review_identity:{source_id,key_id,reviewer_id,github_login},
review_report_path,review_report_sha256,
signature:{algorithm:"Ed25519",value_base64}
```

decision 只能是 `APPROVE_ONE_STEP`、`REVISE`、`STOP`。`approved_action` 等于提案 action_id；action_kind、允许范围和四类预算与 proposed_action 完全相等，再由配置上限约束。expiration 和 deadline_utc 都采用以 `Z` 结尾的 UTC 字符串。

`report_md_sha256` 是研究报告；`review_report_sha256` 是另一段 ChatGPT 独立写回的审查 Markdown，两者不能互代。生产审查 Markdown 位于 `research/agent_loop/reviews/`，JSON 与 Markdown 必须同目录；本实现从不写入该目录。每次 permit 前后复核审查 Markdown、受审文件、配置及时间。

签名消息为 ASCII 前缀 `agent-loop:REAL:v1\0`（模拟为 `agent-loop:TEST_ONLY:v1\0`；末尾为一个 NUL 字节）与去除 signature 字段后的 canonical JSON 拼接。JSON 使用 UTF-8、`sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False`。REAL 拒绝 TEST_ONLY 模式、证据类、source/key/reviewer 标识，即使开关误开。未安装 cryptography 时拒绝验签。

## 远端一次性与配额

GitLedgerStore 在独立临时裸对象库读取远端 head，构造唯一 nonce 的 child commit，通过普通 fast-forward push 争用。无 force、删除 ref 或自动重试；空 ref 首次创建和已有 head 并发争用均只有一个成功。网络结果不明时不返回 permit，已成功的预留可能永久保留。

claim 在返回前已永久消费 approval_id/round_id，预留整轮调用数和总调用预算并置 RUNNING。permit 在返回前计费整次预算。账本保存累积轮数、调用预留、时间预留、已发许可、截止、失败/无改善计数、RUNNING 和 STOP。历史读取验证线性父链、sequence、previous_state_sha256、消费集合单调、不可变 review 及许可前缀，拒绝 FF 历史中的清账和回退。

总墙钟从首个获批 claim 的时间起连续计算；账本固定 `run_started_utc` 与 `run_deadline_utc`，后一轮或新进程不能重置。每轮期限取全局墙钟期限、绝对截止、审查过期与本轮墙钟上限的最早值。

该账本需要服务器保留 ref 与历史。同账号管理员仍能在门禁外重写/删除整个分支；没有分离的服务器权限和外部单调锚时，不声称抵御仓库管理员恶意重建账本。签名审批仍须独立来源。共享工作区在函数返回后仍可能变化，未来执行器须在实际启动点再次验证并落实进程截止；本轮的 permit 不能终止进程。

## 隔离验收

默认测试根为项目 `.runtime/agent_loop_tests`；也可通过外部 `AGENT_LOOP_TEST_TMP` 指定允许根。测试配置必须指向该根的专用子目录，repo/config/本地 remote 全部在其中；ledger ref 必须为 `refs/heads/TEST_ONLY/<namespace>`，审查文件只写该临时 repo 的 `TEST_ONLY-reviews/`。测试私钥只在测试进程内存中存在，清理临时仓库后不保留。主仓库 Git 和真实 reviews 均不写。

```text
python -m unittest discover -s research/agent_loop/tests -p test_gate.py -v
python research/agent_loop/tests/test_gate.py --e2e
```

第二条向 stdout 输出完整 TEST_ONLY 事件序列及环境失败记录，可由验收方归档。Windows 沙箱若阻断 MSYS 本地 Git transport，应明确记录环境失败；需要自动审查通过的、仅针对这些隔离测试的提升权限运行，不能伪造通过结果。
