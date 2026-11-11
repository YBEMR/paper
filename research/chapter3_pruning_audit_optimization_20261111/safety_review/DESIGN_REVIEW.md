# 严格认证模板缓存：设计只读审查

这是实现前的条件审查，不是新实现验收通过。未修改生产源，未构模、求解或热评价。

严格性依据：若两个调用在同一冻结导出器和数值上下文下，源/目标/门的列别名布局、实际binary64变量盒、五组全部区间系数端点文本完全一致，则原10条门控外包行在列重编号后相同。第一次调用按原导出器生成行，并按实际binary64盒做精确有理数门关闭检查；不可变证书可在以后相同键的调用中复用。该推论不把容差替代精确检查，也不要求每个hit重复相同Fraction求和。

必要键和失效条件：

- 系数包含全部lo/hi文本，保留符号零和指数表示；不能只用state/duration或浮点近似系数。
- 实际导出float盒和原内部rational盒若二者均参与导出，应共同绑定；source/target/gate顺序及列别名模式不可丢失。
- 源码身份覆盖真实行导出调用链与interval kernel，不能只覆盖_audit本身。若承诺运行时函数改变失效，需覆盖相应函数身份；否则必须明确冻结运行假设。
- UP/DOWN Decimal Context的precision、rounding、Emin/Emax、clamp、capitals、traps纳入身份；sticky flags一般不影响数值。
- 每Model冷缓存，输入身份绑定；不从历史结果或磁盘免费warm。源或上下文变更清空cache，并在下一miss完整重认证。
- probe按不可变盒/布局复用；若改变盒却不清_bound_*、_affine_templates、_conditional_templates等内部缓存，复用不安全。
- miss完整原导出与Fraction核验，任何正违反均拒绝，不能以1e-9放行。hit返回不可变证书的独立报告副本，避免后续state修改污染cache。
- 报告分别列直接认证模板/行和复用代表的状态/行；源码hash、key构建、cache/probe建立和失效成本都计入真实构模成本。

已识别需覆盖的边界包括：别名导致原affine_conditional_eq进入dictionary overwrite fallback；上下界的外包变化；Decimal上下文或运行时导出函数变化；仅tag/列名变化而数值模板相同；源文件同时间戳修改的身份假设；缓存条目被外部篡改。任意并发语义突变不应被默认为已覆盖，正常证明以冻结单线程模型构建为前提。
