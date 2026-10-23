# K172：loader合同文字澄清补充核查

**通过，原9项审查结论保持。** 当前protocol仅在§4增加一句：薄loader解包`fresh_input`的`raw, config, instance`，再向方法返回`config, instance`。移除该句后，文件字节hash精确恢复原审查绑定的protocol hash；其余审查输入hash全部未变。

该澄清符合原代码：`p0_batch/run_p0.py:72`返回三个值，`neighborhood_method.py:476`按两个值接收loader。没有改变算法、输入、预算、导入时钟或科学源，也不将待批方案变为执行授权。

- 当前protocol SHA：`3c9339127789f97da0f77518773dfd2d9615e0d0445c90111209077f1f603cad`。
- 原protocol SHA：`e8ffad60b334627e2e63e3d53663cc2a1e588ca2787767475aa3af73728163a0`。
- 原独立审查JSON SHA：`3075f4f26e8d7dba0667e973dd6dca094302eb9e0951f1d7e3b59643b4f2802b`。

原`proposal_review.md/json`未覆盖。可继续绑定当前协议提交准备材料；真实启动器仍须另行冻结和验收。本次0研究调用。
