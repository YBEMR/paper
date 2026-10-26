# K193：小域精确参照协议的纯准备

本目录仅生成静态覆盖清单、检验能量包络规则和whole参数转发。**没有真实运行入口**，不能启动热枚举、MATLAB或优化。

- `contract.py`：独立枚举1550个静态合法场景；与生产选项和合法性检查对照；对假定已接纳的记录计算有理数包络。它不认证真实热回执。
- `test_contract.py`：10项纯检查，覆盖清单缺项／重复、未决不能作U、同设备配对、权重一次计入、不可行／ε结论及并列边界。
- `whole_forwarding.py`：走原`formal→warm`函数链，底层方法、构模器和原生会话均为替身；证明参数及输入转发，不构建数值模型。
- `prepare.py`：写入独立新目录，生成`authorized=false`协议和确定次序的1550条清单；不覆盖现有目录。

纯检查：

```powershell
& 'F:/Anaconda3/python.exe' -B 'research/chapter3_experiments/small_exact_preparation/test_contract.py'
& 'F:/Anaconda3/python.exe' -B 'research/chapter3_experiments/small_exact_preparation/whole_forwarding.py'
```

[已生成凭据](../results/small_exact_protocol01/protocol_proposal.json)。一次性科研执行器、真实回执的内层截止接纳、账本／监督及原生身份冻结仍待获批后实施验收。重复纯检查不运行科学评价，也不授予真实预算。
