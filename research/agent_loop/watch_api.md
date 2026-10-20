# 只读审批检测接口

`monitor.py` 是检测器，不执行审批门、不消费批准、不运行提案、不创建审查、不唤醒 ChatGPT。任何输出都不授予研究或实验执行权限；`real_experiments_started` 始终为 `false`。

```text
python -B research/agent_loop/monitor.py
python -B research/agent_loop/monitor.py --repo-root <仓库根目录> --output <显式输出文件>
```

默认只向标准输出打印 JSON。`--config` 默认 `research/agent_loop/config.json`，`--requests` 默认 `research/agent_loop/requests.json`；两者均为仓库相对路径。`--output` 是唯一显式写文件接口，Actions 将其指向运行器临时目录。状态为 `STOP` 或 `UNRESOLVED` 时退出码为 2，其余为 0。退出码 0 仅表示检测完成。

Python 接口：`detect(repo_root, config_path=..., requests_path=...) -> dict`。调用只读工作树文件及 Git 对象，不修改工作树、索引或历史；不访问网络。Git 调用仅限读取固定对象的 `cat-file -t` 和 `show <完整提交SHA>:<相对路径>`。

| status | 含义 |
|---|---|
| `UNPUBLISHED_WAITING_REVIEW` | `subject_commit_sha=null`，尚未发布不可变审查对象 |
| `WAITING_REVIEW` | 缺少 JSON 审查；仅有 Markdown 也继续等待 |
| `APPROVAL_REQUIRES_MACHINE_GATE` | 存在绑定相符的 `APPROVE_ONE_STEP` 声明；签名、身份、范围、预算、有效期仍须由独立执行门验证 |
| `REVISE` | 索引或未验证审查声明要求修改；不继续执行 |
| `STOP` | 停止声明、绑定变动、配置/索引读取失败等；不继续执行 |
| `UNRESOLVED` | 单轮读取不全、损坏 JSON、无效路径或未知决定；不继续执行 |
| `NO_ROUNDS` | 索引为空；未启动任务 |

顶层包含 `schema_version=1`、`detector_only=true`、`machine_gate_required=true`、`real_experiments_disabled=true`、`real_experiments_started=false`、`chatgpt_woken=false`、`review_generated=false`、`reasons` 和 `rounds`。多轮时取最保守状态：`STOP > UNRESOLVED > REVISE > UNPUBLISHED_WAITING_REVIEW > WAITING_REVIEW > APPROVAL_REQUIRES_MACHINE_GATE > NO_ROUNDS`。

单轮记录包含 `round_id`、`subject_commit_sha`、`status`、`reasons`、`bindings` 和 `review`。`review.verified` 始终为 `false`。未经验证的 `STOP/REVISE` 只会使系统更保守，不构成可信审查身份结论；`approved=true` 无效。

`requests.json` 使用 `schema_version=1` 和 `rounds` 数组，每项包含 `round_id`、`subject_commit_sha`、`manifest_path`、`status`。subject 必须为完整 40 位小写 Git 提交 SHA。manifest 从该提交读取，绑定 proposal、report、source_files、evidence_files 与 config 摘要，并核对工作树当前内容。后续只新增审查文件导致 HEAD 变化，不影响原 subject；绑定内容发生变化则原声明不再可用。

审查定位为 `research/agent_loop/reviews/<round_id>/<subject_sha>.json`，可附同名 `.md`。检测器不会创建这些文件，也不会将签名存在性等同于验签成功。JSON 存在时只核对声明的轮次、subject、manifest、proposal、report、配置、仓库、模式及证据类别；剩余条件全部留给执行门。

Actions 仅检出默认分支的受信代码与数据。PR/review 事件触发重新检测默认分支，不检出、不执行 PR 分支脚本，也不把 PR 评论当批准。新审查文件须进入默认分支后才能在此产物中出现。计划间隔配置为每 15 分钟；实际运行时间与是否产生运行记录由 GitHub 调度决定。静态配置不等于已经实际触发。

单测命令：`python -B -m unittest discover -s research/agent_loop/tests -p test_monitor.py -v`。Windows 沙箱如不能写默认临时目录，可设置 `AGENT_LOOP_TEST_TMP` 为已有可写临时目录。测试只在 `TemporaryDirectory` 中创建隔离的 `TEST_ONLY` Git fixture，既不创建真实审查，也不启动研究调用、MATLAB、LP/MILP 或热实验。
