# 53号冻结包

本目录保存53号用户批准的L3输入及比较协议；只有静态结构和代数检查，**没有实验结果**。

- `inputs_v1.json`：8主例＋2独立校验；packages是替代输入包，不是可混用的NPU频率档。cases引用package_id，A/B共用Stage模式表。所有时间s、功率W、能量J；resource_set为抽象固定执行资源标签。
- `rules_v1.json`：同域比较、代表覆盖、容差、排序、60 s总预算及未决语义。
- `freeze_manifest.json`：输入、规则、生成审计脚本和保护清单哈希；生成先于代数检查。
- `static_checks_v1.json`：75项检查、解析RC量和冷态统一上界；不是热轨迹或策略结果。
- `protected_before.json`：1,030项历史文件哈希；`delivery_audit.json`复核交付后的完整性。
- `freeze_and_check.py`：生成输入与静态核查的记录，不是MATLAB运行入口。已有任何冻结输出时拒绝覆盖；不要为重跑删除它们。

只读核验命令（仓库根目录PowerShell）：

```powershell
$manifest53 = Get-Content research/stage53_design/freeze_manifest.json -Raw | ConvertFrom-Json
$manifest53.files.PSObject.Properties | ForEach-Object {
    $actual53 = (Get-FileHash -LiteralPath (Join-Path 'research/stage53_design' $_.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
    [PSCustomObject]@{ File = $_.Name; Match = ($actual53 -eq $_.Value) }
}
```

未来方法只读输入和规则，不以静态检查结果或参考见证提示候选选择。输入与规则更正须新版本、原因和哈希；不据是否产生收益改参。冷态上界不保证60 s内完成规划。暂无八Stage调度器，不能运行H52实验；下一项先制定实现与预检任务。
