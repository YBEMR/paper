# 命令与读取记录

工作目录 `/workspace/paper`，当前checkout仍为 `052c0b01c9a840c2b5b6ff8018afcaf08654a24a`，分支 `chapter4/r2-r5-validation-20261107`。原结果从固定提交2fc52c6直接读取，没有checkout/pull或修改Git历史。工作区已有改动保持原状，本轮新增文件仅在本目录。

先通过GitHub连接器读取固定提交及结果目录，解析出该提交的raw下载地址。连接器不支持13.69MB二进制文件下载，随后使用当前Cloud已允许的raw.githubusercontent.com正常HTTPS读取，未添加凭据、替换代理或绕过限制。

实际主要命令：

```bash
git status --short
git log -1 --format='%H %D'
python3 research/chapter3_native_log_review_20261111/github_verified_run01/fetch_and_verify.py
python3 research/chapter3_native_log_review_20261111/github_verified_run01/analyze_records.py
```

下载命令完整argv保存在 `download_record.json`；为 `curl --fail --silent --show-error --location --max-time 60 --output <本目录ZIP> <固定提交raw地址>`。fetch脚本只下载、哈希、安全路径检查和解压，不执行包内内容；原始ZIP保存于本目录。两个脚本使用创建新文件模式，拒绝覆盖既有输出；复核现有结果不需要重跑。

另执行了若干 `python3 - <<'PY'` 的只读片段：标准库json读取result、events、plan、controller、session/closed/response及初解收据；zipfile读取冻结源码并给出行号；hashlib核对工件。独立矩阵审计使用 `scipy.io.loadmat` 仅读已有request/native MAT，计算 `A @ x0 - b`、等式/边界/整数残差和 `c @ x0`，没有调用MATLAB或研究模块。首次按UTF-8读取MATLAB日志失败，随后按GB18030成功解码；原字节未改。

本机真正执行的命令从原 `raw/local_records/controller_start.json` 读取，下列仅引用，没有在Cloud运行：

```text
F:\Anaconda3\python.exe -B F:\by\11111\R1_native_pair_20261110_run01\research\chapter3_support_local_migration_20261110\run_local_pair.py run --run --plan F:\by\11111\R1_native_pair_20261110_run01\local_records\r1_local_plan.json --output F:\by\11111\R1_native_pair_20261110_run01\local_records\r1_pair_run01
```

本轮另读取MathWorks R2023b两份官方文档，核对rootlp/heuristics、callback.time和relativegap的定义。没有检索新的算法方案，没有新求解、构模、热评价、参数扫描、提交或推送。
