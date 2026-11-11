# 严格门关闭认证模板复用实现

优化已真实实现，最终为正确性修复后的rev2，仅改正式 `research/chapter3_experiments/milp.py` 的审计helper路径并新增cache身份/清理helper及容量常量。`joint_state_support.py`、完整Model类、build_model和能量强化生成器AST均保持原样。没有改变剪枝规则、矩阵行导出算法、原变量盒或物理系数。

## 严格性与缓存键

每个原Model第一次非空审计建立独立冷缓存，容量 `_GATE_AUDIT_CACHE_LIMIT=4096`。没有磁盘加载、跨模型或跨运行warm cache。首次miss仍以原Model.affine_conditional_eq构造原双向行，再调用原verify_gate_off_rows在实际binary64盒上逐行Fraction精确最大化；任何正违反仍抛出异常，只有完整通过后的不可变scalar proof tuple可发布到cache。

完整key分为以下部分，实际key在每个Model的 `preprocessing['joint_state_pruning']['audit_certificate_cache']['template_catalogue']` 逐项记录：

1. 源码/输入/数值环境namespace：milp.py、joint_state_support.py、milp_coefficients.py、thermal.py、thermal.KERNEL_PATH的内容SHA256；model.input_sha256及当次实际 `_digest(model.instance)`；实际interval内核UP/DOWN及thermal别名各自prec、rounding、Emin、Emax、capitals、clamp及traps。sticky flags不影响数值结果，不参与key。
2. 有序source/target角色数量、所有变量别名等价布局、实际lb/ub的float.hex及内部Fraction盒文本；gate固定原[-0.0,1.0]导出盒，并实际断言匹配。
3. 所有温度行及能量行的完整有序系数interval端点lo/hi文字，含常数项，不以近似数、频态标签或仅持续时间代替。

同key的源/目标列只是重编号，别名及插入顺序相同，原导出器产生同binary64条件行及RHS；同盒下门=0的最大残差完全相同，因此hit复用已证明的严格证书而非跳过认证。每个hit返回proof拷贝，不能通过返回报告修改内部不可变证书。probe也仅在完整box/layout相同下复用，绝不原地改probe盒并保留旧缓存。

## 失效与重新认证

每个非空audit边界重新计算实际输入摘要、数值context和相关Model/I/验证器实际callable引用。先核查I相关运算函数的globals正是已认证kernel.__dict__，不符合即拒绝；实际kernel.UP/DOWN及thermal别名四context对象身份与算术属性均纳入，kernel-only重绑定即使留下旧thermal别名也会失效。正常源文件stat变化、函数对象替换、输入身份或context变化均清空性能缓存并重建namespace；被替换对象以强引用保存，避免仅id整数被复用。source namespace保存内容哈希，普通函数替换即使文件字节未变也使用新本地generation。

`_clear_joint_state_gate_audit_cache(model, reason='explicit')`清空entries和probes，下一miss必须再走原严格认证。超过容量也清空并重认证。累计成本和完整证据journal保留用于追溯，但journal不作可读取的warm cache。此机制基于冻结、受控单线程构模；不承诺检测恶意原地篡改函数__code__或内部私有cache对象等任意运行时攻击。正式任务以完整源hash冻结及前后检查约束运行。

## 成本和可审计字段

原每state `states_checked`、`rows_checked`、原proof精确slack等字段保留；新增certificate_cache_hit/template_sha256。`rows_checked`表示被严格证书覆盖的原行总数，**不是本次实际做Fraction循环的行数**；后者在stats.strict_rows_evaluated单独记录。该区别避免把cache代表行数误报成全部逐条重新计算。

cache_snapshot记录累计misses/hits/clears/identity_invalidations、states_represented/rows_represented、strict_rows_evaluated、prepared_probes；成本字段为preparation_s/key_s/probe_prepare_s/export_s/verify_s/cache_hit_s。完整缓存初始化、源码/输入哈希、key构造、系数读取、每次miss准备和所有字典/日志开销全部在原joint_state_gate_off_audit计时区域内；子计时覆盖部分明确阶段，不可拿它们之和取代总区域实际墙钟。没有提前建立免费缓存。

## 已执行与未执行

已做AST/源hash对照及一次纯合成模板helper烟测：一个miss后同key hit，显式clear后重新严格认证，以及已有缓存时验证器替换为预设拒绝Mock，均通过并传播预期ValueError。该检查只创建小型导出行探针，不构造调度模型或评价物理方案；实际起止、耗时和源码hash见pure_smoke.json。

本子任务没有完整R1构模、调度模型构建、LP/MILP或物理评价。独立完整测试及一次冻结静态配对由主代理/验证分工在源稳定后执行，不将此实现检查冒称验收或性能结果。

修改前后快照为milp.py.before/milp.py.after，差异见milp_changes.diff；new_audit_functions.py.txt是最终helper摘录，开始/完成及hash见start.json/completion.json。正式milp SHA256：`98c1ad5735d06e07ad8cb89e8f90e99542c1a1142ef2e7b42439fa47d5eec182`。

## 保留的正确性修订

rev1 `64cac462...`最初仅读取thermal.UP/DOWN别名，安全审查发现：仅重绑定kernel.UP/DOWN而保留旧别名时可能漏失效。主代理要求修复；确认rev1验证子进程全部退出后才修改源。旧源码保存在milp.cache_rev1.py、原完成记录completion.rev1.json，问题及rev2 hash见correctness_revision.json。rev2新增真实算术globals/context绑定，不是为性能结果调参。纯helper检查kernel-only rebind后miss及严格认证次数增加，通过；实际命令和时间见check_audit_cache_smoke.py与pure_smoke_rev2.*。rev1独立测试即使曾通过，也不能替代修复后验收，由主代理保留并在预算内重冻结验证。
