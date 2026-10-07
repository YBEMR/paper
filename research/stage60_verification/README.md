# 60号解析证书核验

本目录验证59号四个既有冷态输入的下界与完整安排，不运行调度器、候选搜索或55号基线。数值仍为53号L3输入。

PowerShell运行（工作目录 `F:\by\11111`）：

```powershell
$env:MATLAB_PREFDIR='F:\by\11111\.runtime\matlab_prefs'
& 'F:\Matlab2023\Program_Files\MATLAB_R2023b\bin\matlab.exe' -batch "addpath('F:/by/11111/research/matlab_config_value_src'); run_certificate60"
```

每次创建独立时间戳目录，保留源码、输入、协议、哈希、CSV／JSON／MAT和日志。运行需要53号冻结JSON以及55号既有D6冷态联合无热JSON见证，不读取其热参考提示来选择新方案；本入口本来就是已知证书核验，不是自主策略。

通过目录为 `run_20260925_210740_491`，261项检查通过。前一目录为结构体保存失败记录，不删除。最优值与完整最优集合分开，后者本轮未枚举；核验耗时不能拿来与完整搜索比较。
