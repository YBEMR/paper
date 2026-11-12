# 完整 auto-L R1 剪枝配对：冻结 Windows 交付包

本包用于现有 GitHub 工作分支与 Windows Work 的文件交接。ZIP 原样保留，不依赖本机主仓库是否已有最新剪枝提交。没有包含 MATLAB 许可证、访问令牌或 Library 账户元数据。

- 原科学源码基准：`fa8e8de0166c1ee8d0ffaaa447122ba8f69014b3`。
- ZIP：`R1_pruned_native_pair_20261111.zip`，1,042,596 字节，227个文件。
- SHA256：`a219ea08f1d10f4e75781690605bdc4fec6f0c5619c87b2cac7545f2d509d685`。
- 包含217份原科学源码、完整输入、专用入口及预算适配、22项通过的模拟测试凭证和Windows说明。未包含已执行的正式配对结果。
- 两组均 `propagate_support=True`，仅 `prune_joint_states` 关闭/开启；各一次完整方法调用、各300秒总预算。初解各自现场生成并核验，仅交叉比较身份哈希，不复用历史SAFE。迟到结果不计入预算内结果。
- probe、OFF、ON使用独立 MATLAB 偏好目录，两组严格串行。已知目标可用内存约2.51–3.02 GiB；原生峰值未知，内存不足应保留失败而非扩大预算或重跑。
- 目标为MATLAB R2023b。Windows Work已报告Python3.12.4、NumPy1.26.4、SciPy1.13.1；本包测试在Cloud运行，不冒充目标机器原生验收。

## 获取与校验

从本目录的ZIP文件页面使用Raw/Download下载，或在取得本次实际提交号后使用对应raw.githubusercontent.com固定提交链接。检查 `SHA256SUMS`，然后解压至新的可写目录，勿覆盖旧结果。

```powershell
Get-FileHash .\R1_pruned_native_pair_20261111.zip -Algorithm SHA256
Expand-Archive .\R1_pruned_native_pair_20261111.zip -DestinationPath .\R1_pruned_native_pair_delivery01
```

进入解压出的 `R1_pruned_native_pair_20261111` 根目录，阅读：
`research/chapter3_pruned_native_pair_delivery_20261111/README_WINDOWS.md`。

```powershell
$entry = "research/chapter3_pruned_native_pair_delivery_20261111/run_pair.py"
python -B $entry verify
python -B research/chapter3_pruned_native_pair_delivery_20261111/test_entry.py local_precheck01
python -B $entry probe --matlab "F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe" --out local_probe01
python -B $entry freeze --probe local_probe01/environment_receipt.json --plan local_pair_plan01.json
```

probe只启动/关闭MATLAB桥，不调用MILP。目标检查通过后才按既有授权执行一次：

```powershell
python -B $entry run --plan local_pair_plan01.json --out local_pair_run01 --execute > local_pair_run01.stdout.log 2> local_pair_run01.stderr.log
```

这次GitHub交付本身没有启动probe或正式实验，没有修改原科学文件或合并main。主机无依赖、入口检查失败、初解身份不一致或清理异常均应停下并报告，不自行重试或换求解器。
