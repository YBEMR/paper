# 研究状态

更新：2026-10-22。

**K.170／D195：部分赋值下界接口与安全剪枝纯预检完成（E615）。** [总报告](research/chapter3_experiments/results/partial_bound_precheck01/summary.md)、[接口合同](research/chapter3_experiments/conditional_energy_bound/README.md)、[最终run05](research/chapter3_experiments/results/conditional_energy_bound_precheck01/run05/checks.json)、[稳定探针/成本run02](research/chapter3_experiments/results/partial_bound_precheck01/review/probe_cost_run02/results.json)保存。新增standalone prepare/bound/原P0 U只读接纳/严格剪枝判读；未接生产，原参数/数学/热安全保持。bounds锁定9b4fc402…de02c6e0a，19项独立数学/身份核对及9组纯预检通过。

保留共享Stage所有场景/请求副本的具体设备一致，OPP逐副本；未知/冲突拒绝无界，不当原问题无解。新界max(legacy条件界,容量分摊完整界,forced驻留完整界)，背景/活动源分解及CPU M/H差分不重计。无安全U不剪；仅LB>同输入既有完整安全U时排除更优延伸，等号保留并列。

固定490项后验条件中255能量排除；扣普通期限与派生旧界后新增187，其中66处于当前联动设备层兼容范围，仍不等于实际开放或已访问。forced比capacity再排22项（设备层兼容11），未被旧界/期限覆盖。R1 AB B.post CPU2/H：capacity .859641815453≤原U .860663343334，forced .860691815453>U约28.472µJ。单列3H链forced比capacity提高16.625mJ，属旧联动设备层外。

固定3次算术成本：各题prepare+root中位8.72—11.80ms，98条件bound+判读116.95—137.00ms；旧U读取/hash另计，不当方法总耗时或加速。人工64组模式标签ledger与部分赋值无高估，未生成调度/热轨迹；早期夹具缺字段、旧源码及一次成本源漂移失败均保留，不作最终凭据。

下一项助手建议只读回放原P0每次build时的同次已成完整U与实际局部模式域/闭锚/原过滤，判断是否真有及时可删项；若有再讨论构模前筛选接线，否则保留质量界、停止生产筛选投入，不新建B&B。此建议尚未变成实施授权。本轮0优化/模型构造/热积分/正式候选/新研究调用，无新U；原253源及旧结果保持，期限16/24、K168pending不变。新增.py可能影响未来发现式源清单，K168执行前须重核，不能复用旧准备称已可run。以下K169及更早为历史。


**K.169／D194：主线C12型机制与C17型独立下界零调用审查完成（E614）。** [总报告](research/chapter3_experiments/results/mainline_mechanism_audit01/summary.md)、[C12账本](research/chapter3_experiments/results/mainline_mechanism_audit01/c12/summary.md)、[C17证明与五题事实](research/chapter3_experiments/results/mainline_mechanism_audit01/c17/summary.md)保存。依据主线ee26af7及P0原H／50°C／80°C、AB/AC、400ms/5ms、四节点、auto-L；只读pilot最新a8ecd41，不合并五节点模型。

C12：4张R3完整安排通过资源／期限／频域及跨场景共享映射检查，完整边际能量代价随CPU高档覆盖改变；18对CPU/GPU参考模式差没有严格跨零。尚未认证正负排序翻转或80°C连续热安全，不产生SAFE/U；原B.main在主线无GPU且无U源，原例不能照搬。

C17：原L0已含域功率底值与逐Stage活动min。以既有初温重导可统一提高0.11264 J；最低基准注热及期限源响应后，R1—R5事后界为0.856570240361／0.855067034496／0.858038063758／0.860483735438／0.852611555851 J。与原存档最佳U差/U约0.4756%／0.4889%／0.4886%／0.4782%／1.2932%；不是新求解结果或最优证明，未回填旧L0/gap。条件CPU驻留／DAG链界有效，但五题根级工作量与共享部署附加强化均0，不重复收费。

主线原模型已表达上下文功耗；完整MILP/HEFT/SA已有设备选择，正式联动版则在seed前固定共享A部署CPU1/NPU0/CPU1，二遍只改域内OPP/起点。新界尚未接生产或证明搜索收益。下一项仅建议讨论同模型下界接口与具体分支剪枝的纯检查，再决定是否有必要另批界开／关配对；不直接补跑或换模型。

本轮0研究构模／优化／热积分／正式候选评价／实机，原源码与旧结果保持；K168仍待确认，期限16已消费／24未启动不变。以下K168及更早为历史。


**K.168／D193：beta_1.0__R2整体增广原生技术诊断准备完成，等待预算确认（E613）。** [冻结协议](research/chapter3_experiments/whole_native_diagnostic/protocol.md)、[准备总结](research/chapter3_experiments/results/whole_augmented_native_preparation01/summary.md)、[7项准备层预检](research/chapter3_experiments/results/whole_native_diagnostic_precheck01/run01/checks.json)及零消费声明保存。只读现有参数JSON和源码，253源/11工件绑定；科学导入/函数/进程守卫全0，原26项未复跑。

**待确认提案：新独立1次×300方法秒，最多1次native、max_rounds=1，0post/不补跑。** 输入/独立L0/构模/MATLAB启动/原最多3次初始化及连续复核/增广/hash/日志/native/callback-final完整接纳均计300；原生MaxTime只取剩余。40秒清理、420秒方法返回监督、480秒整项监督单列，300后仅停止/清理/只读保存，不形成新U。原H/50/80/beta1.0/auto-L/400ms/5ms、完整合法域/原选项容差保持。

现helper不能直接传max_rounds；纯recipe显式绑定context诊断函数max_rounds1，保留旧入口标签50并另记actual1。prepare层run永拒，实际launcher尚未实现/验收；用户确认后才按冻结配方落实一次性受控启动及其必要预检，不自行授权。15项独立内部核对通过，250旧源及原档案/账本保持，原16消费/24未启动不变。本轮0研究调用/0预留/无claim，尚未授权执行，也未验证原生可用或数值冲突修复。以下K167及更早为历史。


**K.167／D192：整体MILP增广接口适配完成，最终26项纯夹具通过，仍无真实求解调用（E612）。** [实现与验收总结](research/chapter3_experiments/results/whole_augmented_precheck01/summary.md)、[最终run04](research/chapter3_experiments/results/whole_augmented_precheck01/run04/checks.json)保存。新增可选whole_augmented入口；formal仅增加记录器/诊断函数注入口，默认路径保持。初始点包装、callback/final原/新/link接纳、多场景完整Recorder、反馈后新映射、原生/派生证据分列和只读身份核对已接通。

预算内技术故障不归正常截止，原生编号/回调内容错配锁存；已有budget取消标记不覆盖，截止及档案异常保留已成替身见证、拒绝迟到新U。最终源码f913b927…d98bc绑定26/26纯夹具，真实构模/求解器/子进程/热积分守卫全0；run01—03为不同源码历史，不作为最终凭据。替身SAFE/U不属于研究结果。独立3项AST核对表明去掉可选hook后原两个函数与旧版一致，其余247旧源/输入/旧档案保持。

本轮无研究构模、原R2转换、MATLAB/LP/MILP、热/post或新增研究U；16消费/24未启动不变，旧批次执行链未改/未恢复。尚未核actual whole覆盖率、成本及原生接纳，不能说−2故障已修或有节能/反馈收益。阶段到接口验收结束；下一步若做单次数值兼容诊断须另定范围/预算及新版本，期限补齐与机制实验优先级另议。以下K166及更早为历史。


**K.166／D191：整体MILP等价增广表达零调用兼容性审查完成，数学兼容、接口待适配（E611）。** [总报告](research/chapter3_experiments/results/whole_augmented_compatibility01/summary.md)及代数/whole生命周期/旧档案身份三项核查保存。互补变量变换保留连续放松、整数可行域投影与目标，不加强精确LP界。可继承精确b−M筛选、不可无损行原样保留及原/新/link联合接纳；当前whole直接创建完整Recorder，既有增广封装绑定PartialRecorder，不能只换session_factory。

具体缺口为：whole数值请求绑定、callback/final原坐标门、原生/派生回执分列，以及反馈后按当前矩阵重绑。旧R2无同次names/row_tags身份，不猜列或重建补称；未核整规模实际合格行数量、成本或原生故障是否改善。link误差可由M放大，仍须原容差复核原行及完整连续热安全，不能把增广可行当安全U或独立证书。

本轮0构模/载荷变换/求解/热/post/新U，原248源、旧432工件、当前30目标hash保持，16消费/24未启动不变。建议下一步仅whole数值薄层适配与纯夹具预检，未实施/未授权新研究调用；不自动恢复24次、不追加大批或热扫描。该项为工程兼容性工作，不能补足反馈收益/创新证据；完成后再决定单次数值诊断、期限补齐或机制验证的优先级。内部报告复核通过；12项终态完整性核对通过，两个审计脚本字段/账本计数误用的开发失败均保留，未影响原研究。以下K165及更早为历史。


**K.165／D190：R2整体数值冲突只读排查完成，未找到传输故障，原生内部根因仍未决（E610）。** [结论与下一步](research/chapter3_experiments/results/deadline_numerical_readonly01/summary.md)、[载荷复算](research/chapter3_experiments/results/deadline_numerical_readonly01/payload/payload_audit_final.json)、[24项传输核对](research/chapter3_experiments/results/deadline_numerical_readonly01/transport/transport_review.json)保存。原x0与native initialPoint逐字节相同；23464变量/143276行/1131整数索引正常，原接纳复现。全行残差含舍入余量最高9.4641e−13＜1e−9，32重点行精确核对通过。相邻条件双行存在1.4211e−14窄带，但原点在这些局部允许区间内，不能认定窄带就是−2根因。

定向8份回执均有done计数1/最终0，7份为时间退出0；该计数差不能证明solver已保留x0。本次属于旧K106/K131同族状态冲突，LP/IntegerPreprocess已为none；whole仍用原载荷，linked仅第二阶段采用既有增广。通用ACTUAL_NUMERICAL_REPORT_REJECTED理由过强，准确为数值接纳与原生状态一致性未决；只澄清口径，不改冻结分类。无内部阶段日志，不能区分根LP、切面或内部时限路径；Python根未超时不排除原生内部时限有关。

本轮无构模/求解/热评价/post/新U，原248源、旧两槽与R2档案保持，16已消费/24未启动不变。下一步仅建议先审查复用既有增广到whole的表达兼容性；任何原生诊断/修复/续接须另外明确范围和预算，不直接恢复24次。以下K164及更早为历史。



**K.164结束／D189：期限组16/40次后因数值一致性未决停止，24次未启动（E609执行补充）。** [阶段总结](research/chapter3_experiments/results/deadline_resume01/summary.md)、[40槽含缺失结果](research/chapter3_experiments/results/deadline_resume01/analysis01/results40.csv)与联合终态审计保存。15次有原始完整SAFE，其中14份通过既定post、可比较；R2 HEFT正常未得解，R2整体MILP保留旧SAFE但发生数值一致性未决且未post，不参与正常排名。根方法时间合4159.173秒、已消费预算4800秒，原启动至停止5650.908秒，原40次/12000秒和绝对截止未重置，原248源/旧两槽保持。

R1联动U=0.880088065 J，低于HEFT的0.936682145 J约6.041973%，但300秒对26.172秒；R2联动U=0.979461140 J，五个SA均更低（中位数0.906912922 J），HEFT未得合法完整安排。R3—R5未启动，不汇总为完整五题排名；MILP热反馈0，独立最优/无解证明0。

**新的停止原因不同于此前取消标记：** R2整体MILP在298.391秒内返回NUMERICAL_ADMISSION_STATUS_CONFLICT。显式初始点通过现有数值行接纳且原生确认收到，但求解器报告exitflag=-2/x=[]，done回调可行点计数1、最终计数0；这是一致性未决，不是已证模型无解、已证求解器缺陷或普通根截止。原SAFE U=1.078187304 J及26.453秒形成时刻保留，不补post/新U、不放宽容差、不重跑、不继续消费24槽。下一项建议仅只读核查当前数值payload与原生状态冲突，再决定是否修复及续接；不追加条件扫描或算法调参。以下是本次续接前记录。



**K.164／D189：期限组原2次保留，修正截止记录后仅续接原38个未消费槽（E609）。** K163运行至2/40次停止：整体MILP为正常截止、安全U=1.084886371304 J；联动已在255.156秒形成安全U=0.880088064994 J，但原“budget”取消标记被通用文案覆盖，唯一MISSING_MATCHING_ROOT_CANCEL_FILE导致管理层误判。24项适配夹具与14项只读证据核对通过，派生状态为正常截止末请求未决；原失败终态、claims、U及形成时刻不改。第二槽原定一次60秒post在独立目录执行并通过，不搜索、不新增U。

仅新增管理记录适配及原槽3—40的独立续接层，旧240科学/执行源保持。[续接协议](research/chapter3_experiments/deadline_resume/protocol.md)、[修正审查](research/chapter3_experiments/results/deadline_cutoff_repair01/repair_review.json)及[单次post](research/chapter3_experiments/results/deadline_cutoff_repair01/post_summary.json)留存。原40次/12000方法秒和最初UTC2026-10-22T13:46:38.073713绝对截止不变，诊断/暂停不重置日历，前两次不重跑。没有新的参数、算法、初始化或研究预算；原BLOCKED与派生解释分列。待纯预检及冻结审查通过后只启动剩余38次；实际进度以deadline_resume01独立账本/终态为准。以下K163冻结状态为启动前历史。



**K.163冻结／D188：β=1.0期限组按40×300秒、12000方法秒/19200日历秒推进（E608）。** 用户在上一条具体列明该预算及先冻结/预检后执行步骤后回复“继续吧”；本轮承接这一范围，不扩其他批。新[执行协议](research/chapter3_experiments/deadline_execution/protocol.md)、[冻结说明](research/chapter3_experiments/results/deadline_execution01/preparation_summary.md)及240源/五输入/40槽声明保存，205项守卫预检通过；原234源/K162准备账本及P0/P1/P2归档不改，当前仍0研究调用/零消费。

原H响应、50°C/80°C、期限beta1.0、auto-L/完整链/400ms/5ms及功热安全门保持；不借历史候选/锚/热缓存。总控显式要求当前期限审计通过，正常无U不做post、不填0能耗；有据的三模板未得种子可正常终止，热/数值未分辨/技术故障停后续。独立claims、19200秒唯一日历、420/480秒监督及一次60秒post保持，不补跑/延期。下一步核对冻结凭据、提交后唯一启动；实际状态以新deadline_execution01账本/终态为准。以下K162未授权描述保留为本次“继续”前历史。

**K.162／D187：β=1.0期限组准备完成，182项纯预检通过，执行预算尚未授权（E607）。** [准备结论](research/chapter3_experiments/results/deadline_batch_preparation01/summary.md)、[输入逐字段对照](research/chapter3_experiments/results/deadline_batch_preparation01/input_contrast.json)、[182项守卫预检](research/chapter3_experiments/results/deadline_precheck02/checks.json)保存。仅base原H响应的期限1.3→1.0，50°C入口/80°C温限、auto-L、完整链/400 ms/5 ms、原功热/合法域/方法保持；234源绑定，原224份继承科学和执行源码不改，0研究/原生/构模/热积分。首轮误把消融清单标签要求不变而有3项输入对照error；按原生成器登记该元数据后为13处差异，失败和修正均保留，未改研究输入。

增加当前期限精确合法性审计，以及有完整三模板失败证据的NO_COMPLETE_SAFE_LINKED_SEED正常无U终态适配；缺证据/热未分辨/数值和技术故障不放行。只检查已存回执，不新增初始模板、求解规则或安全U。43项独立内部静态/快照核对通过并另存，非外部ChatGPT批准；外部自动审查仍暂停。

**当前停止位置：** 输入/源码快照、40拟议槽与协议齐备，账本消费/预留0、无claims、CLI拒绝run，无真实批量launcher。拟40×300秒、12000方法秒/19200日历秒，尚待用户单独确认，再冻结并预检实际执行链；不自动运行、不补跑P0/P1/P2、不启动其他期限档/响应/热扫描。以下K161及更早的“下一步/当前”保留为阶段历史。

**K.161完成／D186：P2共40/40次结束，40份最终SAFE均通过既定post（E606执行补充）。** [阶段结论与图](research/chapter3_experiments/results/p2_execution01/summary.md)、[40次CSV](research/chapter3_experiments/results/p2_execution01/analysis01/results40.csv)、[709项终态核查](research/chapter3_experiments/results/p2_audit_tools01/p2_terminal_review01.json)已存。原H响应，仅初温78°C/温限80°C；224源/原218及旧P0/P1/准备工件保持，无补跑/延时/参数变化。方法根时钟合10395.472秒，监督日历10779.703秒＜19200秒；30次正常截止末请求未决、10次正常完成，不是全部求解已决。

联动相对HEFT降幅R1—R5为−0.696955%／+0.059475%／−14.832562%／−1.075126%／−8.752756%，仅R2更低，HEFT五题均更快；联动第二阶段4/5严格改善，R3无改善。本组没有建立联动的一般优势。独立最优/无解证明0、内部界仍按原作用域登记，L0高于U异常0。

**热证据分开：** 17个调用（HEFT5＋SA12）保存热违规，按评价对象去重为46条存档，MILP反馈0。五题完全相同HEFT中间候选在P0完整SAFE、P2严格超温；但五题最终HEFT安排仍相同，不写最终调度被热约束改变。R1同一候选CPU1在P0峰温55.558515°C，P2的95 ms温度下端81.209166°C＞80°C；同一最终HEFT安排的增耗0.105765583281 J与温度修正增量相容。30项热接纳、40条曲线末值、55项解释核对通过，新增科学评价0；25条保存热未决均因wall_time_limit，不当数值故障。

**停止位置：** P2预算已消费完毕，原始结果/安排/界/热拒绝/阶段耗时/快照齐备，MAT仅本地保留及hash。下一步建议先收拢P0/P1/P2证据与方法限制，再讨论有通用依据的改进；不针对R4补丁、不继续温度扫描、不启动P3或新消融。本批真实自动执行已结束；外部审查自动化仍暂停。以下为本次执行前冻结及旧阶段记录。

**K.161冻结历史／D186：用户已确认P2预算，实际启动流程已冻结（E606）。** 仅initial_78__R1—R5，原H响应、入口78°C/温限80°C，其余模型/方法/合法域保持。40次各300秒，12000方法秒/19200日历秒，不补跑、不延长。170项纯预检、25项启动前只读核对通过，224源/五输入/40槽绑定；原218源及P0/P1保持，旧K160准备不改写。

独立[实际执行协议](research/chapter3_experiments/p2_execution/protocol.md)、[冻结说明](research/chapter3_experiments/results/p2_execution01/preparation_summary.md)及声明已存。首轮1项来源标签声明遗漏已补齐，失败记录保留，真实研究/构模/求解/热调用0。仅新执行层持本次用户授权；唯一launcher计19200秒，独占claim先消费，420/480秒监督及一次60秒post不延长300秒安全证据窗口。技术/数值/源/输入/IO/post错误停止后续，0反馈/0改善如实保留。当前实际进度以p2_execution01/status.json、不可变回执及终态为准，不自动启动后续批次。以下K160未授权记录为本次确认前历史。

**K.160／D185：P2高初温准备完成，执行预算仍未授权（E605）。** [准备说明](research/chapter3_experiments/results/p2_batch_preparation01/summary.md)、[153项纯预检](research/chapter3_experiments/results/p2_precheck01/checks.json)、[五输入逐字段对照](research/chapter3_experiments/results/p2_batch_preparation01/input_contrast.json)及29项只读准备核对已保存。原211源/P0/P1工件保持；本批218源绑定，0研究、构模、求解、热评价调用。用户要求保留R4局限诊断，不针对失败点改算法，转向既有initial_78的准备。

五题相对P0/base原H响应各仅12处差异：三个目录/身份字段、初温设置、AB/AC各四节点50→78°C；80°C温限、模式表、期限/权重、完整三Stage链、400 ms/5 ms、auto-L等其余字段一致。不叠加P1统一响应。四方法仅适配新输入/回执绑定，153项核对包括40槽模拟派发、独立加载/计费、源和输入漂移阻断及未授权状态；不证明78°C可行或求解成功。

**待确认的唯一执行事项：** 建议P2 R1—R5每题整体MILP/预消元联动/HEFT各1＋SA101—105，共40次×300秒，12000方法秒、19200日历秒。当前仅草案，准备ledger零预留/消费、无claims，真实批量启动器未实现，CLI拒绝run。获得独立预算后，再冻结/预检实际启动流程，之后才运行；不增加热扫描或消融、不要求反馈/改善正例，不把触发反馈等同于已证求解收益。以下K159及更早“下一步/尚未准备”是历史记录。

**K.159／D184：P0/P1的R4只读诊断完成，P2仍未授权（E604）。** [报告](research/chapter3_experiments/results/p1_r4_readonly01/summary.md)、111项数据/代数核对、39项原来源核对及11项报告核对通过；211项冻结源、原输入/安排/结果保持，0求解、0热评价、0研究调用。

P0两法均12L，活动/基准/公共能量相同，联动仅少0.103486 mJ温度修正。P1联动多93.740034 mJ，其中AC贡献87.592809%；活动增量+63.727161、基准+24.180000、温度修正+5.832872 mJ。P1第一阶段约32.625秒结束，两个受限子问题均solver-reported零gap但未形成改善；第二阶段因此仍闭合B/C.main、post的原H档锚，不能到达HEFT的AC全L安排。P0暖锚已是L档。精确HEFT安排均在当前局部域外，但P0域内另一套全L安排已接近；不据此推断所有同等质量安排均被排除。

P1根时钟158.578秒，尚余141.422秒；第二阶段两场景各约60秒，是预定序列正常结束，非300秒耗尽或启动瓶颈。第一阶段为何报告零gap仍未独立解释，不能写成低档均不可行。AB两个main同NPU且双L的完成下界126 ms已超过较晚期限125.84 ms，需区别AC已有全L安全见证。0热违规/反馈；本次没有热排除导致落后的证据。下一步仅考虑既有P2：以P0/base原H响应为参照，只改78°C入口，不能默认为P1的R响应叠加高初温；尚未适配、预检或执行P2。

**K.158完成／D183：P1 response_R共40/40次完成，40份最终方案均SAFE（E603执行补充）。** 185项必要预检、14项冻结核对及489项终态存档核查通过；211源／输入保持，无技术故障、无补跑，worker／process均COMPLETED。[结果与图](research/chapter3_experiments/results/p1_execution01/summary.md)、[40次CSV](research/chapter3_experiments/results/p1_execution01/analysis01/results40.csv)、[存档核查](research/chapter3_experiments/results/p1_execution01/record_review01.json)已存。

联动R1—R5的U为0.901812648325／0.904029114143／1.001135476136／1.029573489263／0.970744327679 J，相对HEFT降低4.618619%／7.084054%／-6.314225%／-10.016743%／-1.209506%；2/5题严格更低，负值为更差。HEFT在5/5题更快；第二阶段5/5题有严格改善。

保存热违规0／反馈0；独立全域最优0／无解0，L0高于U异常0。solver-reported和局部状态不升级为全域证明，未新增扫描或认证工作。预留12000方法秒，实际根时钟合10282.141秒；从本批启动至终态日历10645.915秒＜19200秒。启动／构模／求解／内部连续复核全部计费，停止延迟与各一次post另列；预算后新U未接纳，不补跑／延时。

P1是共同真实响应输入α=1的对照条件；与P0不同问题，不把两批能量差称为共同评价下的建模节能收益。SA101—105逐次及分布保留，不作五取一等预算排名；固定五变体及单次确定性运行不外推稳定性。本阶段结束，下一项先审阅本组正反结果，再确认后续既定条件及预算；不自动启动其他批。

**K.158冻结历史／D183：P1统一1/f响应组已完成独立适配、185项必要预检及冻结，已按冻结协议启动（E603）。** [协议](research/chapter3_experiments/p1_batch/protocol.md)、[准备说明](research/chapter3_experiments/results/p1_execution01/summary.md)、[声明](research/chapter3_experiments/results/p1_execution01/declaration.json)保存，211项源绑定、14项准备核对通过。仅response_R R1—R5的40槽，各300秒、12000方法秒／19200日历秒；原203源／参数／完整安全保持，P0不重跑不改写。新输入独立重载与计费，不借P0候选／缓存。首轮185项中5个目录标签预期差异留存，修正纯夹具后全过，0研究／原生／模型／热调用。待提交冻结后按本次已确认预算执行，其他条件不自动启动。

**D183授权历史：用户已单独批准P1响应组40次预算，先适配／预检／冻结，再执行。** 范围response_R__R1—R5，每题整体／联动／HEFT各1＋SA101—105各1；每次300秒，方法总上限12000秒、总日历19200秒，不补跑／延时，不改既有方法、参数及安全标准。当前仅开始独立P1接口准备，未启动新研究调用。D182的“尚缺预算”是本次确认前的记录；B／C／D其余条件仍未授权。

**K.157／D182：已读取最新独立建议0e8a69c，完成P0／R3零调用诊断及四类条件草案（E602）。** [只读分析报告](research/chapter3_experiments/results/p0_readonly_review01/summary.md)、[25项记录核对](research/chapter3_experiments/results/p0_readonly_review01/checks.json)、[31项来源核对](research/chapter3_experiments/results/p0_readonly_review01/source_checks.json)已存；原方法／参数／P0工件不改，0求解／热评价／研究调用。采纳先收拢已有证据、分批扩展的建议，不把750或160次作为论文硬门槛。

**R3已查清的部分：** 加权能耗差0.074696070 J几乎全部来自AB（+0.074785259 J；AC略抵消）。差额由活动增量+0.055911588、设备基准+0.015120000、温度修正+0.003664482 J组成。AB联动4H／1M／1L、HEFT全L；同为A.main先于B.main，主要设备类别相同。即使统一交换CPU标签，HEFT的AB安排仍违反第二遍B.main的闭锚：L／75 ms不同于M／85 ms。精确HEFT安排不在当前条件域，但不能据此断言同样好的安排全部不在域内或改邻域必能胜出。R3根时钟257.422秒结束，尚余42.578秒；三次原生求解受约60秒scene片限制，AB二遍solver-reported收敛未改善。并非根300秒耗尽；0反馈，AB峰温约51.683°C＜80°C，无热故障证据。

**下一步建议及待确认：** 草案先P1 response_R，再initial_78、beta_1.0、requests_2；均取旧目录，后两水平是助手推荐而非用户确认。P1两场景／全链不变，但P0 ID白名单、输入／回执绑定及旧claim不能直接复用，需独立适配与预检。建议P1若单独批准为40次×300秒、方法上限12000秒、日历19200秒；本轮没有新调用预算，不自动启动。多副本的开放集合仍待适配／确认；无NPU两档联动继续后置。P0图表直接复用，R4仅称差异很小，热反馈贡献仍未观察。

**K.156／D181：账本修复后37次续接全部完成，P0合计40/40份最终SAFE（E601）。** 前三次未重跑，37份新结果均完成原定一次post；167项必要预检及453项终态存档核查通过，203项冻结源与旧工件保持，续接无技术故障。每次300秒接纳截止，原3次900＋本次37次11100＝12000预留方法秒；实计方法根时钟10542.234秒，原启动至终态12685.815秒＜19200秒，暂停计入且未重置。完整[阶段结果与图](research/chapter3_experiments/results/p0_resume01/summary.md)、[40次CSV](research/chapter3_experiments/results/p0_resume01/analysis01/results40.csv)、[453项核查](research/chapter3_experiments/results/p0_resume01/record_review01.json)保存。

**质量与限制：** 联动相对HEFT在R1／R2／R4／R5分别低2.318117%／10.067571%／0.011967%／5.875998%，R3高8.662912%；HEFT五题均更快。联动五题均低于整体MILP，第二阶段5/5有严格安全改善，但不构成等预算消融或全域最优证明。SA五种子分别及分布保存，不以五次最优值冒充单次竞争者。40次保存热违规0／反馈0，独立L0未闭合、全域最优及无解证明均0；本批不能宣称热反馈求解收益。MATLAB启动差异与分段执行如实保留，不作统计稳定性或实机收益结论。

**执行层改变与完成边界：** 同次pending替换WinError5／32最多等待1秒，监督只读compact status，方法回执先独占落盘，worker／supervisor均已COMPLETED、退出0。原197源与旧三次证据／claims不改，不借旧见证或缓存；首轮5项夹具接口错误留档，最终167项预检无研究调用。原300秒证据截止、420／480秒停止监督及各一次60秒post保持。外部自动审查仍暂停，453项为本会话存档核查。阶段已结束；下一步先审阅P0及R3反向结果，再确认下一组既定实验预算，不自动启动后续批次或调参。

**K.155历史执行结果：P0在3/40次后因账本写入故障停止，当时37次未启动，无补跑／延时。** 三份R1最终安排均SAFE并完成各自一次post；U依次整体1.084886371304、联动0.860663343334、HEFT0.881087997281 J。联动本次严格低于HEFT 2.318117%，HEFT更快；SA／R2—R5尚无结果，不能称40次完成或总体排名。整体正常截止末请求未决，联动与HEFT方法正常完成；故障在HEFT返回后替换账本，非求解／热模型失败。消费3次／900预留秒，方法时钟合610.219秒、监督637.579秒，0新热反馈／全域证明。[阶段结论](research/chapter3_experiments/results/p0_execution01/summary.md)、[派生终态](research/chapter3_experiments/results/p0_execution01/terminal_receipt.json)、[27项核查](research/chapter3_experiments/results/p0_execution01/failure_review01/review.json)保存。

**K.155故障处理历史：** 原ledger及pending保留，因此旧文件仍显示HEFT RUNNING；实际进程已退出，以派生终态和退出日志解释，不改写历史。197冻结源与原153工件保持；原定HEFT一次post已完成，无重跑。Windows读句柄占用可在小夹具复现，但实际锁持有者未定位；1秒有界IO重试候选8/8通过，仅留在故障目录，未接入冻结源码。下一步建议接入写入修复及独立故障终态、作并发读写／退出预检，再单独冻结未执行37槽的后续安排；不直接重启本批、不重跑前三次、不改科学模型或方法。

**K.155历史冻结：用户确认P0 40次×300秒，实际启动协议及163项预检通过，当时准备执行（E600）。** R1—R5每题整体／预消元联动／HEFT各1＋SA101—105各1，顺序及输入沿K154，原178方法／配置与191准备源不改。新增[实际总控协议](research/chapter3_experiments/p0_execution/protocol.md)与[冻结声明](research/chapter3_experiments/results/p0_execution01/declaration.json)绑定197项源／协议／依赖；方法上限12000秒，日历硬限19200秒，单槽返回／清理420秒、含post／归档480秒均不延长300秒安全证据截止。真实claims独占消费，无恢复／补跑入口；正常截止经原回执与隔离核对可继续，故障／数值覆盖未决／post失败停后续。每份已接纳最终SAFE只作一次60秒post，不补搜索或改U。当前进度以[p0账本](research/chapter3_experiments/results/p0_execution01/ledger.json)为准；未把准备通过写成已运行40次。自动外审仍暂停，依据本轮直接授权执行。

**K.154／D179：P0基准批准备完成，139项预检及20项存档核对通过，0研究调用（E599）。** 新增[多问题入口与协议](research/chapter3_experiments/p0_batch/protocol.md)、[阶段说明](research/chapter3_experiments/results/p0_batch_preparation01/summary.md)和40槽声明，独立展开base__R1—R5原完整AB／AC链，保留400 ms／5 ms、auto-L、原功热与安全标准。178份旧源码不改；五个输入身份、方法轮转／SA101—105、派发参数、截止处理及完整回执条件已核。R1仍是拟议新批的预声明重复，不复用K152见证或配额。首轮系统版本查询触发子进程禁用门的2项失败保留，修正测试环境后139/139通过；340份K152原工件保持。

**执行仍未授权：** 准备账本消费0／授权样例false；本轮一次消费仅TEST_ONLY模拟，真实批量总控／claim尚未冻结，CLI拒绝run。下一步集中确认P0 40次×300秒（方法上限3小时20分、含额外处理的日历预留5小时20分），再冻结并模拟核对实际启动、总墙钟／隔离停止和post流程，之后才执行。没有修改模型、适配无NPU联动、增加温度扫描或恢复115次／自动外审。

**K.153／D178：已回到第三章五组正式实验安排，本轮仅计划、零研究调用（E598）。** 保留当前auto-L、完整链、功热／安全标准与预消元联动版，新增[分批执行表](research/第三章当前进展与正式实验推进计划_审查稿.md#k153第三章正式实验分批安排待确认不执行)及[机器可读计划](research/chapter3_experiments/plans/k153_execution_plan_v1.json)。建议顺序：基准→统一1/f→78°C入口→设备平均响应→其余既有热水平→期限→资源→场景→请求规模。每个完整问题整体1＋联动1＋HEFT1＋SA101—105共8次；建议新批沿300秒，先准备基准R1—R5的40槽／方法上限3小时20分，随后两批各40槽。上述预算、重复和执行尚待确认，不恢复旧115次或自动启动120次。

**用户已确认的适配边界：** CPU-only、CPU+GPU不含当前固定共享A.main所需NPU0，两档各5个联动槽先后置，保持现版本；不擅自回退CPU，不记算法失败。五组全范围去重19条件／95问题，750拟执行＋10后置；300秒下方法上限62小时30分＋后置50分，仅盘点、不承诺全跑。旧115次是hold历史，K152为独立先导，不免费充抵正式样本或初解；K127热证据及0反馈保留，不新增扫描／默认10次消融。批量入口和部分审计仍绑定base__R1，多场景／请求须按原目录规则核覆盖，尚非即用能力；178源／配置和历史结果未改。下一步仅建议制定并实现P0多问题入口／必要预检，再提交40槽具体预算，不自行继续实施或运行。

**K.152／D177：最小四方法同轮对照完成，预消元联动取得本次最低安全能量（E597）。** 原base__R1完整AB／AC三Stage、400 ms／5 ms、auto-L及50°C／80°C保持，整体MILP→联动→HEFT→SA101各独立一次300秒。U分别1.084886371304／0.860663691235／0.881087997281／0.907346431253 J；联动相对HEFT、SA、整体分别严格低2.318078%／5.144974%／20.667849%。HEFT43.625秒完成，联动273.688秒；不称普遍更快。95项预检与83项内部独审通过，四份最终安排独立连续复核均SAFE。[阶段结论](research/chapter3_experiments/results/four_method_comparison01/summary.md)、[同轮事实及图](research/chapter3_experiments/results/four_method_comparison01/analysis01/summary.md)、[独审](research/chapter3_experiments/results/four_method_comparison01/independent_review.md)保存。

**归因与边界：** 联动第一／二阶段U为0.962885037941／0.860663691235 J，第二阶段确有完整改善；对HEFT少0.020424306046 J主要来自活动项少0.016301038062 J。整体构模／进入求解器但无新已接纳整数候选，保留本次初始化SAFE；整体及SA正常截止、末请求／评价未决，未补记迟到U。共同L0≈0.738286 J未闭合；本轮0热违规／0反馈，不增加热反馈收益证据。消费4调用、预留1200秒，实际方法合917.391秒、进程940.359秒，无补跑／延时。178源／输入／原记录保持；分析层一处L0形成时刻误取已纠正，旧分析及脚本保留。下一步建议保留本版、回到既定分组正式实验的有限执行计划，不再加邻域／温限；115次批量、新配额及自动外审均未自动开启。

**K.151／D176：原基准固定锚预消元配对完成，取得5.446441%严格安全质量改善（E596）。** 用户“进行”授权旧4开与预消元版各一次300秒，原base__R1、完整AB／AC三Stage、400 ms／5 ms、auto-L及50°C／80°C保持。旧U＝0.910239340728 J，新U＝0.860663691235 J，新上端严格低于旧下端；种子及第一遍最后warm完全相同。两方已成方案分别经原连续评价器事后复核SAFE，内部独审60/60通过。[结论](research/chapter3_experiments/results/anchor_quality_pair01/summary.md)、[事实及图](research/chapter3_experiments/results/anchor_quality_pair01/analysis01/summary.md)、[独审](research/chapter3_experiments/results/anchor_quality_pair01/independent_review.md)保存。

**机制与限制：** 第二遍AB280→216／AC274→213项、原生变量6738→5312／7810→6144，热能耗条件组少23.30%；AC根LP原生累计10.073→3.821秒，形成两次新完整改善。主要收益在AC，AB未更低。第一遍独立耗时差43.828秒、MATLAB启动56.703／12.766秒，新二遍余量更多，不能将全部绝对时间／质量差唯一归因过滤；总构模9.564→10.328秒未减少。两法方法停止300.016／281.641秒，U形成253.047／261.438秒；本次质量改善已证，没有全域最优、普遍加速或新热反馈收益（0反馈）。

**执行与完成：** 29项配对包装预检通过。首进程把实际300.016秒取消及末请求三份空BUDGET状态误判硬错，停住未开始新版；经独立存档核查与12项纯记录正反例，仅追加分类adapter校正。174冻结源、原BLOCKED／账本／claims不改，只执行尚未开始新版，旧未重跑。累计2次／600预留研究秒已消费；活动进程602.766秒、诊断暂停510.697秒、完整日历1113.457秒，不称900秒连续完成。下一项建议保留预消元版、回到最小同轮公平方法比较，不继续扩邻域或温限；新调用须独立冻结，不恢复115次及自动外审。

**K.150／D175：固定锚约束预消元已实现，80项正确性预检通过（E595）。** 保持4开2闭、原参数和连续安全门；默认关闭，显式开启只作用于联动第二遍。过滤位于邻域／期限之后、事件及热系数之前，以闭合Stage的同单元、同域异OPP和原直接依赖事实删除必零选项；不将开放warm固定、不加迭代或新邻域。[阶段结论](research/chapter3_experiments/results/anchor_precheck02/summary.md)、[80项门](research/chapter3_experiments/results/anchor_precheck02/checks.json)、[内部核对](research/chapter3_experiments/results/anchor_precheck02/internal_review.md)保存。

**范围与证据：** 通用1296组合保留96个合法安排；实际4开2闭AB／AC各1296组合，合法36／108均保留。小物理warm按新事件、新x0与补集映射重新接纳并完整连续复核；0原基准构模／0真实求解／0研究调用，不称0热计算。旧路径66项与新增14项合计80通过，首轮检查器签名错误及开发失败留档。172份当前源码／输入绑定，167继承材料仅3份生产源按声明修改，其余164份及399历史工件保持；没有速度或节能收益结论。下一项只建议单独冻结质量配对，旧调用配额不复用，自动外审仍暂停。

**K.149／D174：保留4开2闭；完成根LP／整数候选瓶颈分析，唯一提出固定锚约束预消元（E594）。** 用户明确保持原参数及热安全、不补跑；本轮仅读K148日志、原生矩阵身份、选项目录和源码，0构模／LP／MILP／热／研究调用，167生产与调用源保持。[分析与提案](research/chapter3_experiments/results/root_candidate_analysis01/summary.md)、[原生指标](research/chapter3_experiments/results/root_candidate_analysis01/native_metrics.json)、[静态计数](research/chapter3_experiments/results/root_candidate_analysis01/direct_dependency_analysis01/anchor_dependency_note.json)保存。

**定位与唯一改进：** 求解等待／响应读取占84.82%／86.89%；8个请求均自报0分支节点，但旧4第二遍AB有warm外3个安排，直到请求约60秒才发布。主要问题不是热核／数值门，也无“大分支树”的证据。原生最终维数须计补集列：旧AB／AC为6738／7810，新为8060／15314，区别于构模摘要。建议只把闭main/post锚所决定的同单元、同域异OPP和原直接依赖必零选项，在事件展开前一次排除；不加CDF、迭代或邻域。旧4 AB280→216、AC274→213选项，跨事件joint合计3077→2360、温度／能量条件等式组合计静态少23.30%，原完整warm均保留。证明限原4开2闭真实整数合法域；新系数包络不冒称旧浮点矩阵逐点相同。

**完成边界：** 内部独立资源及依赖核对通过，非外部ChatGPT审批；现有目录核对不替代完整小域穷举。预消元尚未接入生产，无新速度／能耗结果。下一项仅建议实现这一预消元并作小域合法集合、新事件、x0／增广映射及连续门预检，再单独讨论冻结质量配对；本轮不新增研究配额、不恢复115次或温度扫描。

**K.148／D173：5开1闭质量配对完成，未优于旧4开2闭（E593）。** 原base__R1、完整AB／AC三Stage、400 ms／5 ms、auto-L与50°C／80°C保持，两方法各一次独立300秒。旧U＝0.910239340728 J／282.703秒，新U＝0.962884840560 J／274.734秒，新高5.783699%。旧第二遍3次完整改善，新第二遍0次；两方法最终SAFE均已完整连续复核。[阶段结论](research/chapter3_experiments/results/linked_five_open_pair01/summary.md)、[存档分析](research/chapter3_experiments/results/linked_five_open_pair01/analysis01/facts.json)、[内部独审43项](research/chapter3_experiments/results/linked_five_open_pair01/independent_review.md)保存，非主线⑥跨会话审批。

**方法线索：** 新第二遍只开放本地main，设备及闭post仍取自身完整锚；模型扩大，AB／AC根LP原生自报4.317／8.256→15.913／45.067秒，新只重新得到warm。两次第一遍B.post为145／150 ms，不能作固定warm单因素归因；新有更多二遍剩余预算仍无新增改善。0热违规／0反馈，L0约0.738286 J未闭合，无全域最优／无解证明。建议暂保留4开2闭，停止直接扩大开放数量，下一项仅据已有模型／根LP记录确定一项整数候选生成结构修订；未授权新调用、温度扫描或115次批量。

**实现故障与恢复：** 原包装将60位向外舍入上端多5×10⁻⁶¹ J误判加权不等，保守阻断后续。24项包装＋504项小域预检未覆盖此边界；另补7项回归与独立存档核对后，只执行尚未开始的新方法，旧未重跑、旧BLOCKED／claim保持。167冻结源／165继承源与301历史工件不变；额外修复适配器只纠正事后审计，绑定SHA另存。累计2次／600研究秒配额已消费；活动进程576.422秒、诊断暂停388.623秒，完整日历约965.037秒，不称无中断900秒内完成。临时目录失败、审计首轮类型错误、绑定分析版及图例修订均保留。

**协作方式更新（2026-10-21，D172）：** 用户暂停自动审查，改由本人转述另一会话的审查意见。本会话小时监测已完成6次并PAUSED；观察到本机续接和GitHub schedule检测成功，但未见外部review／开放PR／新分支，科研调用0。后续恢复人工交接与用户逐项授权，不以未配置签名和自动runner继续阻挡人工讨论；不伪造reviews、不删自动化归档、不启用旧夜间配额。D172时仅汇报K146进展；后续用户D173另行授权K148配对，结果见上。自动审查仍未恢复，115次正式批量未启动。

**K.147／D171：GitHub交接与审批基础设施验收，真实执行仍关闭（E592）。** 用户要求由原有另一段ChatGPT独立审查，执行端不得代写reviews；已保存[协议](research/agent_loop/PROTOCOL.md)、固定subject／hash交接、只读检测器、签名／一次性消费／Git远端CAS／预算预留／STOP。[门禁28项](research/agent_loop/validation/gate_unittest.json)、[监测25项](research/agent_loop/validation/monitor_unittest.json)及[TEST_ONLY全链](research/agent_loop/validation/test_only_e2e.json)通过；均为基础设施测试，0研究／MATLAB／LP/MILP／热计算。原165源码及301旧工件保持，未创建真实reviews。

**授权与阻塞：** 用户确认外部“GitHub 独立实验审查”每小时启用，双方同YBEMR；后续明确授权最多2轮、累计2次×300秒、累计600研究秒、总墙钟7200秒、北京时间2026-10-21 07:00截止，无改善／技术故障即停、不补跑。config已记新配额，未复用历史预算；真实来源／公钥、实际写回、受控Windows/MATLAB执行链仍未验收，开关false。GitHub只读检测每15分钟配置，手动实测成功并返回WAITING_REVIEW，不能唤醒外部聊天或替代审批；本机heartbeat最终创建成功：每小时最多6次、ACTIVE、早于明早07:00结束；尚未实测唤醒，依赖本机／App，不等于科研执行已通。当前待审为[K146交接](research/agent_loop/rounds/K146-handoff-001/experiment_report.md)及“5开1闭”只读范围／成本审查提案，未授权实施或求解。详见[验收与实际远程检测记录](research/agent_loop/ACCEPTANCE.md)。

**K.146／D170：联动—HEFT存档差异分析完成，0研究调用（E591）。** 用户只授权对比部署、工作点、时序和组成，不补跑、不改参数。原输入三文件逐字相同、165源与301份K142原工件保持。[分析](research/chapter3_experiments/results/linked_heft_gap_analysis01/summary.md)：K142联动0.962885037941 J，K145 HEFT0.881087997281 J，完整方案差0.081797040660 J；活动0.056607632、基准0.020300000、温度修正0.004889409 J，公共项不变。这是跨批次方案账差，不拼四法排名或单因素因果。

**范围与下一项建议：** 首遍固定A整链H／起点，二遍开放A但闭合本地main／post，HEFT精确方案不在两域；二遍222.656秒才进入、余77.344秒，发布候选均warm。10次已存解码全LEGAL、6次场景评价全SAFE，无热拒绝。共享A设备与场景内A工作点分层；CPU统一换名不能消除A.pre/post同核差异，但K140同seed设备已达0.910240996773 J，不能把全部差距归设备。K135／138全开早试过且无新增；建议下一项仅审查二遍由4开2闭替换5开1闭（A整链＋本地pre/main开放，post完整warm闭合，设备不动），先核范围／成本与同预算执行，不已实施或承诺收益；不加阶段、研究调用或温限扫描。

**K.145／D169：独立HEFT、SA101各一次300秒执行完成，均有完整SAFE（E590）。** 用户按K144冻结协议明确授权，原参数、合法域、auto-L及连续热标准保持，165源不改；无补跑、延时或额外种子。[结果](research/chapter3_experiments/results/heft_sa_followup01/k145_summary.md)：HEFT U＝0.881087997281 J、43.250秒正常完成；SA101 U＝0.907346431253 J、300.000秒正常截止，末候选未决但此前SAFE保留。本次SA能耗比HEFT高2.9802%，不是稳定排名。

**计时与下一项：** 两法首完整SAFE均1.125秒，首区间严格改善12.266／2.782秒；最终U形成43.234／169.797秒。SA末评估AB已成、AC仅45 ms，不接纳部分能量；44／241张不同完整SAFE时间表核对通过。共同L0＝0.738285994489 J未闭合，独立最优未证；0热违规、无本次热反馈收益证据。封存／提取单列，包装348.563秒，不冒称未单测的全进程墙钟。下一项建议只比对K142联动与本次HEFT已存方案的部署、工作点、时序及能量组成，定位低能选择未到达的原因；不拼历史四法同轮，不增调用、种子、温限或115次。

**K.144／D168：分类／计时已接入新独立包装，63项离线预检通过，研究调用0（E589）。** 用户“继续”承接K143最小接入。新增分类、完整回执计时和HEFT→SA101包装／测试共6文件，159继承逐字保持，165当前／快照一致。最终02为63/63、1.407秒（22分类＋19计时＋22包装），真实方法／MATLAB／优化器／构模／热入口guard尝试0。[实现与准备](research/chapter3_experiments/results/heft_sa_followup01/summary.md)、[02凭据](research/chapter3_experiments/results/heuristic_followup_precheck02/checks.json)保存。01旧源61项通过仅历史保留；独审指出输入核对未完被当成明确错误后，修为None／False分离并增2项，不重跑研究。

**结果与下一项：** 新U核原scene全集、400 ms／尾段、节点峰包络、当前调用候选hash／已接纳回执及预算内形成时间；真错误不能被deadline豁免，早期未决和已成违规保留。计时单列启动／实耗／剩余／首完整SAFE与可靠区间首严格改善，不把HEFT／SA内部计时帧当算法阶段收益。K142存档新接口重放10项通过，原165源／301工件保持，正常截止／旧U／末请求未决及160.344秒首改善一致。新[独立协议](research/chapter3_experiments/results/heft_sa_followup01/protocol.md)冻结HEFT→SA101各一次300秒，ledger DECLARED／consumed0、claims空、新global未建；保留基线设备自由度，不借历史答案，不改旧MILP／运输或K142记录。下一项仅执行新两法并统一复核，不补整体／联动、不拼历史四法排名，不加算法／温限／种子或115次。

**K.143／D167：预算状态离线审查完成，K142属正常截止＋既成SAFE＋末请求未决（E588）。** 用户只授权本轮离线审查及独立后续协议。bridge已返回BUDGET_EXHAUSTED、拒绝新候选；6份已存增广数值门通过，222.250秒完整U＝0.962885037941 J保留。旧增广包装把预算／回调未闭合统一锁存，旧比较包装再列技术issue；新增解释不改K142原BLOCKED／TECHNICAL_BLOCK、claims及2次消费，不追认完整四法比较。[审查结论](research/chapter3_experiments/results/budget_end_review01/summary.md)、[22例纯数据分支与存档核对](research/chapter3_experiments/results/budget_end_review01/audit.json)保存。

**分类与后续：** 正常截止须有因果记录、既存检查及隔离依据；身份／载荷／I/O／数值／进程等真异常不因同时超时豁免。留档与可信可排名SAFE分开；旧回执受损时不继续用U。159源、301原工件保持，0研究／热计算／生产改动，初版19例的身份与accepted口径缺口经独审后收紧并保留旧记录。MATLAB启动17.125／72.297秒、阶段实际预算、首完整SAFE与首严格改善分列；联动首严格改善160.344秒，二遍未观测新增。HEFT→SA101各一次300秒已另立[后续协议](research/chapter3_experiments/results/budget_end_review01/followup_protocol.md)，本轮不执行，不重置K142或拼接历史四法排名。下一项只需最小包装接入与离线门，再单独安排两方法，不增模型／算法或温限扫描。

**K.142／D166：四方法冻结执行在第二次截止处阻断，已有完整SAFE保留（E587）。** 用户明确授权整体MILP→联动版→HEFT→SA101各一次300秒，原输入／auto-L／50°C与80°C／完整连续热标准保持。整体正常时间停止U＝1.084886371304 J；联动已得U＝0.962885037941 J，但第二遍AC接纳／归档在截止处未闭合，冻结包装停止后两方法。实际消费2次、HEFT／SA未启动，无补跑／延时。[执行结论](research/chapter3_experiments/results/fair_comparison_preparation01/execution_k142/summary.md)、[存档分析](research/chapter3_experiments/results/fair_comparison_preparation01/execution_k142/analysis01/summary.md)、[本线程独审](research/chapter3_experiments/results/fair_comparison_preparation01/execution_k142/independent_review.md)保存，非主线⑥跨会话审查。

**原因与边界：** 联动最后完整U在222.250秒形成，第一遍219.953秒，第二遍含准备77.687秒、0新增完整U；启动72.297秒已计费。已存数值门均通过，锁存为预算到期检查未完成，不能写成数值候选非法或原问题无解。159源／输入／协议保持，准入18／终审37项通过；方法合600.047秒、清理28.781秒、外部进程636.282秒，合作式尾延迟不补新证据。0热违规／反馈，L0约0.738286 J未闭合；本次四法比较未完成，不能借K127／K140补排名或第二遍收益。唯一下一项建议只核预算截止与真故障分类及离线边界预检，不新增物理条件、算法或研究调用，也不恢复115次。

**K.141／D165：第三章四方法最小对照已准备，0研究调用（E586）。** 用户“可以，你继续吧”承接K140下一项，只完成准备、必要mock与冻结，不运行比较。整体MILP、联动版、HEFT、SA101按原base__R1完整AB／AC、400 ms／5 ms、auto-L及50°C／80°C，下一阶段各一次300秒。三个参照保留设备选择，联动版固定自身种子unit；比较同原问题可用SAFE，不称等覆盖。公共代码加载／包装／清理与方法内时钟分列。[准备结论](research/chapter3_experiments/results/fair_comparison_preparation01/summary.md)、[冻结协议](research/chapter3_experiments/results/fair_comparison_preparation01/protocol.md)、[本线程独审](research/chapter3_experiments/results/fair_comparison_preparation01/independent_review.md)保存，非主线⑥跨会话审查。

**检查与边界：** 仅新运行包装／测试，157继承不改，159当前／快照一致。K127125源中122保持，3变更按当前129／66项链继承，不声称旧67整包重跑。wrapper03最终25/25、4.860秒；01 mock／环境guard失败和02旧源通过保留。修正whole首候选／合法／SAFE详情的嵌套diagnostic读取，未改算法。独审24项通过，ledger DECLARED、consumed0、claims空，global／launcher未消费。无原规模构模、热评价、优化器或研究调用，无新性能结果。下一项只建议按冻结清单执行4次并统一分析，不增邻域、温限或SA种子，不恢复115次；当前launcher未运行。

**K.140／D164：联动版原基准质量配对取得第二阶段新增节能（E585）。** 用户“继续”承接K139唯一下一项，事前冻结旧N1→联动版各一次300秒；原完整AB／AC、400 ms／5 ms、auto-L与50°C／80°C保持。两调用均正常完成，旧U＝0.962885037941 J／147.562秒，新U＝0.910240996773 J／274.688秒，严格低5.4673236257%。[配对结论](research/chapter3_experiments/results/linked_quality_pair01/summary.md)、[存档分析](research/chapter3_experiments/results/linked_quality_pair01/analysis01/summary.md)、[本线程独审](research/chapter3_experiments/results/linked_quality_pair01/independent_review.md)保存，非主线⑥跨会话审查。

**阶段归因：** 同一fresh种子1.080823451833 J，新第一遍U＝0.962884840560 J；第二遍在206.844／208.407／209.735秒形成3次完整更新，新增下降0.052643843787 J，含setup133.422秒。AB的A整链与B.pre均H→L并调起点，后缀保持第一遍完整SAFE，设备始终固定；AC无新增。第一遍约0.197微焦耳差不归第二遍。方法合422.250秒、清理12.906秒、包装440.234秒、进程441.797秒；以更多计算换本例更低安全能耗，不称加速。

**检查与边界：** K139 66/66＋新wrapper最终28/28准入，157源／快照、155继承与1087历史保持；wrapper01测试索引失败保留，仅改测试后02通过。独立准入25／终审41项通过，160原工件hash及完整连续回执、双锚、数值门、预算与完整代一致。SAFE去重3／7，0热违规／反馈；L0约0.738286 J未闭合，最优／无解未证。2次调用结束，无补跑／延时／调温限。下一项建议回到第三章小范围公平对照准备，先核主方法与既有整体MILP／HEFT／SA接口，再单独冻结；不加邻域／阶段，不自动恢复115次或新研究调用。

**K.139／D163：单一联动块已实现，66/66必要预检通过（E584）。** 用户授权推进当前设计／实现／预检小目标，不运行原基准。第二遍每scene开A整链＋本地pre，闭合main／post到第一遍最后完整SAFE；设备仍固定原fresh种子。双完整回执／同预算绑定，原子账本取锚、二遍冻结一次，源与数值／连续热门保持。仅milp增加15行协议分派，旧N1／staged生命周期不改。[实现与范围](research/chapter3_experiments/results/linked_precheck02/summary.md)、[最终凭据](research/chapter3_experiments/results/linked_precheck02/checks.json)、[本线程独审](research/chapter3_experiments/results/linked_precheck02/independent_review.md)保存，非主线⑥跨会话审查。

**检查与静态依据：** 02共66/66、71.094秒（21新＋45旧），155源／快照、148继承及1087历史保持。01为65/66、73.265秒，新21全过，旧拒参小夹具被runner误拦；只修guard并保留161项01，生产和tests保持。小域1296赋值／96合法投影一致，默认／旧N1／旧全开放8数组回归保持；真实tiny四次自身x0回声、完整评价通过，第二遍221／243→239／262维，能量同种子。全部原生／优化器／原规模构模禁止入口尝试0，无研究求解。

**范围与下一项：** 原输入只作JSON静态核查，4开2闭；AB选项441→280、事件271→173，AC405→274、296→201；联动与全固定设备域独立活动下界同为0.140285994489 J，不当系统收益或加速。一次预定L演示仅结构合法，未评价温度／完整能量、未注入方法。新块只包含当前完整SAFE，不包含全部旧N1域，不能称全域覆盖。下一项建议单独冻结原基准旧N1→联动版各一次同预算质量配对，检验第二遍新增完整节能；本次未冻结／运行，不恢复115次、温度扫描或设备重选。

**K.138／D162：原基准质量配对完成，第二阶段141.203秒无新增节能（E583）。** 用户明确授权旧N1→两阶段版各一次300秒，不补跑／延时；原完整AB／AC三Stage、400 ms／5 ms、auto-L及50°C／80°C保持。147继承源不变，新两个wrapper最终22/22纯mock与K137 99/99共同准入，149源／快照和452历史身份一致。两调用独立fresh种子同为1.080823451833 J。[配对结论](research/chapter3_experiments/results/staged_quality_pair01/summary.md)、[存档分析](research/chapter3_experiments/results/staged_quality_pair01/analysis01/summary.md)、[本线程独审](research/chapter3_experiments/results/staged_quality_pair01/independent_review.md)保存，非主线⑥跨会话审查。

**实际结果与归因：** 旧N1 U＝0.962885037941 J、190.016秒；新版第一阶段U＝0.962884840560 J、含初始化142.344秒，第二阶段含衔接141.203秒、0完整U更新，整调用283.547秒。新比旧严格低约0.197微焦耳／0.000020499%，但全部来自第一阶段AB的B.post起点145→150 ms，不能归给第二阶段或称实用优势。初始到最终均约10.9119%节能；MATLAB启动旧56.875／新9.063秒，不把第一阶段本次更快当算法加速。完整SAFE去重3／4，0热违规／反馈，L0约0.738286 J未闭合。

**边界与下一项：** 两方法合473.563秒、清理14.437秒、包装490.141秒、完整进程492.032秒；原生合作式延迟另列，两个根预算均未越，既有SAFE未丢，6个原生请求不混作6次研究调用。第二阶段AB中间admission比终态少1条通过的final门，按终态完整记录核查，不称副本逐字同。本轮2次研究调用已结束，无补跑／调参／新热条件。下一项只建议集中审本次第二阶段根LP／整数候选前段成本后提出单一结构修订，不直接追加同类诊断或恢复115次。

**K.137／D161：两遍搜索实现与99/99必要小域预检完成（E582）。** 用户“继续”承接K136，仅实现及预检，不运行原基准。新增`execute_staged_fixed_unit_opp_start`，复用N1生命周期；一次fresh种子、同一预算／底层worker，先原N1再用余量逐场景开放全部OPP／起点。D由初始种子固定，场景内A频点与时序独立。原子完整账本是warm唯一来源，模型／事件／x0及第二遍逐请求增广映射重新建立；原行与完整连续热能耗门保持。[实现总结](research/chapter3_experiments/results/staged_method_precheck02/summary.md)、[最终凭据](research/chapter3_experiments/results/staged_method_precheck02/checks.json)、[本线程独审](research/chapter3_experiments/results/staged_method_precheck02/independent_review.md)保存，非主线⑥跨会话审查。

**实际覆盖：** 最终02共99/99、38.703秒（16新＋83旧相关回归），147源／快照一致、143继承源不变；452历史工件保持（原299＋首轮153）。首轮01同为99/99、52.828秒，因未激活R/k<60分支，只补新测试的100秒mock子例后另跑02，01保持。第二遍首片47.1秒，确认余量分配及根预算不重置；原生／优化器／进程禁止入口尝试0。真实小域两scene四个单Stage请求：第一遍276／320维，第二遍377／443→417／486维，新x0回声与完整连续复核通过，能量同种子；不是原三Stage研究案例或节能结果。

**边界与唯一下一项：** 只改N1生命周期接缝并新增独立入口／测试／预检；物理模型、输入参数、合法域、安全标准及旧默认协议保持。已有完整SAFE在劣解、无候选、拒绝x0、异常或到期后保留；局部记录可能先于完整U，须读`committed_safe_snapshot`及各`phases`。本轮0原生／研究求解、0原规模构模，无新增节能／热反馈／最优性证据，第二遍大域成本仍在。下一项建议单独冻结旧N1与两遍版本的原base__R1同预算质量配对，再执行限定调用；本次未冻结或运行，115次／温度扫描暂停。

**K.136／D160：全开放结构与搜索组织分析完成，建议仅实现两遍释放（E581）。** 用户“按照你的思路来吧”授权集中分析K135存档，不授权本轮补跑。当前144源与原档案保持，只读MAT／事件／JSON统计；未构模、热重算、原生求解或改生产程序。[集中分析](research/chapter3_experiments/results/augmented_structure_review01/summary.md)、[静态指标](research/chapter3_experiments/results/augmented_structure_review01/metrics/summary.md)及[本线程独审](research/chapter3_experiments/results/augmented_structure_review01/independent_review.md)保存，非主线⑥跨会话审查。

**核清与建议：** 旧N1固定A工作点／起点及本地pre，新版在同设备下全部开放，扩张影响事件／状态／条件行；增广再增加连续补变量及链接行。旧AB／AC新候选到原生48.920／60.288秒才发布，不能无依据把60秒拆半；当前两版因预定片段结束，未用满300秒。建议同一调用先保留旧N1的60秒片，再在剩余总时间内逐场景访问一次全Stage范围，从自身当前完整SAFE重新准备新模型x0；模型外保留完整U。设备D始终锚定原fresh种子，A共享部署与场景内OPP／起点分层，不复制旧向量、反馈列或映射。

**保证与唯一下一项：** 只能保证调度域包含与本次已认证U不回退，不能保证辅助向量提升成功、优于另一独立旧N1或HEFT、根LP变快。第二遍是余量利用与开放顺序的组合修订，不是单因素效果或已冻结研究协议。下一项建议只实现单一两遍生命周期及必要小域／mock预检，随后再决定是否冻结原规模质量调用；本轮0研究调用、无新节能／反馈／最优证明，115次和温度扫描继续暂停。

**K.135／D159：原基准质量配对正常完成，新版未优于旧N1（E580）。** 用户“继续”后冻结原base__R1、完整AB／AC三Stage、400 ms／5 ms、auto-L与50°C／80°C，旧N1→增广全Stage OPP／起点各一次300秒、scene60秒合作式限额。旧142源／60项凭据保持，新两个wrapper经19项mock预检02通过，冻结144源；01失败保留。独立准入后执行唯一launcher，无补跑／延时／新热条件。[阶段结论](research/chapter3_experiments/results/augmented_quality_pair01/summary.md)、[本线程终审](research/chapter3_experiments/results/augmented_quality_pair01/independent_review.md)保存，非主线⑥跨会话审查。

**实际结果：** 同一fresh种子1.080823451833 J；旧N1最终0.962885037941 J、159.532秒，新版仅种子1.080823451833 J、150.063秒；去重完整SAFE为3／1。新版AB返回x0同点，AC片内无新整数候选，数值−2中止未再现；32项载荷身份及原前缀门通过、无锁存。旧AB／AC首rootlp原生自报6.091／2.276秒，新AB52.058秒、新AC未发布；仅为求解前段线索，非单因素归因。旧安全安排属于新版声明的固定设备调度子域，但未免费注入。

**边界与唯一下一项：** 方法合309.595秒、包装331.094秒、清理18.140秒、外部进程332.000秒；均在单方法总截止内形成SAFE，合作式原生延迟另列。0违规／0反馈，L0约0.738286 J未闭合，历史HEFT仅质量背景。首要质量标准失败，不以稍短耗时替代；analysis02更正非空callback统计，原01不改。下一项只对已有候选、根LP／整数条件结构和场景预算集中分析，比较逐步释放决策、保留本次自己找到的SAFE等组织，再提一项修订；不再追加同类诊断、调参或恢复115次。

**K.134／D158：新版增广表达已接通完整方法，60/60必要小域预检通过（E579）。** 用户“继续”授权接入K133下一项。新增独立`execute_augmented_fixed_unit_opp_start`，每调用独立上下文、每轮按当前模型重建映射；原前缀通过原矩阵原容差后才进入合法性及完整连续热能耗评价。非法候选／缺发布等锁存取消，已有完整SAFE保留。旧固定设备入口AST／协议、138份继承源码、物理输入与安全标准保持。[阶段结论](research/chapter3_experiments/results/augmented_method_precheck01/summary.md)、[本线程独审](research/chapter3_experiments/results/augmented_method_precheck01/independent_review.md)保存，非主线⑥跨会话审查。

**等价适配与实测范围：** 小域出现b−M非无损行，K134显式只改写无损行，其余逐bit保留原式；K133严格模块不改。混合行消元核查及原AB八数组一致性通过。142源匹配，134份历史档案不变；冻结检查29.391秒，19新项＋41旧回归通过。真实小域双场景377／443→417／486维，改写397／426行、保留3／4行，回声候选→原前缀→连续评价→完整汇总走通，能量同种子。零原生／研究调用、零原规模构模，无新增节能结论；开发失败及归档错误均保留。

**唯一下一项：** 返回原base__R1质量验证，建议独立冻结旧N1→新增广版本各一次300秒、scene60秒合作式限额，原400 ms／5 ms、auto-L及完整热标准不变；变换与检查全部计费，实际原生停止延迟另列。首要标准仍是更低完整安全能量，历史HEFT仅背景。本次未启动该配对，不补K131／K133、不调温限或恢复115次。

**K.133／D157：增广表达原生数值接纳通过；原生实际调用超60秒，无新增节能（E578）。** 用户要求继续，事前冻结同一存档AB／原x0／139源，唯一一次180秒总墙钟技术检查；34项载荷＋19项driver离线预检通过后执行，没有热重算或质量补跑。新增独立载荷／检查入口，生产方法未改。[阶段结论](research/chapter3_experiments/results/augmented_native_check01/summary.md)、[本线程终审](research/chapter3_experiments/results/augmented_native_check01/independent_review.md)保存，非主线⑥跨会话审查。

**实际结果：** 原生exitflag=2（时间停止），唯一非空callback及最终向量均为原x0同点，原8525维前缀逐bit保持；原最大不等式正残差2.13e−14，等式／界／整数残差0，原1e−9／1e−6标准通过。原／新增各8项身份16/16匹配，139源和96份K131档案未变。全进程87.034秒≤180，工作81.547秒≤135，清理5.265秒且所属身份全退；MaxTime虽为60，实际intlinprog调用62.960秒，超2.960秒，不能写成严格原生60秒内完成或全部硬限通过。raw技术PASS未检查实际native≤60，须连同最终时间审计读取，不直接作后续质量准入凭据。

**边界与唯一下一项：** 0新SAFE／U／质量更新／热反馈，原K131失败不追认，数值根因和完整新版质量仍未证。下一项建议将增广表达接入新版final／callback／动态反馈，保持原行原容差门及单总截止，完成必要小域检查后再冻结质量验证；新增反馈后重建匹配载荷／映射，不能复用旧映射。原生停止延迟单列，总截止后不补U；不再泛查环境、补本次调用、调温限或恢复115次。

**K.132／D156：数值冲突已收窄，最小增广原型通过离线等价核查（E577）。** 用户要求继续，先冻结135源／K131原档案、零求解／MATLAB／候选热评价范围。唯一AB技术重建在120秒上限内完成，8项导出数组与原MAT逐项相同，构模＋导出3.375秒，不当构模加速或新方法结果。[阶段结论](research/chapter3_experiments/results/numerical_conflict_audit01/summary.md)、[本线程独审](research/chapter3_experiments/results/numerical_conflict_audit01/independent_review.md)保存，非主线⑥跨会话审查。

**定位与方案：** 最大系数比行13838在原x0处未激活；浮点最坏行16380精确残差为负，另67条紧行仍有微小正残差（最大3.06e−15），所以只保持容差接纳。全joint取补因269条能量下界行右端不能精确表示而拒绝。保留原w，新增v∈[0,1]且v+w=1，只将24000条物理条件行改写为减M·v；全部b−M无损导出，消元精确恢复原行，39733行连续gate样本残差恒等。其余行、441整数坐标及原目标保持；变量8525→10925、总行39733→42133。原最大系数比不变，原生根因仍未证。

**边界与唯一下一项：** 只实现存档代数原型，生产未改；原x0浮点残差下降不当作已修复或新SAFE。链接容差可向原行放大约6.02e−8，未来final／callback原前缀必须按原矩阵原容差复核，不通过则数值路径未决，独立完整物理SAFE仍保留。下一项建议冻结一次原生接纳技术检查：同一存档AB／原x0／唯一增广表达，总墙钟180秒含清理、native至多60秒且受剩余时钟约束；不热重算、不补K131、不作质量排名。此项尚未执行，生产桥接和新版质量仍未完成；115次及调温限继续暂停。

**K.131／D155：排故后质量配对已执行，新版因数值状态冲突停止（E576）。** 用户要求继续，独立冻结旧N1→固定设备全Stage OPP／起点各一次300秒、scene60秒；原base__R1、完整AB／AC链、400 ms／5 ms、auto-L及50°C／80°C保持。两次fresh种子候选及初始能量逐字一致，135源和输入匹配；未借历史答案。[结果与U曲线](research/chapter3_experiments/results/fixed_unit_pair02/analysis01/summary.md)、[本线程终审](research/chapter3_experiments/results/fixed_unit_pair02/independent_review.md)已保存，非主线⑥跨会话审查。

**实际结果：** 旧N1完整安全U＝0.962885037941 J、方法154.047秒；新版只保留初始完整SAFE U＝1.080823451833 J，72.781秒因SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED停止，AC搜索未启动。AB显式8525维x0在1e-9约束／1e-6整数容差内通过，worker确实收到相同向量，但intlinprog返回exit−2及空x／fval，未给有限内部界。独审从现存MAT重算最大不等式残差2.13e-14，其余等式／界／整数残差0，未发现传输错位；仍不是精确可行证书，也不能认定真实无解或求解器缺陷。原输入安全种子不被该退出撤销。

**阶段判断与下一项：** 两次调用已消费，方法合226.828秒、包装247.296秒、清理19.969秒；均正常退出、所属身份全退，本轮未再现I/O／清理故障。3份旧／1份新完整SAFE汇总审计通过，0热违规／反馈，L0未闭合。质量配对未正常完成，不把技术中止当作开放范围无效或完成性能排名；旧K129失败不追认。下一项只针对已存AB载荷定位数值表达问题，先核条件行尺度与辅助量边界，不补跑、扩时、调温限或恢复115次。

**K.130／D154：运行链路已通过连续双会话验收，可恢复新版质量验证（E575）。** 用户要求先排故，本轮零求解／构模／热评价。定位并修复清理权限、强杀非零误判及父子退出确认竞态；保留原退出码、强制事实和成本。READY／清理前记录所属PID与创建时间，在原40秒总窗口内确认已观察身份退出，权限／身份／存活未决均不放行。N1与固定设备入口统一判定，不覆盖原启动／求解／归档失败或SAFE。[排故结果](research/chapter3_experiments/results/runtime_io_probe05/summary.md)保存。

**最终验收：** [129/129回归](research/chapter3_experiments/results/runtime_io_precheck02/checks.json)、19.797秒，135源及默认／旧N1小域数组核对通过；获批host上下文同Python连续两次空闲MATLAB启动／读写／退出40.140秒完成。一轮forced_closed、另一轮graceful_closed，各3个已观察所属身份均退出，额外只读核无残留；零request。原02／03／04技术失败保持，六次技术READY／五程序墙钟合162.141秒（不含分析编码），没有补跑K129。用户缓存前后哈希均不变，未删除缓存或改全局配置。

**保留的未知与下一项：** 历史Errno22未复现、直接根因未证实；本机原mtime表明READY晚于K129失败约17秒，不能把后来READY当成功握手。MATLAB自然退出有时慢，仍靠有记录的强制收尾；不继续泛查环境。下一项只回到原模型的新版质量验证，所有方法统一使用已验收执行上下文、统一计费；启动仍计费、清理单列。原K129新版U仍缺失，不追认或改绿，115次和温度扫描暂停。

**K.129／D153：固定设备、全Stage工作点／时序已实现；质量配对因归档故障未完成（E574）。** 用户认可同预算、同完整安全下先优于旧N1的成功标准并要求推进。新增独立`fixed_unit_method`／范围／原输入包装，旧N1定义保持。所有设备固定本次新种子，每scene全部Stage OPP／起点开放，包括共享A；共享具体unit与场景内频点／时序仍分层。[审查稿K.129](research/第三章当前进展与正式实验推进计划_审查稿.md#k129全stage工作点与时序实现质量配对因归档故障中止)维护详细范围。

**实际结果：** [冻结配对](research/chapter3_experiments/results/fixed_unit_pair01/analysis01/summary.md)只消费旧N1→新版各一次300秒上限，无补跑／延时／新热条件。旧N1完整安全U＝0.962885037941 J，首SAFE0.860秒、方法165.672秒；新版包装25.265秒后最终归档发生OSError errno22，未保存方法结果，U留空、质量未验证。两个模型及视图SAFE／x0检查点存在，不能补成原输入全聚合U；两次包装196.328秒，不冒充方法合计。无原生请求文件，READY不等于已入intlinprog。最早触发错误仍未知，不能归因于模型／算法质量。原档案和132源快照保持。

**预检与修复：** 运行前02中84/84通过，默认／旧N1数组及rows／options／summary与`3859cbe`一致；01的临时目录setup失败记录保留。实际故障暴露收尾归档及启动清理的异常遮蔽：已最小修复错误分列、内存SAFE／原错误／时序保留和本次进程清理，不重启求解。修复[预检04](research/chapter3_experiments/results/fixed_unit_precheck04/checks.json)117/117、20.500秒、134源匹配；03因禁启guard过早拦截旧Cut非法构造参数测试而失败，原记录保留，修正预检guard粒度，不放开真实进程。新凭据不能追认失败调用。[本线程独立审查](research/chapter3_experiments/results/fixed_unit_pair01/independent_review.md)非主线⑥跨会话审查。下一项应独立冻结修复后的新版质量验证；115次、温度扫描、设备重选暂停，本轮不补调用。

**K.128／D152：HEFT—N1集中分析完成，建议固定设备、开放全Stage的OPP和时序（E573）。** 已保存[方法分析与修订建议](research/第三章当前进展与正式实验推进计划_审查稿.md#k128heftn1差异与下一版局部milp范围只读分析完成)、[精确存档代数](research/chapter3_experiments/results/method_revision_analysis01/activity_facts.json)。原N1四个可变Stage均已取固定unit的最低活动能量，总活动项0.213194664232 J达到该子域独立下界；继续原N1不能再降活动项，仍可能改善基准／温度项，非总能耗最优证明。释放A、再释放本地pre的乐观活动项下界依次0.148298957452、0.140285994489 J，均不当可实现节能。

**两层与范围：** 共享A只统一具体unit，各scene的A OPP／起点独立。建议先保持全部unit为本次新种子，联动开放每scene全部六Stage OPP／起点；不把这称为共享部署重选。仅开频点会碰后继固定起点，仅开A仍受本地pre的共享域H片段约束，因此暂不另造小块协调。现N1显式拒绝开放共享Stage，需版本化新条件；已有固定a接口已经更宽，不宣称新表达能力。变量／事件会增加，收益与运行成本待验证。该具体范围仅助手推荐，用户本轮授权的是分析；未改算法／输入、构模、热评价、求解或预检，原125源保持，115次及热扫描暂停。下一项只建议实现该新条件及必要小域核查，新研究调用须另定协议。

**K.127／D151：夜间授权范围内六次调用完成，热约束改变选择，HEFT本次优于N1（E572）。** [夜间总结与证据](research/chapter3_experiments/results/night_k127_run02/night_summary.md)已保存。预先冻结一组50°C入口／52°C温限，原物理、完整三Stage、400 ms／5 ms、auto-L不变；热配对两次均H明确违规→M完整SAFE，U同0.962111586360 J。与80°C调用同H候选／轨迹直接对照，支持热约束接纳和选择作用；0外层反馈／0新增行，不支持反馈收益。收紧温限后的较低预算内U是构造访问路径差，不能称真实最优能量下降。

**原base单次公平比较：** 整体MILP／N1／HEFT／SA101安全U依次1.084886371304／0.962884840560／0.881087997281／0.907346431253 J，方法耗时300／139.828／46.047／300秒。各方fresh输入、初始化及完整连续复核；HEFT本次质量和时间优于N1，SA仅固定101探索。N1严格改善自身种子约10.912%，但冻结了HEFT实际调整的共享A工作点／设备和pre，不能替代强基线优势。L₀约0.738286 J均未闭合，最优／不可行未证；N1内部界不升全域。

**完成边界：** 67／67必要预检、125源匹配、六份最终SAFE存档核验通过。实际方法合1385.875秒、包装1416.578秒、清理28.110秒；消费6／8次，每项上限300，无补跑／延时，整体不足1小时。本线程独审不是主线⑥跨会话审查。研究调用已结束；不启动115次、五组扩展、N2或温限扫描。下一项只建议据真实选择差讨论最小候选覆盖修订，尚未实施／授权新研究调用。

**K.126／D150：唯一一次原基准N1诊断取得初始化外的严格节能（E571）。** 原base__R1、共享A＝CPU1→NPU0→CPU1、完整AB／AC、400 ms／5 ms、auto-L、50°C／80°C不变；只开本地main＋post的OPP／起点，设备全固定本次新种子。一次300秒总预算、每scene60秒合作片、CDF off／Cut10；正常完成，54源一致、无补跑／延时。[结果与U曲线](research/chapter3_experiments/results/neighborhood_diagnostic01/analysis01/summary.md)、[本线程独审](research/chapter3_experiments/results/neighborhood_diagnostic01/independent_review.md)已保存，非主线⑥跨会话结论。

**实际结果：** 本次种子1.080823451833→最终0.962885037941 J，最终上端严格低于种子下端，减少0.117938413893 J／10.9119%。首SAFE0.812秒，严格更新129.703／204.500秒，方法204.531秒、清理9.234秒。两个原生请求确认2个新安排，7次后续接收含3次重复；B／C main＋post均H改L并调整起点，A／pre不变。C.post本次固定CPU1，不套旧CPU2。L₀＝Lₐ≈0.738285994489 J，保守差距23.3256%，未证最优／无解。两scene均提前停止、nodes0，不能写成收敛。

**边界及唯一下一项：** 最终最高峰约51.178°C，0违规／0反馈，本次只支持节能搜索进展，不能证明热反馈有效。全部SAFE经预算内原输入完整连续评价与全聚合；事后只读核验8/8、113原档案保持。60秒合作片实际约69.515／61.985秒，总截止未越；剩余预算未补搜索。N1是局部域，历史K122不是单因素control，不外推完整部署搜索或基线优势。节能已有本次正例，下一项建议集中整理热约束／反馈最小对照协议，优先复用已声明压力条件，先冻结共同比较口径；不继续扫冷态N1或加N2，本轮未追加调用／改参，正式比较尚未恢复。

**K.125／D149：N1方法生命周期已接通，最终必要预检45/45通过（E570）。** 新独立`execute_n1_neighborhood`在同MethodBudget中完成fresh构造→原输入全场景SAFE种子→N1条件构模／x0→候选回调／连续反馈→原输入复核及全场景U更新。旧生产源码、参数、合法选择与历史结果保持。没有完整安全种子则未决；x0拒收可裸求解；已有SAFE与技术异常分列。[结果](research/chapter3_experiments/results/neighborhood_method_precheck02/summary.md)、[本线程独审](research/chapter3_experiments/results/neighborhood_method_precheck02/independent_review.md)保存，非主线⑥跨会话结论。

**实际核查：** 01为修订前44/44、13.969秒；复审补正Lₐ中断时保留已成L₀，02为45/45、14.140秒，53源与快照匹配。最终23项新生命周期、16旧partial及6包装回归通过；真实小域两物理模型／六次连续评价、276／320维x0数值接纳。模拟session只回声本次x0，最终包络等于种子；零原规模／优化器／MATLAB／研究调用，没有新搜索或节能结论。01保留旧hash范围，不冒称覆盖修订后源。

**完成边界与唯一下一项：** 方法收益只相对本次种子；完整视图构造可能与旧partial逐scene初始化不同，不能借K122做单因素对照。N1内部界和无解不升级全域结论。下一项建议冻结并运行一次原`base__R1`首共享部署的N1质量诊断，仅开本地main＋post的原OPP／5 ms起点，重点核初始化外的更低完整安全U及成本；预算／调用协议尚未冻结，本轮未启动。不加N2、热近似、参数或额外预检层，不恢复正式批次。

**K.124／D148：N1条件接口已实现，必要小域预检43/43通过（E569）。** 用户“可以继续下一步”确认K123提出的薄接口／小域范围。新增条件模块、原输入评价包装与默认None构模参数：所有设备固定种子，只有明确开放的本地Stage保留原OPP／起点；其他工作精确unit＋OPP＋Fraction起点固定。条件按(scene,Stage实例)绑定原输入、完整聚合SAFE回执、源及同Budget，选项过滤在事件展开前，不改原模式表／物理值。[结果](research/chapter3_experiments/results/neighborhood_precheck01/summary.md)、[本线程独审](research/chapter3_experiments/results/neighborhood_precheck01/independent_review.md)保存，非主线⑥跨会话结论。

**实际核查：** [一次43/43](research/chapter3_experiments/results/neighborhood_precheck01/checks.json)，21.344秒、50源前后匹配；32项新检查＋11旧累计回归。N1小域36种赋值／24合法与独立oracle一致；旧144／80回归保持。小结构默认8组数组及rows／options／summary与bd9293c相同。真实夹具的同Budget种子→条件模型→原输入复核／原聚合闭环通过，276维x0解码与数值行接纳；只是正确性夹具，未产生原规模SAFE或节能。共22个当前小域构模（1物理）、另1旧源结构、4次真实小域连续传播，零LP／MILP／MATLAB／研究调用。

**完成边界与唯一下一项：** 默认／None保持；旧full fixed_deployment拒auto-L、正式starts限制保留。原评价回执不改写，内层已成证据跨外层截止保留；局部界不升全域。当前只有条件构模及评价接口，尚未接通N1方法级搜索或验证收益。下一项建议一次接完fresh初始化→条件构模／x0→候选原输入复核／反馈→同Budget全场景U更新，完成必要端到端预检，再确定一次原基准质量诊断；本轮不启动该调用、不调参数、扩大预算或叠加N2。旧凭据按历史源范围保留，不冒称旧整包gate匹配新milp。

**K.123／D147：已审f60469d，只读盘点支持先做本地main＋post的固定设备邻域（E568）。** 采纳逐Stage能耗／余量与N1／N2比较；四阶段作为边界，不再加重复准入。未变研究输入、原方法及热安全，不构模／求解／新热评价。[机会表与精确事实](research/chapter3_experiments/results/local_neighborhood_audit01/summary.md)、[本线程独审](research/chapter3_experiments/results/local_neighborhood_audit01/independent_review.md)保存，非主线⑥跨会话结论。

**发现与取舍：** 当前12份Stage均H。加权能耗分项为基准0.545725、活动0.302450、公共0.120000、温度修正约0.112648452 J；其中全L基准＋公共0.620000 J是温度无关固定部分，不能沿用旧hold尾段归因。B／C请求余量76.3／75 ms；本地main＋post原活动项0.177450 J，占活动能耗58.6709%。推荐仅开放这两份Stage各自原OPP和5 ms起点，设备保持NPU0／GPU0及CPU2；A与本地pre的精确选项暂固定。AB／AC静态选项167／137、事件150／144（原654／601、271／296），不是完整安排数或求解成本。低档联动post示例结构可行，但无新SAFE或完整节能结论。

**K.123结束时的下一项（已由K.124实现并预检）：** 实现独立N1条件接口及必要小域校验，按(scene,Stage实例)在事件构造前保留选项，绑定原输入、本次新初始化和邻域身份；仍完整评价四节点、auto-L与原期限。旧full fixed_deployment拒收auto-L，不能直接复用；starts形参不得伪装fixture。局部条件不改一般原域，局部界不提升全域；N2保留，不同时实现。研究预算尚未确定，不自动补跑K122或开展新调用。

**K.122／D146：累计前置关闭／开启配对完成，未取得初始化外的能耗改善（E567）。** 原`base__R1`首共享条件A＝CPU1→NPU0→CPU1、完整AB／AC及本地选择保持；先off后on，均Cut=10，各300秒总上限、每scene一个60秒合作式片。两调用正常结束、41源未变，无补跑／延时／技术故障。[结果与曲线](research/chapter3_experiments/results/cumulative_pair_diagnostic01/analysis01/summary.md)、[本线程独立审查](research/chapter3_experiments/results/cumulative_pair_diagnostic01/independent_review.md)保存；后者非主线⑥跨会话审查。

**结果：** 两版U均1.080823451833 J，原始完整区间均等于各自初始化；0新decoded安排、0严格改善、0热反馈。AB全部非空向量精确等于本次x0，AC最终向量均空，四请求节点均0。首SAFE为26.234／26.375秒，方法249.875／167.782秒，清理6.265／6.109秒。独立L0＝L_a＝1152169123/1560600000 J（0.738285994489 J），保守gap31.6923%，最优／无解未证。AB单场景未加权内部界只提高0.000186010306 J，不能代替系统认证界或节能结果。

**归因与完成：** ON仅追加AB99／AC91行、共16656非零，旧A/b前缀及其余六组数组相同；CDF测量组件约0.029105秒。总耗时差82.093秒中，startup差54.312秒；AB合作片实际97.453／69.797秒，均超软60片但未超总300。单次差异不足以归因CDF加速。入口[11/11](research/chapter3_experiments/results/cumulative_pair_precheck01/checks.json)及只读后处理[6/6](research/chapter3_experiments/results/cumulative_pair_diagnostic01/analysis_precheck01/checks.json)通过，K.121凭据按未变源复用，没有重跑整包。累计开关保持默认关闭，不据本例断言一般无效；原400 ms／5 ms、自动L、物理／合法域和连续SAFE标准保持。

**K.122结束时的后续建议（K.123已完成只读盘点）：** 暂停根割／CDF追加实验，先只读盘点本次安全初始化的能量构成、工作点与时序余量及原合法替换，审查一个小邻域MILP改善接口是否值得实现，目标仍是生成更低能耗整数方案。该项不运行新热评价／求解，不预定邻域或裁减原问题；本阶段至此结束，不恢复正式批次或扩大预算。

**K.121／D145：累计前置已作为默认关闭的表达强化接入，必要预检通过（E566）。** `build_model(..., cumulative_precedence=True)`在全部旧行之后追加直接边CDF约束，保留原期望依赖、选项、变量、目标、事件及热表达；不取整结束。真实y索引与精确Fraction前缀生成，空前驱prefix行保留，只删已证恒真／精确重复；生成、统计及导出均计入原Budget。默认省略与False不增加formulation／summary键；scene／partial沿原builder_options显式传参，shared沿既有condition_options转发。

**实际核查：** [最终02](research/chapter3_experiments/results/cumulative_precedence_precheck02/checks.json)62/62、27.750秒，39源匹配；22项新测试及40项受影响模拟回归。144个两Stage小域完整安排中80合法、64非法，旧／新结构表达与独立oracle一致，保留合法等待、非整数结束、跨场景同名选项和中断状态。[旧源矩阵对照](research/chapter3_experiments/results/cumulative_precedence_precheck02/default_matrix_identity.json)按`229eef8`源码做三次小型物理构模：默认导出与旧版逐项相同，True仅追加1行／14非零；[归档局部行核对](research/chapter3_experiments/results/cumulative_precedence_precheck02/archived_rows.json)另确认AB／AC生产行99／91、9306／7350非零，38条空prefix及已存x0的y均保留。未重建原规模完整模型、未解LP／MILP／启动MATLAB或新算热轨迹。

**失败记录与下一项：** [01](research/chapter3_experiments/results/cumulative_precedence_precheck01/checks.json)仍为false，62项中记录115个Windows临时目录访问／清理错误；02仅改沙箱外执行权限，全部源码SHA与01相同，不将两次写成一次全通过。本线程[独立审查](research/chapter3_experiments/results/cumulative_precedence_precheck02/independent_review.md)另存，非主线⑥；旧整包凭据不冒称适用于新源。本轮只证明接入范围与正确性，没有新U、节能或加速结论。K.121结束时建议下一项按已声明范围做累计开关关闭／开启同预算配对；该项现已由K.122完成，未叠加其他优化。

**K.120／D144：累计前置是有效的局部松弛强化，静态成本已核清（E565）。** 原`milp.py`699／705—709行在one-hot整数选择下正确；放松后只约束期望结束≤期望启动。新关系按每条直接边、每个不同后继合法启动τ约束“已启动的后继质量≤已结束的前驱质量”；完整族保留所有真实合法整数安排，在非负归一化分数域可严格强于原行。非整数结束用Fraction、同刻可接，原期望行保留。本轮只新增独立代数／静态核查入口，未接入生产MILP，不产生加速或节能结论。

**核查结果：** 一次[11/11代数单测](research/chapter3_experiments/results/cumulative_precedence_audit01/unit_checks.json)覆盖384个局部整数选项配对；[薄核验7/7](research/chapter3_experiments/results/cumulative_precedence_audit01/verification.json)复核两种独立生成口径、成本复跑及已存x0通过全部190行。K.119首条件AB／AC仅新增99／91行、9306／7350非零，合计行约增0.146%、非零约增1.221%，不增变量或重建热事件；38条前驱空prefix的非平凡行均保留。[逐弧成本](research/chapter3_experiments/results/cumulative_precedence_audit01/reproduced/costs.csv)与全部8条原矩阵依赖行逐系数匹配；静态规模不代表实际耗时。

**范围与下一项：** 局部分数反例不冒充当前完整LP最优点；旧回调没有保存该分数向量，不能认定它已是本例主瓶颈。原34生产／输入源及K.119结果保持，零新模型／LP／MILP／热／研究调用。[本线程独立审查](research/chapter3_experiments/results/cumulative_precedence_audit01/independent_review.md)另存，非主线⑥。下一项建议将累计行作为默认关闭的可选强化接入，保留旧行，核默认矩阵不变及开启后的精确新增行／小域合法集合，再决定一次有界性能验证；当前不启动该调用、不调参数或继续扫割设置。

**K.119／D143：根割单因素配对完成，未观察到节能或搜索进展收益（E564）。** 原`base__R1`首共享条件A＝CPU1→NPU0→CPU1，先10后1，各一次300秒独立总上限、AB／AC各60秒合作式片；原输入／自动L／连续安全不变。两调用均正常完成，34源不变，无补跑、延时或技术故障。[结果与图](research/chapter3_experiments/results/cut_pair_diagnostic01/analysis01/summary.md)保存同模型、同计量标准的本次对照，不以K.116当control。[本线程独立审查](research/chapter3_experiments/results/cut_pair_diagnostic01/independent_review.md)另存，非主线⑥跨会话结论。

**结果：** 两版完整初始化与最终能量区间相同，U＝1.080823451833 J，0后续改善、0新decoded安排、0热反馈；L0＝L_a＝0.738285994489 J，可信gap31.6923%，未证最优／无解。10／1的首SAFE为22.359／23.719秒，方法160.484／160.922秒，清理5.953／6.906秒。每版AB只返回本次x0、AC返回空，四请求节点均0。实际选项分别10／1，首模型八组数组指纹全同；除预算派生MaxTime差异外，其余设置相同。0.438秒单次差异不作速度结论。

**完成与下一项：** 生产只增加可选会话级cut传递；None继续原默认，本次不将1推广为主方法。首轮49/49及[最终50/50](research/chapter3_experiments/results/cut_pair_precheck02/checks.json)均保留，后者绑定34源；K.117读取尾块及原73/74 false保持。本项到此停止，不扫其他割设置。下一项建议回到分数松弛，优先核现有依赖仅约束期望时刻是否过弱，推导一项累计前置强化及其必要小域检查范围；不自动启动新研究调用，不改物理／合法安排或安全标准。

**K.118／D142：九次既有日志已核清，下一项只建议验证根割轮数上限（E563）。** 本轮零构模／LP／热／求解及生产代码变更。[逐请求CSV及事实](research/chapter3_experiments/results/shared_search_diagnostic01/log_analysis01/facts.json)确认：9次均传入本次x0，7次完整返回及所有非空callback向量与对应x0逐元素相同，2次最终向量为空；没有输出新方案。7次已报告rootlp→heuristics及有限内部界，转段报告的求解时间21.409—52.580秒，不能把节点0解释成根LP均未完成。第7次到58.442秒仍报告cutgen，界未出现可辨识提升；其他请求的后段阶段耗时未细分。[独立审查](research/chapter3_experiments/results/shared_search_diagnostic01/log_analysis01/independent_review.md)8项核查通过，非主线⑥跨会话结论。

**代价与限制：** 九次原生调用合计625.232秒，占方法763.156秒约81.93%；构模89.453秒，九次搜索内连续复核3.641秒。跨进程时间重叠不相加；所有原生终止消息均报告MaxTime，不能从cancel文件单独推断停止原因。当前最直接待解决的是在预算内输出不同于初始化的整数方案；没有依据把零收益归为温度检查误删，也尚未定位某类模型行是唯一瓶颈。

**唯一建议，尚未实施：** 将`CutMaxIterations`由已归档默认10单独限为1，保留`CutGeneration=basic`、60秒片、模型和全部其他设置。它是进入分支前割轮数的工程上限，实际已做轮数未保存；减少上限可能更早进分支，也可能削弱界，不能预设节能。最小后续配对提案在[原计划K.118](research/第三章当前进展与正式实验推进计划_审查稿.md#k118九次既有日志的瓶颈归因与唯一后续候选)统一维护：只给定首条件A＝CPU1→NPU0→CPU1，保留完整AB／AC及本地自由决策，10／1各一次、各300秒总上限及各场景60秒片。该范围／预算是助手提案，未批准或执行，不补K.116、不启动正式比较。先接单开关并做必要表达／记录核对；不叠加启发式切换、累计前置约束、DAG过滤或新种子。K.117自然退出限制及73/74 false保持。

**K.117／D141：MATLAB请求读取修复已按范围验证，进程自然退出仍有局限（E562）。** 只改`solve_model.m`：可识别文件打开失败最多重试2秒、间隔10毫秒，坏JSON在循环外立即报错；读前／后检查取消、stop及guard，沿原requestClock扣费，不重置请求或方法截止。原Python发布、数学表达、物理参数、容差及SAFE接纳保持。[实现与预检入口](research/chapter3_experiments/README.md#312w-matlab请求读取修复与分范围验收k117)。

**实际核查：** 原12项纯Python桥接测试通过。唯一一次180秒接口预检使用同worker六个1变量请求，80.828秒、清理20.344秒：真实短锁拒读1次后恢复求解；持续拒读107次／2.005秒后ERROR；坏JSON不重试，取消／stop均不入solver，后续普通请求恢复。同一总截止、K.116旧记录及其余源保持。原报告为**73/74、passed=false**：唯一失败是5秒内OS进程退出；随后原20秒清理也需强制结束进程树，自然退出尚未证实。[独立审查](research/chapter3_experiments/results/request_read_native01/independent_review.md)接受读取修复范围，保留原预检false及清理限制，不洗绿或补跑。

**完成与下一项：** 本轮零物理构模、热评价和研究调用，未增加SAFE／U或节能结论，未重跑K.116。原57/13整包凭据不冒称匹配修改后的worker；本次核新I/O路径，数学与数值模块按未变源复用。读取修复阶段结束；清理成本及兜底保留为实现限制，不再新增关机速度准入门槛。下一项优先读取K.116已有九次求解记录，确定内层优化无进展的一个针对性改进点，再决定验证范围；不直接恢复批量实验或延长预算。

**K.116／D140：唯一一次原完整链诊断已结束，保留SAFE但因接口错误提前停止（E561）。** 原`base__R1`、自动L、400 ms／5 ms及原物理参数不变，一个900秒总预算、一个MATLAB worker、每场景60秒合作式片。实际访问5/16个共享部署、发出10个请求；方法763.156秒、清理7.594秒。第10请求在MATLAB读取请求JSON时`Permission denied`，尚未进入`intlinprog`，按规则停止，无重试或延时。这是技术失败，`SAFE`仅表示已有安全证据保留，不能当整次技术通过。

**安全输出与优化结果：** 26.640秒形成首次完整SAFE；最终U＝1.080823451833 J，与本次5套完整初始化的最佳值相同，内层／换a均无全局改善，0热反馈。独立全域L0＝0.738285994489 J，保守相对差距31.6923%，未证最优或无解。其余11条件未访问，已访问条件亦未穷尽。此前9次实际`intlinprog`均时间限停止，原生报告节点数均0；626.454秒为等待／响应读取，89.453秒构模，不能把等待全部归为某个求解器内部阶段。结果、U(t)及逐条件表见[诊断汇总](research/chapter3_experiments/results/shared_search_diagnostic01/analysis/summary.md)和[README §3.12v](research/chapter3_experiments/README.md#312v-一次原完整链共享部署搜索诊断k116)。

**结束与下一项：** 29项源／输入快照与既有57/13凭据绑定；本次已有SAFE、L0及数值包络只读审计通过。独立终审另存（本线程，非主线⑥）；后处理初版6项、修订8项测试通过，图表修订不调用求解／热评价，不补研究调用。阶段结束，不因故障补跑。下一项优先修复并预检MATLAB请求读取的瞬态失败处理；具体占用进程仍未知，不能据`Permission denied`认定永久ACL错误。修复前不启动正式比较；当前无初始化之外节能或热反馈收益证据，不调物理参数。

**K.115／D139：外层首遍搜索与合作式时间片已实现，必要预检通过（E560）。** 新`shared_search`按K.114轮转16个共享部署，单Budget、懒启动同一个MATLAB worker，逐a构模／初始化、各场景固定片、不回访；新a初始化、内层候选和换a分开记账。`partial_method`兼容接入外部Budget／会话；桥接新增独立原生软上限，Python响应与证据仍用总截止。[README §3.12u](research/chapter3_experiments/README.md#312u-共享部署首遍搜索与合作式搜索片k115)维护实现与预检入口。原参数、表达、连续数值核及旧研究结果保持。

**预检：** [模拟04](research/chapter3_experiments/results/shared_search_precheck04/checks.json)57/57、6.219秒（52单测＋5完整性），零实际构模／热／优化器；含16项受影响旧路径。独审补正全部初始化包络的严格比较、pre/main/post排序键及Recorder／Model—Observer引用环。唯一一次180秒内[原生接口](research/chapter3_experiments/results/shared_search_native01/verification.json)13/13：方法20.093秒、清理8.766秒；一个99变量小模型、同worker两请求，首次实际因`MaxTime=1e-6`秒停止，未找到整数可行点，第二默认正常求解、结构合法。没有真实热评价或新SAFE／能耗结论。01／02失败及03通过后的审查修订记录保留，28项源码／输入与快照绑定；只复用未变模块，不宣称旧整包准入仍匹配当前桥接。

**完成与下一项：** 本轮只完成实现及必要预检，不运行900秒完整链、旧批次或正式比较。下一项直接落实K.114的一次原`base__R1`完整链900秒诊断及一次性记录，核初始化之外的安全能耗改善；不继续加预检案例、调配额或热压力。总预算／片超出、未访问及数值状态仍单列，零改善如实结束，不补跑。

**K.114／D138：完整链共享部署搜索诊断协议已整理，未执行（E559）。** [原计划K.114](research/第三章当前进展与正式实验推进计划_审查稿.md#k114一次完整链共享部署搜索诊断协议待实现待执行)维护唯一规则。建议原`base__R1`完整AB／AC三Stage、自动L下只做一次900秒总预算诊断；16个A共享部署保留，按A.main四种具体单元分组轮转，逐a懒构模／初始化，AB、AC各一个固定60秒合作式搜索片，首版不回访。不新增物理参数、对照或研究案例。每次U更新分列初始化／内层候选与是否换a，并与本次最佳完整初始化能量比较。

**接口与停止：** 现有单a入口不能直接循环16次；须接单绝对Budget、一个worker和独立原生软上限，不能把短`remaining_s`当可续接配额。片末正常收束后才换任务，跨片但总截止前证据可接纳、超出单列；总截止后不补U，单条失败不排a。全局L0、条件L_a及内部界分列。下一阶段只补这些接口及必要预检，新增原生接口预检最多一次180秒，与900秒研究调用分开。当前900／60、180秒接口预检及访问规则均是助手提案，尚未获具体运行批准；本轮零程序变更、构模、热评价或求解，不恢复旧批次／Goal。

**K.113／D137：给定共享部署的统一预算内层流程接通，原生小域完成（E558）。** 新`partial_method`先取得全部场景的本次初始化回执，再用一个新MATLAB会话按原场景顺序求解；callback安全候选即时原输入复核并更新全局U，可信违规合作停止当前请求、收到正常回执后加原热反馈。新独立界接口给出原域L0与固定H条件L_a，分开scope与solver-reported内部界；已成界、SAFE及违规在中断时保留。[README §3.12t](research/chapter3_experiments/README.md#312t-给定共享部署的统一预算生命周期k113)维护唯一实现／复跑说明。

**验证结果：** [39/39模拟代数](research/chapter3_experiments/results/partial_method_precheck02/checks.json)，34单测＋5完整性、2.453秒，0真实构模／热传播／优化器；K.112表达凭据匹配复用。随后唯一一次180秒小域[14/14验收](research/chapter3_experiments/results/partial_method_native01/verification.json)通过：原两个场景各一个A.pre，共享CPU1、起点0，物理及400 ms窗口不改，两次实际请求、各注本次x0并工程级收敛。初始全局U=0.736704563597 J在1.312秒形成，callback来源原输入复核在29.422／31.812秒提交0.729707535086、0.722710506574 J，均早于对应Python solve返回，且与前包络严格分离。方法31.844秒，清理7.859秒另列，0反馈；独立L0／L_a均48781/81000 J，未闭合，不记独立最优。[内部终审](research/chapter3_experiments/results/partial_method_native01/independent_review.md)非主线⑥跨会话结论。

**范围与下一项：** 初版模拟01为38/38；独审随后发现保留SAFE不能掩盖技术异常，只补验收和断言形成02，生产实现未改，唯一原生调用未补跑。常规实现新增无／拒收x0时的裸MIP回退，须在后续对照中统一或单列，不称旧初始化行为完全不变。本轮仅处理一个给定a、证明后续候选可更新全局方案，未实现外层搜索或验证完整链性能、热反馈收益。原参数、正文和115项／Q1／K.108不改，旧24档案保持，不启动新Goal。下一项收拢一次原完整三Stage诊断的共享部署范围和统一预算，再实施外层组织；不继续堆预检，不自动运行16条件或正式对照。

**K.112／D136：自动L的MILP表达／物理补全、仅共享部署构模及候选合并通过小域核查（E557）。** 非L活动支持行配合原锁频／one-hot，空域必L；auto取消空闲保持行，按真实半开事件处理，两种lift／x0同步，无新增busy整数变量。新`fixed_shared_deployment`在原完整输入识别H，只固定跨场景具体单元，保留本地B／C及其频点／时序；新partial协议区分外层条件与本地求得部署，合并后核原输入，全场景含零权重匹配SAFE才提交加权U。[README §3.12s](research/chapter3_experiments/README.md#312s-自动l的milp表达与仅共享部署接口k112)维护实现及复跑入口。

**预检与边界：** [最终02](research/chapter3_experiments/results/auto_milp_precheck02/checks.json)71/71、19.922秒，59单测＋12完整性；408条小域赋值／197合法安排在两种辅助整数设置下与独立检查一致，另36条部分固定赋值核场景乘积／外层并集。真实SAFE单Stage的两种补全通过原x0容差，4条导出能量下界行／证书的7个状态检查均通过；两个真实partial场景完整SAFE在同一Budget加权合并。每轮6次连续传播、2次传播前截止，25次当前及2次旧参考小域构模，零优化器／研究调用；28项源码输入、原数值核心及旧24档案保持。[内部独立终审](research/chapter3_experiments/results/auto_milp_precheck02/independent_review.md)另存，非主线⑥跨会话审查。首轮01为70/71：测试将L档支持设备积误当满足原期限的可行积；仅修订预期后通过，未改实现或研究输入。

**下一项：** 接通仅固定共享部署的内层求解／反馈、同一预算和全场景U更新，先小域端到端。当前不是完整方法已可运行或研究节能结果；HEFT／SA、旧方法下界及旧完整fixed-deployment的auto路径继续拒收，相关适配留待对应阶段。原参数、正文、115项／Q1／K.108结果不改，不启动新Goal。外层排序／配额、原规模清单和预算仍未确定，最终质量目标仍为预算内更低完整安全能耗。

**K.111／D135：自动L共同轨迹与连续评价已实现，必要预检67/67通过（E556）。** 新`auto_low_immediate_v1`按K.110规则处理整域空闲、同刻结束／启动、同频并发、非整数结束、入口及完整400 ms尾段；由显式转换工具深复制执行规则，原config_v01和全部数值参数保持。共同评价仍采用原连续数值核与误差要求，新回执绑定完整输入／候选身份，旧规则及回执兼容。[README §3.12r](research/chapter3_experiments/README.md#312r-自动l共同轨迹与连续评价k111)为实现／复跑入口。

**验证与审查：** [最终预检02](research/chapter3_experiments/results/idle_policy_precheck02/checks.json)67/67、6.141秒，包含27项新检查、32项受影响旧单测及8项完整性核对；每轮三次真实小域区间传播、两次传播前到期、一次mock汇总及一次手写功率表ODE交叉核，零MILP构模、零MATLAB、零研究方法调用。26项依赖源码／输入与快照绑定、旧24份档案不变。[独立审查](research/chapter3_experiments/results/idle_policy_precheck02/independent_review.md)通过，属于本线程内部审查，非主线⑥跨会话结论。首轮01为66/66通过；审查补强了复跑时的旧源码基准，将动态HEAD固定为修改前`e086ef4`，只改测试／记录入口后形成02，未修改控制或数值实现，不是研究补跑。

**完成边界与下一项：** 当前只完成共同评价基础层，不报告新模型节能或MILP改进。尚未适配的MILP构模／lift／x0、旧场景适配、方法下界及HEFT／SA入口显式拒收新策略，防止混用hold表达。下一小目标接自动L的MILP控制／物理补全与仅部分固定部署构模、候选合并，先做必要小域核查，再接统一预算与反馈生命周期；实际研究调用及总预算仍未确定，不重启旧115项、Q1或K.108，不新建Goal。分解质量目标仍是预算内更低的完整安全能耗，不能以构模缩小替代。

**K.110／D134：首版自动L规则已确认，仅共享部署接口完成纸面定稿（E555）。** 用户针对上一答方案回复“可以”，强调先定模型再公平比较、分解必须面向预算内更低安全能耗。本轮确认：保留CPU共享域及GPU／NPU各自控制域，真正整域空闲且同刻无新Stage时立即L，全部OPP转换额外时间／能量为0；这是公开抽象而非硬件实测。半开区间先处理真实结束，再合并继续／新启；忙域同OPP可新启，全结束同刻新M直接M，非整数结束不等下一5 ms格点。入口及无工作域按t=0规则取L，温度连续，L基准／漏电、四节点耦合与公共功率口径保留。新规则还未写入程序／config_v01，旧输入和历史结果保持。

**接口与质量目标：** 规则及接口唯一入口为[原计划K.110](research/第三章当前进展与正式实验推进计划_审查稿.md)。共享集合H从原完整输入按跨场景出现关系识别，外层只固定H的具体单元；当前A的16种名义组合，B／C及场景内频率／时序仍自由，场景内多请求部署一致性保留。固定H后，场景独立入口与可加目标使新自动L策略下仍可分。区分外层固定条件与内层求得部署，绑定规则／原输入／候选／精度／源码和同一时钟；全部场景含零权重场景匹配SAFE后才加权一次提交U，局部违规／未决不排整个部署。收益分列初始化、同共享条件的内层MILP和换共享部署后的全局更新，严格比较完整能量区间，不以规模或构模时间替代质量验收。

**本阶段完成与下一项：** 6类纸面情形及源码接口差异已核，非自动测试或性能结果；无程序／配置／正文变更、构模、热评价或求解。下一步进入K.109第2步：最小新控制轨迹／共同评价、部分固定部署构模与候选合并，再接统一预算及候选／反馈生命周期，补必要可复跑预检。外层排序／配额、研究调用数和总预算仍未擅定；同一新策略应用到整体MILP、分解方法和HEFT／SA后才能比较。新模型SAFE与相关下界须重新核，原115项、Q1、K.108不重跑／覆盖；不创建新Goal或继承D132夜间自动范围。

**K.109／D133：下一阶段转向共享部署结构下的预算内安全能耗优化（E554）。** 用户认可仅固定跨场景共享Stage的分解方向，要求研究重点从“完整MILP能否构建／求解”转向“合理预算内找到更低能耗的安全方案”。已审查最新`db2fbe4`，纠正此前固定全部部署的外层建议：当前AB／AC仅A的三个Stage跨场景出现，外层为A的16种名义具体单元组合，B／C的各12种映射留在各自场景内；16不是全部可行或最优证明。具体计划与首版空闲控制规则草案统一维护于[原计划K.109](research/第三章当前进展与正式实验推进计划_审查稿.md)。

**K.109形成时的待定事项（已由K.110承接）：** 用户倾向保留CPU共享域、全域空闲自动L，允许规则确认与分解结构分析并行。该时立即／延迟和开销尚未确认；本段记录历史状态，不在K.110之后继续要求重复选择。研究调用及预算仍待后续明确，原115项、Q1、K.108及旧源码／输入／结果保持。

**五步顺序：** ①空闲规则短说明与仅共享部署分解接口并行定稿；②统一控制／计量及部分固定部署的最小实现和必要预检；③事先声明一次原完整链诊断范围与统一预算，核真实后续改善；④同模型同预算比较整体MILP、分解方法、HEFT／SA，并分别核热约束与反馈作用；⑤收敛第三章方法和实验结论。前两项的具体编程、后续调用数／预算及正式清单待各阶段落实，不借本计划自动重跑115项。研发结果分列初始化、内层MILP及外层换部署后的全局U更新；热反馈不以次数多或必须胜出验收。按需热能耗块、局部修复及每核独立DVFS保留为后备，不同步实施。

**K.108／D132：夜间有界阶段完成，前置过滤降低表达与准备成本，尚无后续节能（E553）。** 用户回复“可以，那你开始吧”后，按[冻结协议](research/chapter3_experiments/prefilter_diagnostic_protocol.md)完成必要预检57/57及一次合并审查修订，再执行三个原R1条件×current／prefilter，各一次／300秒，6/6技术验收通过。原八项核心、配置、完整三Stage合法安排及连续热标准保持；77项源码／规则运行前后及快照匹配，旧24份档案未改。见[结果与图表](research/chapter3_formal_analysis/prefilter_diagnostic01/summary.md)、[运行独立审查](research/chapter3_experiments/results/prefilter_diagnostic01/independent_review.md)。首轮56/57及开发失败记录保留，没有补跑、扩时或增加条件；独立审查为本线程内部审查，不冒称主线⑥跨会话审查。

**主要结果：** base／initial_78的变量91844→29599、总行614943→200205；response_R变量59084→20378、总行382003→134868。三组构模时间依次29.578→19.188、26.562→19.922、19.156→12.437秒；首SAFE依次46.594→28.063、34.188→28.547、27.750→21.157秒。三对最终U分别相同，约1.632465／1.823226／1.632465 J，全部仍等于各自种子，0次严格改善、0条反馈。仅response_R过滤版在288.891秒形成后续MILP SAFE，候选和能量均等种子；287.500秒收到rootlp回调，287.797秒heuristics报告内部界约0.780766 J，预算内节点0，非独立证书。前五次无后续SAFE；第六次没有原生最终回执，保留预算内SAFE及20.282秒进程清理记录。方法停止elapsed合计1800.080秒，其中0.080秒为合作式截止处理；六进程合计1871.750秒，导入、清理与归档单列，未补记预算外新U。

**归因与完成边界：** 只读原15题／45份SAFE记录，MILP种子的全窗基准、活动及温度修正项均高于HEFT和SA代表；base R1基准项差占与HEFT总差约73.5%，并非单一尾段OPP的因果收益。两版本轮均为conditional反馈，不是反馈消融；模型缩小及首SAFE提前只支持本组三对的工程改善，不支持普遍加速、后续能量优势或反馈有效。本阶段到此结束，原115项、Q1和历史无收益结果保持。下一项建议回到K.95—96已接通的固定部署／场景分解，先界定外层部署搜索与内层评价的工作量和保证范围，再由用户审阅确定；本轮不实现、不运行。

**K.107／D131：已审查d597c0c意见，建议优先改进完整链MILP，再补热反馈价值证据（E552）。** 计划集中追加于[原审查稿K.107](research/第三章当前进展与正式实验推进计划_审查稿.md)。原15次MILP均进入求解器，但已存15组callback／13份终回执分支节点计数均0；预算内4次后续SAFE均等种子。HEFT／SA同题已有更低安全U，原合法域存在改善空间，但不保证MILP预算内一定取得。下一小目标建议复用K.95已实现、正式默认关闭的期限前置过滤／事件重建，配合一次已有能耗归因，核小域后另定一次完整链诊断；不同时加入HEFT初始化、外层分解或扩大预算。K.94静态6422→1681选项、480330→156870主要条件行仅为规模依据，不预报加速。当前为提案，无新程序改动、构模、热评价或求解。

**热证据分工与取舍：** 采纳意见P1及P2C优先，P3作为档案辅助展示，P2A／B与K.95—96分解作后备；P4需后续单独声明最少条件及预算。已有26冷热同候选配对足证热约束改变接纳；当前模型已内建事件温限和热能耗，外部反馈补内部峰等剩余违规，0反馈不证明有益或无用，也不能直接归因于内建约束强。旧78号有旧模型条件性收益，不能升级为当前模型证据。追求多数案例竞争力、热约束取舍和反馈计算价值分别验收，不以任何一项预设胜出替代实际结果。原115项、参数和热标准保留；本轮结束于目标与路线建议，具体实现／运行协议待下一项。

**K.106／D130：MILP数值状态异常已完成工程修正（E551）。** 见[诊断与修复](research/chapter3_experiments/results/infeasible_audit01/summary.md)。同一原逻辑选择、原物理矩阵和容差的零目标子问题，`LPPreprocess=basic`于2.359秒报告无解，`none`于26.066秒返回原x0本身；独立原行／界复核通过原数值接纳标准。今后两版MILP显式采用LP none，Integer none及其余设置保持，并补存隐藏LP选项。当前数值接纳x0与内部无解仍冲突时，保留原始回执及既有SAFE/U，标数值一致性未决，不排除或自动重试。[公共预检115/115](research/chapter3_experiments/results/infeasible_audit01/final_common_precheck/checks.json)、[原生接口13/13](research/chapter3_experiments/results/infeasible_audit01/native_interface_precheck/checks.json)通过，绑定71项当前源码／规则。

**修复范围与下一步：** 原完整自由调度矩阵关闭LP预处理的隔离诊断仍超时、无候选，返回跨外部300秒界，不补作预算内结果；固定子问题通过不证明完整模型性能改善或精确数学可行。三次原矩阵诊断及唯一两变量接口检查均留存，无正式方法补跑、新热评价或新研究U。原115项档案及统计不改，旧源码快照／批准保留。[独立审查](research/chapter3_experiments/results/infeasible_audit01/independent_review.md)另存，非主线⑥跨会话审查。下一项回到第三章现有结果与可写结论整理，不继续增加数值诊断、自动重跑或调参；未来比较须使用匹配新源码的凭据。下方K.105“异常待核”为修复前历史。

**K.105／D129：110项续行完成，原115项均已调用，114项技术通过且有SAFE（E550）。** 用户“继续”接受仅执行原未启动110项、各300秒；原5项不重跑，SA103仍为技术失败且仅保留审计SAFE。续行[115/115预检及独立审查](research/chapter3_experiments/results/formal_continuation_precheck01/independent_review.md)、[新批准](research/chapter3_experiments/results/formal_protocol02/approval_record.json)绑定70项源码与manifest `ab212b5038fa3ff5086cfe48d58eb7d97ffdb73a5ffce3bd3b1328e2a31cdc31`，新110项全部退出0、技术通过，无重试、补跑或扩时。源码前后相同、旧24份档案哈希不变；首3项只验续行入口，不把原8项技术验收的7/8改成全通过。[只读合并结果及逐题详表](research/chapter3_formal_analysis/results02/summary.md)保留两批来源与源码指纹。

**首批结果：** 15题均有MILP、HEFT及SA安全输出；正式SA为74/75次，base R1仅4/5成功种子。SA成功种子能量中位数在14/15题低于HEFT，`initial_78__R4`为反例（SA 1.003226 J，HEFT 0.969888 J）。MILP15次及完整赋值反馈消融10次都未严格改善初始SAFE，全部0条反馈；不能称MILP优化或连续反馈节能已获验证。已有HEFT记录中找到26个同一完整候选、35个严格超温点：除入口温度外输入相同，50°C全窗SAFE而78°C违规，支持热约束参与筛查。该证据不要求新压力实验，也不等于最优配置变化或反馈收益。[运行终审](research/chapter3_experiments/results/formal_comparison02/independent_review.md)及[分析终审](research/chapter3_formal_analysis/results02/independent_review.md)已保存，后处理44/44合成检查通过；均非主线⑥跨会话审查。

**异常与完成边界：** `response_R__R2`的MILP于233.047秒报告无解，但独立SAFE种子U=1.626668 J仍保留；无严格改善截断／反馈行，请求x0与原生初始点相同且通过数值接纳。这是表示／数值一致性待核，不是普通超时或模型无解证明。全部正式U与L0未闭合，0独立最优／无解。当前完成的是原首批15个完整三Stage问题，不是五组实验全部完成；Q1、物理参数、工作负载与安全标准保持，未追加案例。下一项建议只核这条内部无解与已保存初始点的关系，再收拢第三章可写结论；不自动增加算法组件、热条件或预算。下方K.104及更早“待批／未启动”为历史。

**K.104／D128：正式批次在第5次归档故障后按约停止，4次技术通过，110次未启动（E549）。** 用户已确认115次／各300秒，实际批准及一次消费记录均保存。首例`base__R1`的MILP、HEFT、SA101／102通过：U分别约1.632465、0.985107、0.869718／0.873164 J。MILP仅保留初始构造见证，无后续MILP安全候选或热反馈；SA五种子未齐、首8次技术验收未完成，不形成15问题总体比较。[完整状态与汇总](research/chapter3_formal_analysis/results01/summary.md)、[独立运行审查](research/chapter3_experiments/results/formal_comparison01/independent_review.md)已保存，非主线⑥跨会话审查。

**停止原因与修正：** SA103已完成搜索并将SAFE结果完整保存；随后worker补写身份标签时，`Path.write_text`打开同一`result.json`发生`OSError: [Errno 22] Invalid argument`，退出1触发控制器停止。原24 MB JSON可完整解析，SAFE于281.391秒形成、U约0.871736 J，按审计证据保留，**不补认技术完成或计入正式SA统计**。隔离字节写入未复现，具体系统原因未定。仅将driver归档改为临时文件写完再原子替换，失败保留旧证据／pending文件；未改算法、参数或安全标准。[修正后98/98预检](research/chapter3_experiments/results/formal_precheck02/checks.json)通过，与原运行快照分开。旧结果、退出码及调用均未改，无研究补跑／自动续跑。

**K.104结束时的历史提案（已由上方D129接受并执行）：** [110项清单](research/chapter3_experiments/results/formal_comparison01/remaining_scope_proposal.json)保留原顺序／原300秒，各次合计最多33000秒＝9小时10分；原5项包括103不重跑。原批准不重置，后续另立续行入口与批准。本段的未授权状态不代表当前状态。

**K.103／D127：完整链首批比较方法已实现，96项必要预检通过，具体批量预算待确认（E548）。** 新增共享部署HEFT、SA、两版MILP共同包装及[正式协议](research/chapter3_experiments/formal_comparison_protocol.md)，复用原资源／期限检查与完整连续热能耗评价。HEFT继承向上排序／最早完成插入，适配跨场景部署、工作点及一轮节能调整；SA搜索部署、频点、优先级和等待，其退火参数是对照前自设算法常数。反馈消融只将条件温限反馈换为可靠违规场景的完整赋值删除，原种子／x0、主模型、四项强化与统一时钟保持。

**已核范围：** [预检96/96](research/chapter3_experiments/results/formal_precheck01/checks.json)包含91个静态／模拟测试、两次既有单Stage夹具实际连续评价及其SAFE接纳、源码一致性；未运行原基准、Q1、MATLAB或正式研究对照。一次授权消费、15项派生输入身份、晚SAFE拒收、已有见证保留和SA到期状态已核。[内部独立审查](research/chapter3_experiments/results/formal_precheck01/independent_review.md)另存，非主线⑥跨会话审查；历史原生小域及Q1仅支持未改桥接，不冒充本次全流程性能验证。

**下一项仅待批量范围／预算确认：** [已生成清单](research/chapter3_experiments/results/formal_protocol01/proposed_manifest.json)为原`base`、`initial_78`、`response_R`各R1—R5，15个完整三Stage问题；MILP／HEFT各一次、SA固定五种子、10次反馈消融，共115次，建议各300秒、方法上限9小时35分。已集中询问，尚未取得该具体清单的确认；示例批准文件为`approved=false`，不能运行。首例8次只验技术正确，出错停止，无收益可继续；不补跑、不延长。主线⑥新Stage／DAG建议接受为后续备选，不自动纳入本批。Q1已结束，不重跑。当前`comparison_implementation_prechecked=true`、`batch_authorized=false`、`formal_experiments_ready=false`。下方K.102等为历史状态。

**K.102／D126：Q1质量参照已完成，两方法得到相同安全能量，独立遍历完成（E547）。** 依用户阶段授权采用{0,45} ms、两独立调用各一次／各300秒；完整三Stage主实验及物理／安全参数不变。整体MILP74.985秒工程级收敛，初始U=1.284120126709441 J，后续U=0.845572004073791 J，改善来源为MILP候选；独立遍历106.937秒覆盖11520／11520项（4374非法、7146完整SAFE），同一最佳安排／U，有限域最优包络宽约1.35646×10⁻²⁹ J，无未决。两者均未记独立精确最优，0热反馈／0热排除，不将本例归为热反馈收益。[结果与解释](research/chapter3_experiments/README.md#312l-q1小规模优化质量参照完成)、[汇总](research/chapter3_experiments/results/q1_quality01/summary.json)及[独立终审](research/chapter3_experiments/results/q1_quality01/independent_review.md)已保存。

**实现与阶段结束：** 显式起点共同接口及独立遍历落实，[54/54必要预检](research/chapter3_experiments/results/q1_precheck01/checks.json)通过，内部独立复跑28项及结果终审无阻断（非主线⑥跨会话审查）。两输入SHA相同、56项源码／规则前后匹配；两保存见证事后复核SAFE，成本单列，不补预算内U。仅本次种子改善约34.15%，不是对其他方法的节能率；完整链、连续启动域及热反馈收益仍不由Q1证明。Q1停止，无补跑／扩时；下一项回到第三章正式实验的首批方法实现和共同比较规则，不再追加质量诊断。正式批量实验尚未启动，`formal_experiments_ready=false`。下方K.101等为历史状态。

**K.101：Q1运行与必要预检协议已形成，等待起点／预算冻结（D125／E546）。** 见[执行协议](research/chapter3_experiments/q1_quality_protocol.md)。整体MILP沿K.92四项表达及首解／x0／连续反馈；独立遍历覆盖完整联合赋值，单次内惰性复用局部结果，更新U前全场景复核，未完保留L0／U及未决域。已定位`expand_options`、共同合法性与首解未统一支持显式起点的缺口，拟新增实例`start_domain`，默认完整链行为保持，不用fixture标签绕过。新协议只补六组必要检查，不预跑Q1热库或重复旧原生夹具。{0,45} ms及各一次／各300秒（合计10分钟）已集中询问，待回复；只确认本项预算，不自动冻结主实验预算。当前仅协议／源码静态核查及内部复核，无代码、输入或实验改动，`formal_experiments_ready=false`。

**Q1范围已确认（D124／E545）：** 用户接受main子工作负载，**仅用于第三章小规模优化质量参照；正式主实验仍用完整三Stage链**。AB／AC共享A.main的具体单元等Q1关系继续沿[计划§4.1.1](research/第三章当前进展与正式实验推进计划_审查稿.md)整理；此前{0,45} ms及原参数提案保留，执行协议／预算仍待冻结，不凭本次范围确认启动实现或实验。下一项可整理Q1运行与必要预检协议，沿“一次MILP＋一次有限遍历”的有界安排推进，不扩充案例或改主工作负载。本轮仅同步选择，`formal_experiments_ready=false`。

**K.100历史提案：小型质量参照具体化为Q1（D123／E544；范围后由D124确认）。** 见[同一计划§4.1.1](research/第三章当前进展与正式实验推进计划_审查稿.md)。建议只为质量参照抽取AB／AC的main，保留A具体单元共享、全部合法CPU标签／GPU／NPU与H／M／L、四节点及400 ms完整能耗。起点{0,45} ms由原最快H参考时长30／35／45推导，沿用50°C入口／80°C温限及原期限123.5／157.3／143 ms；删除前后处理后只是继承预算，不验证完整请求链。完整链主实验不变。只读有理数核得筛前46656完整赋值／864不同场景安排，单项期限过滤后11520／384，尚非合法数／热评价数／性能结论。K.100交付时尚待选择，后续确认见上方D124；预算未确定。配置／程序／原结果未改，未构模、枚举完整安排、仿真或求解。

**K.99：K.98计划已按外部意见修订v2，采用有边界的证据补强（D122／E543）。** 仍维护[同一计划](research/第三章当前进展与正式实验推进计划_审查稿.md)，不新建长报告。提前纳入一个保留共享部署／竞争／完整热能耗的小型质量参照，最多MILP和独立有限遍历各一次；热证据分开约束作用与反馈作用，必要时仅`base__R1`最多两个新条件、两版MILP各一次，共四次。沿待审统一T，建议300秒时额外最多30分钟；基础115＋补充6次上限121次／10小时5分，具体小域限制、压力数值、方法细则及预算均未冻结。复用已有种子归因和能耗组成，补正式展示与尾段汇总；首个配对只验技术正确，不要求方法获胜或已证最优。原模型／源码／参数及结果未改，本轮无运行，`formal_experiments_ready=false`。

**K.98：当前进展与第三章正式实验推进计划已提交审查（D121／E542）。** 见[审查稿](research/第三章当前进展与正式实验推进计划_审查稿.md)。核清整体MILP／首解／评价器已实现，固定部署场景入口只完成内层，HEFT／SA及外层部署搜索未实现，正式比较未运行。建议暂缓可选K.97诊断，先按已确认五组收拢首批；提案为`base`／`initial_78`／`response_R`各R1—R5、三个主方法及反馈消融，共115次，300秒／次与SA五种子等均待用户审查，不是已冻结运行。所有模型、参数、程序和历史结果保持；本轮只写计划，不启动实现／构模／实验，`formal_experiments_ready=false`。

**推进约定更新（D120／E541）：当前验证已足以开始收拢第三章正式实验安排。** 用户同意由助手判断诊断的合适停止点。K.95—96已核固定部署后的场景表达、连续评价／反馈和统一计时的必要小域正确性，外层共享部署搜索尚未实现；下一步可整理最小实验组、比较方法及统一预算。K.97原规模固定部署诊断是可选的可实施性补充，不再作为开始实验安排的必过门槛；其部署／预算仍待确认，不据本条启动。若执行，只按确认范围诊断一次，结束后回到实验安排，不以原规模最优、超过种子或算法占优为结束条件。具体正确性、安全接纳或计费错误须修复并核受影响检查；性能不理想则按局限保留，不自动追加组件或预算。**开始安排不等于正式运行就绪**，方法适配、输入／预算冻结及执行前必要检查仍需完成，`formal_experiments_ready=false`。

**K.97：固定部署原规模诊断方案已整理，部署与预算待确认（D119／E540）。** 见[短协议](research/chapter3_experiments/fixed_scene_diagnostic_protocol.md)。建议只借用K.92历史SAFE的具体单元：A／B为CPU2→NPU0→CPU1，C为CPU1→GPU0→CPU1；全部相容工作点／5 ms起点重新求解，不输入旧时间表、U或x0。原`base__R1`、400 ms、权重及物理／安全标准保持。这是给定部署的条件子问题，不能与原整体搜索直接比较加速。

**待确认及执行边界：** 助手建议一次300秒完整总预算，900秒为备选，均未获本轮具体确认、未启动运行。已有顺序入口先AB后AC、每轮只核最终返回候选，AB可能占满预算；不为避免该结果临时加切片或组件。用户选择后，只补薄入口的必要模拟／哈希门槛再按确认限额诊断一次。当前只读核材料和源码、写方案及内部独立审查，没有构模、测试、MATLAB／求解或正式对照，`formal_experiments_ready=false`。

**K.96：固定部署单场景的MATLAB小域端到端已接通（D118／E539）。** 见[README §3.12k](research/chapter3_experiments/README.md#312k-固定部署的matlab小域端到端接通)。新增`scene_method`复用原单场景模型视图求解／连续温限反馈，SAFE后再核原完整输入；全部匹配场景SAFE才汇总U。一个MethodBudget覆盖读取、所有构模、一次新MATLAB启动、全部轮次、两种评价及汇总；原入口／核心模型／物理参数未改。没有初始解或外层部署搜索。

**实际进展：** [接口／预算预检02](research/chapter3_experiments/results/scene_method_precheck02/summary.json)37/37及[原生小域核查](research/chapter3_experiments/results/scene_method_native01/summary.json)28/28通过，内部独立终审无阻断。按[预声明](research/chapter3_experiments/scene_method_protocol.md)三次各180秒调用、共7请求，无x0／候选或热缓存共享。双场景SAFE，75.813 s（启动64 s）；真正重分段链式SAFE，17.204 s；解析内部峰16.281 s、3条温限反馈后第4轮solver-reported无解，U为空、独立无解false。未运行研究原规模或正式对照。首次时间仅针对已复核返回候选，不是callback首个整数解；内部界不升级，实际未触发完整赋值删除。清理及事后见证复核单列。

**下一小目标建议：** 讨论一次固定部署的原规模可实施性诊断，先明确部署来源和总预算，核结构缩减能否产生可用输出；不自动运行、不扩大预算，也不先选外层算法。小域接通不证明加速、额外节能或最优，K.92历史结论保持，`formal_experiments_ready=false`。

**K.95：固定部署单场景构模与未加权评价接口已实现，小域门槛通过（D117／E538）。** 见[README §3.12j](research/chapter3_experiments/README.md#312j-固定部署的单场景构模与未加权评价)。`build_model`增加默认关闭的期限前置过滤、完整固定部署及单场景视图选项；保留全部相容工作点／起点，重建事件、物理包络及下界，未用域显式保持入口档但保留四节点／基准／漏电／耦合。新`scene_adapter`显式核完整外层部署、返回未加权连续热能耗回执；全部场景匹配SAFE且在同一截止内，才按原权重汇总U。原默认整体表达及生产评价器保持。

**已核结果：** [完整预检02](research/chapter3_experiments/results/scene_precheck02/summary.json)227/227、[旧结构回归02](research/chapter3_experiments/results/scene_legacy_structural02/checks.json)44/44通过并匹配当前源码。六夹具456条赋值、213条合法安排及30种部署枚举，固定完整域与单场景乘积投影一致；真正重分段夹具事件24→12，两条合法时间表通过原1e-9 Python行／界门槛及连续包络交叉核查，新能量下界证书重核。双场景未加权汇总与原共同评价能量区间完全相同。01是补齐覆盖前的开发记录，02为本阶段完整门槛。参数配置SHA保持`615be096…9a4fe`；没有原规模构模、MATLAB／MILP求解或性能比较。

**下一小目标建议：** 接入固定部署单场景的MATLAB候选求解、原连续反馈与统一计时，先做小域端到端核查。当前只完成Python构模／矩阵残差与完整评价接口，尚无新表达的求解器实际接纳、加速或能量改善证据；外层部署搜索、精确LBBD、原规模运行预算及正式对照仍未确定。K.92历史结果保持，`formal_experiments_ready=false`。

**K.94：固定部署结构核查完成，可缩表达但尚未验证加速（D116／E537）。** 见[静态核查](research/chapter3_experiments/fixed_deployment_structure_audit.md)。固定完整共享部署后，独立入口场景可分；零权重场景仍须可行。单元不相容及期限必零选项可前置过滤，再由全部保留起止点重建事件；无工作域保持入口档，但保留基准、漏电及全部热节点。精确调度与RC语义可保留，新分段的数值包络／变量盒／M／下界须重核，不能称原外包矩阵逐行等价。

**静态规模与归因：** 只读原`base__R1`冻结输入，以历史首解的具体单元作为尺寸示例，保留所有相容H／M／L和起点。原／仅期限／仅部署／两者合用分别有6422／1681／2746／846选项，1779／581／1708／565片段，480330／156870／320760／103950条条件热能耗行。最终相对原少78.36%，相对仅期限前置过滤少33.74%，不能都归给分解。A＋B联合状态27→9，A＋C仍27且事件不减；不是全部部署的尺寸结论。精确集合双算、档案复现及内部独立复核一致，见[JSON](research/chapter3_experiments/results/fixed_deployment_audit01/static_counts.json)。只新增静态计数与核查材料，未改生产源码、参数、正文或运行仿真／构模／求解。

**下一小目标建议：** 实现固定部署的单场景构模／未加权评价适配，先做小域语义及数值接纳核查。期限前置过滤作为整体和固定部署表达的共用前处理；全部场景SAFE后按原权重汇总U，违规与未决分别保留。尚未实现此接口，不确定外层算法、精确LBBD或新原规模预算，不运行正式对照。K.92历史结果保持，`formal_experiments_ready=false`。

**K.93：已复核最新分解路线意见，建议下一项优先核固定部署后的表达缩减（E536）。** 对照提交`c423919`、共同模型接口及源码，采纳“保留整体MILP参照＋先核场景分解结构”的建议。当前跨场景只由共享部署链接，入口独立、时序与热状态均按场景建立，固定完整部署后可以分别规划；场景内四节点热耦合及频率域仍保留。只固定变量不会自动删除选项、事件或联合工作点状态，不能据此预告加速。

**推荐调整：** 下一项先静态核查“按固定部署过滤必不相容选项后，事件、可达工作点状态及热能耗行究竟能缩到什么程度”，区分减少CPU标签与减少物理表达；不再优先讨论延长整体MILP预算。完全未用域可保持入口工作点并缩控制状态，仍计基准／漏电、保留热节点。重建事件后的等价性应对照真实调度与RC问题，重新核数值包络，不预设与原外包矩阵逐行相同。现评价总接口要求全部场景且权重和为1，分解时需适配单场景未加权回执，再由外层按原权重汇总，不能直接删去其他场景后沿用原总接口。交付范围只含条件论证、代码接口及静态规模依据，不证明运行加速。

本轮只完成意见与源码复核，未改正文／程序／参数或运行实验；K.92实际进展保持。小域研究参照应保留关联场景和共享部署，具体范围、正式预算、第四章算法及精确LBBD仍未确定。上述为助手建议，不作为用户已选算法或新运行授权。

**当前阶段K.92：首解辅助完整900秒诊断完成，原规模已观察到种子成为求解器可行解，能量未进一步改善（D115／E535）。** 原`base__R1`、400 ms／5 ms、四项表达开关、91844变量／614943行／6422选项及物理／安全参数保持。初始方案在本调用重造并计费，59.938 s取得连续SAFE，66.266 s完成数值起点；73.250 s收到求解入口，290.328 s收到与种子模式／起点完全相同的整数候选，292.297 s独立复核SAFE。初始U、MILP已复核U均约1.632464816557 J，最终来源仍为`initial_constructor`；两项改善标记均false。见[摘要](research/chapter3_experiments/results/base_warm_diagnostic01/diagnostic_summary.json)及[README §3.12i](research/chapter3_experiments/README.md#312i-首解辅助的完整900秒诊断)。

**运行与核对：** 当前核心109/109、新入口24/24含实际小域接入通过，复用匹配源码的19／29／9／82凭据；原规模只读81/81及内部独立终审通过，非主线⑥跨会话审查。21项依赖源码运行前后相同，输入快照与K.88逐字节一致，只有一次请求，无热反馈。根LP在289.406 s报告0.740331756 J；408.860 s内部下界0.740333147 J，仍为solver-reported。900.031 s返回，31 ms是中断处理；清理13.407 s、结果归档0.234 s、源码归档0.031 s单列，不补预算外候选。迟到原生exitflag2／可行点1／节点0只作归档，未生成新U或最优证明。

**阶段判断与下一小目标：** 原规模首解构造、数值接纳和实际求解器回传已接通，可以结束首解接入诊断。预算内安全输出来自构造器，尚无后续优化收益、独立最优或加速证据。下一项建议集中确定工程级MILP参照的正式比较口径与预算，以及需要独立最优参考的小域范围；不自动补900秒、继续堆强化、改输入或开启正式对照。`formal_experiments_ready=false`。

**主线6分解路线审查交接（2026-10-17，用户要求提交供主线⑦参考）：** 见[多场景共享部署分解路线审查意见](research/多场景共享部署分解路线_主线6审查意见.md)。认可保留整体MILP参照并核查固定部署后的场景分解；建议先静态澄清选项、事件及状态能否在保留全部相容安排时缩减，复用现有完整评价。小域参照须保留研究核心；固定变量不自动缩小表达；外包模型收敛不等于真实RC能耗最优。第四章具体算法、精确LBBD及新运行预算均未由此次归档确认，未改模型／代码／参数或运行实验，K.92实际进展保持。

下方K.91及更早内容为历史，以本段K.92为当前状态。

**当前阶段K.91：原基准已取得安全见证及数值接纳通过的完整初始向量（D114／E534）。** 一次180秒上限的首解诊断，原`base__R1`输入快照与K.88逐字节一致，四项表达开关、91844变量／614943行／6422选项保持。首个H档模板即取得完整合法安排；52.531 s形成原连续评价器的SAFE回执，完整窗口加权安全能量上界约1.632464816557 J；60.000 s完成91844维向量的Python全行数值接纳，最大不等式残差2.13e-14，其余残差0，未舍入或放宽容差。见[结果](research/chapter3_experiments/results/base_initial_witness01/result.json)及[README §3.12h](research/chapter3_experiments/README.md#312h-原基准安全见证与完整初始向量的有限诊断)。

**凭据与边界：** 新入口36/36及归档只读39/39通过，复用源码匹配的109／19／29／9／82项凭据，16项源码运行前后及快照一致。内部只读独立终审通过，非主线⑥跨会话审查。本次没有启动MATLAB或调用`intlinprog`，原规模实际接纳为`NOT_TESTED`；安全方案来自本次构造器，不是MILP优化结果，不证明最优或加速。声明上限180秒、实际60秒，不升级为正式60秒方法已通过。已有SAFE和后续向量状态分别保存；本轮一次调用，无补跑、扩时或正式对照。

**已回答与下一小目标：** 原模型中存在满足期限和连续热安全的完整安排，且简单首解规则能形成全变量数值起点；此前900秒无候选不能解释为原问题无解。下一项建议在先声明的完整方法预算内接入该构造器、核MATLAB实际接纳及后续优化，构造／连续复核／补全全部重新计费，初始安全U和MILP后续改善分列，不免费注入本次历史向量。新优化调用及预算尚未确定，`formal_experiments_ready=false`。

下方K.90及更早内容为历史，以本段K.91为当前状态。

**当前阶段K.90：首个安全见证与可选MILP初始解已在小域接通（D113／E533）。** 新增有界、确定性的共同部署与完整安排构造器，最多尝试三档工作点模板；完整候选先经原连续热能耗评价取得SAFE，再补全全变量向量、检查解码往返及原容差的矩阵残差，首轮通过可选`x0`提交MATLAB。模板只限制种子构造，主MILP的全部合法映射、逐忙段调频及起点保持。无初始解路径仍为默认，原输入、数学构造、物理参数与安全标准未改。见[协议](research/chapter3_experiments/initial_point_protocol.md)及[README §3.12g](research/chapter3_experiments/README.md#312g-初始安全见证与可选初始解的小域接入)。

**完成结果：** 首解流程109/109、桥接19/19、统一计时29/29、预算边界9/9、原MILP回归82/82通过。五个既有夹具均在首模板取得SAFE与可接纳向量；438条独立小域完整赋值／209条合法安排用于核对，未供构造器或求解器读取。实际单Stage调用接收108维`x0`，初始安全U为1.049679 J，MILP后续安全U为0.722711 J；首个初始SAFE在10.859 s形成，方法17.422 s完成，清理3.140 s单列，均按事先声明的180秒小域预算处理。此结果证明接入流程可运行，不证明初始解加速或原规模收益。

**异常保留与停止：** 首轮桥接原生检查在60秒内未完成MATLAB启动；无初始解计时模拟曾因新增可选参数失配，恢复旧默认调用后通过；另一次预算预检因沙箱临时目录权限错误中止，正常环境重做通过。原失败记录均保留。已有SAFE在补全拒收、预算中断或求解器异常后保留；未知／违规不提交，失败不排除原域。本轮原基准零构模、零求解，无新增900秒调用或正式对照，`formal_experiments_ready=false`。

**下一小目标建议：原基准的有限安全见证构造与初始向量接纳诊断。** 先确定一次调用的总预算及源码凭据，再核这套简单规则能否在原规模取得SAFE并形成可接纳`x0`；不以优化收敛为本项门槛。当前原900秒入口尚未自动接入首解流程。若构造／补全失败，保留具体原因后讨论，不默认扩时、缩域或修改功热模型。该原规模诊断尚未执行。

下方K.89及更早内容为历史，以本段K.90为当前状态。

**当前阶段K.88：能量下界强化后的单次900秒诊断完成，LP改善但仍无首解（D112／E531）。** 本次显式开启能量下界强化及辅助连续化，保留期限必零、单位级频点聚合，原`base__R1`、400 ms／5 ms及物理／热安全参数保持。新增1779行，模型91844变量、6422整数声明、614943行、7835918非零元；保存矩阵的全部原A／b前缀及目标、边界、intcon与K.86相同。见[结果](research/chapter3_experiments/results/base_long_diagnostic04/diagnostic_summary.json)及[README §3.12f](research/chapter3_experiments/README.md#312f-能量下界强化后的单次900秒诊断)。

**本次事实：** 构模46.906 s，其中下界生成10.679 s；63.531 s收到求解入口，369.062 s根LP报告目标0.740331756 J（K.86为0），525.968 s割阶段内部界0.740333147 J。900秒内候选、LEGAL、SAFE、连续评价及反馈均0，U与首次合法／SAFE时刻为空；`UNRESOLVED / wall_time_limit`。方法900.062 s返回，62 ms为中断处理，清理16.484 s、归档0.266 s和源码归档0.015 s单列，不接纳预算外消息。

**核对与边界：** 新接入实时预检20/20、辅助数值325/325、计时29/29通过，复用相关源码未变的能量342/MILP82/桥接9项凭据；运行后只读125/125通过，独立内部审查无阻断。原数学构造与K.87提交`5efaebd`一致，只接入显式开关和凭据检查。原规模LP松弛改善已观察到；本次构模、根LP完成时刻增加，尚无首解、求解加速或节能收益证据，也不判无解。正式对照仍未就绪。

**下一小目标建议：先审查整数首解的构造与接入条件。** 复用已有日志和合法域，不默认继续堆下界或增加预算；后续新方法／新运行另行讨论。本阶段只调用原基准一次，无补跑、扩时或正式比较，默认开关仍关闭。`formal_experiments_ready=false`。

**主线6交接建议（2026-10-16，用户要求整理并提交）：** 见[MILP首个安全方案与参照可实施性审查建议](research/MILP首个安全方案与参照可实施性_审查建议.md)。建议下一项先核完整安全见证的构造与接入路线，区分调度合法、连续SAFE及求解器初始向量；不得免费借用其他方法候选、缩小搜索域或把初始方案收益全部归给MILP。保留足够论文实质，不无限追加下界／900秒诊断，也不自动取消温度相关能耗。该交接未修改模型／实现，未运行实验，不新增运行预算或模型选择。

下方K.87及更早内容为历史，当前以K.88为准。

**K.89：已复核主线⑥首解建议，推荐先打通安全见证与初始解接口（E532，2026-10-16）。** 核对最新提交`f7f3e1e`及现有源码，接受其三层区分：完整调度合法、连续SAFE、可供MILP接纳的全变量向量。R2023b支持可行初始点`x0`，当前桥接不导出且MATLAB明确传空；现有`lift_candidate`限定预检，2e-8回归门槛不等于当前1e-9求解设置下已可接纳。SAFE与矩阵接纳分别记录，不能用一方替代另一方。没有新增模型确认、运行预算或实验。

**推荐下一小目标：形成并落实一个范围有限的首解构造与接入协议。** 先固定简单、确定性的共同部署／完整安排构造规则和尝试上限，复用原合法域及连续评价；再核补全、残差、解码往返及`x0`传输，小域通过后才讨论一次原规模见证构造／接纳诊断。候选构造、补全与评价全部计入调用，初始能量与MILP后续改进分列；输入向量不固定后续决策。单纯找到或接纳初始方案不作为MILP优化收益。若简单构造无见证，或补全需发展复杂新求解器，集中讨论，不默认继续堆约束、增加900秒调用或改物理模型。本项为助手建议，执行及预算尚未获用户确认；本轮仅审查与计划。

**当前阶段K.87：热能耗条件行的有效下界已实现，小域核对通过（D111／E530）。** 每个事件片段从原导出条件能量行和变量盒推导共同斜率、状态相关截距，追加一条不带Big-M的能量下界。精确有理数证明及逐状态全盒检查表明：保留原导出MILP的全部整数状态可行点，包括数值外包允许的点；不改变原参数、合法安排、目标、温度递推、旧M或连续热接纳。新开关`strengthen_energy_lower_bounds=False`默认关闭。详见[推导§8](research/chapter3_experiments/milp_structure_audit.md#8由已导出条件行生成能量下界k87d111)和[结果§3.12e](research/chapter3_experiments/README.md#312e-热能耗条件行的能量下界强化)。

**本轮证据：** [强化预检02](research/chapter3_experiments/results/energy_bound_precheck02/checks.json)342/342；五个既有小域438条完整赋值中209条调度合法，物理补全均保留，130份新增行证书覆盖2262个状态。五域solver-reported LP目标均提高，例如非整数时长链式域0→0.649430 J；单Stage四版本均取得相同连续SAFE能量约0.722711 J。原MILP回归82/82、方法计时29/29通过。首次预检303/304因OSError中止，保留原记录；仅修补预检记录的原子发布、有限IO重试及错误堆栈后重做，未改数学构造，最终无IO重试。

**完成边界与下一步：** 本轮只做推导、实现和小域核对，未构造或求解原基准、未补跑900秒或运行正式对照。确认的是整数域保留及这些小域的松弛改善，尚不能判断原规模首解或求解耗时是否改善；浮点LP报告也未提升为独立界证书。下一项可讨论单独启用该强化的同预算原规模诊断，重点记录根LP、首个合法候选和SAFE时间；本轮不自动执行。`formal_experiments_ready=false`。

下方K.86及更早内容为历史，当前以K.87为准。

**当前阶段K.86：辅助整数连续化后的单次900秒诊断完成，仍无首解（D110／E529）。** 保留期限必零和单位级频点聚合，本次显式开启辅助连续化。原91844变量／613164行／7771874非零元不变，整数声明75825→6422；归档对比确认约束矩阵、右端、目标及变量上下界相同，仅`intcon`改变。20.609 s构模，34.344 s收到求解入口回执，165.719 s根LP目标0，279.094 s割后已报告下界0。900秒候选0、安全U为空；首次合法／SAFE时间为空、辅助解码未触发。见[结果](research/chapter3_experiments/results/base_long_diagnostic03/diagnostic_summary.json)及[README §3.12d](research/chapter3_experiments/README.md#312d-辅助整数连续化的数值接纳与单次900秒诊断)。

**核对与边界：** 数值325／表达165／MILP82／计时29／实时19项通过，运行后只读89/89通过。补齐辅助量合法二元范围检查，保留1e-6容差，独立调度与完整热评价保持。900.047 s返回、清理11 s单列，迟到空向量不补认首解。小域MATLAB沙箱启动失败及换行读取导致的测试失败均保留，最终凭据完整；原基准只调用一次，无补跑、扩时或正式对照。

**下一小目标建议：转向热能耗条件行的可靠分段／状态下界强化，先推导与小域核对。** 本次未观察到辅助连续化解决首解，不据此认定其普遍无效或模型无解。原根LP仍0，强化应从已导出外包行出发，不能直接填物理下界或任意缩小M。默认辅助开关仍False，本次True仅为独立诊断；后续正式版本及新运行需讨论，`formal_experiments_ready=false`。

下方K.85及更早内容保留为历史，当前以K.86为准。

**最新优先级复核K.85（E528）：建议下一项受控诊断优先考虑辅助整数连续化。** 开关及等价性核对已具备，适合单项归因；不认定它已是无首解主因。它不改变原始根LP，已有小域节点5→11、调用墙钟0.437→0.719 s，不能承诺加速。热能耗松弛仍弱，后续可沿导出条件行加强分段／状态下界，但下界提高不保证取得首解。详见[结构审查§7](research/chapter3_experiments/milp_structure_audit.md#7k84后两项改进的优先级复核k85)。

**本轮范围：** 仅读既有日志、源码与R2023b官方文档；没有补跑、构模、改参数或热安全标准，辅助连续化仍关闭。建议尚未获用户选择，不新增确认记录或运行授权；保留全部逻辑量的数值解码和独立完整复核。下方K.84是最近一次实际运行，正式实验仍未就绪。

**最近运行K.84：两项调度强化后的单次900秒完整诊断完成，仍无整数候选（D109／E527）。** 原`base__R1`及全部参数保持；期限必零与单位级频点聚合开启，辅助整数连续化关闭。模型25.359 s完成，37.844 s收到求解器入口、154.625 s收到根LP回调、285.328 s收到割平面回调。截止900 s候选0、连续复核0、安全U为空，`UNRESOLVED / wall_time_limit`。见[诊断摘要](research/chapter3_experiments/results/base_long_diagnostic02/diagnostic_summary.json)及[README §3.12c](research/chapter3_experiments/README.md#312c-两项调度强化后的单次900秒完整诊断)。

**本次可确认的变化：** 6422选项仍保留，其中4741上界固定0；91844变量／75825二元声明不变，行数1172563→613164，非零元8331273→7771874。相较K.81，根LP和割平面回调较早，但两次均未在预算内产生首解。单次记录不能支持稳定加速，尚未解决原规模首解问题；不解释为模型无解、热安全失败或主线无效。

**核查与停止：** 实时预检18/18及运行后只读核对59/59通过，K.83的165/82/29项凭据与源码匹配。生产源码本轮未改，原输入、评价标准和求解选项一致。900.031 s方法返回含31 ms中断处理；清理13.797 s、归档0.156 s和源码归档0.016 s单列，不增加证据预算。迟到done回调虽报可行点1，但向量为空、最终output报0，保留为原生计数不一致，不能补认首解；K.81也存在此现象。本阶段结束，无补跑或正式对照；下一次求解、辅助连续化启用与正式预算均须另行讨论。`formal_experiments_ready=false`。

下方K.83及更早内容为历史，当前以K.84为准。

**历史K.83：期限必零与单位级频点聚合已落实，辅助整数连续化独立预检通过（D108／E526）。** 默认启用两项调度强化；辅助连续化保留`relax_auxiliary_integrality=False`独立开关，未自动作为主版本。保留原选项／事件、400 ms尾段、5 ms起点、逐忙段调频及连续热接纳。期限必零在原物理行构造后收紧上界并刷新边界缓存，原热能耗行及误差包络保持；全部逻辑二元量仍按原容差解码。

**可复跑核对：** [分项预检01](research/chapter3_experiments/results/formulation_precheck01/checks.json) **165/165**，六版本对照`e6eb792`，10小域1050条完整赋值／555条数学合法安排；物理行、目标及既有误差记录核对一致。小域实际MATLAB旧版、两项强化版及辅助连续化版取得相同安全能量，全部超期夹具结果一致。[MILP14](research/chapter3_experiments/results/milp_precheck14/checks.json) **82/82**、[方法计时13](research/chapter3_experiments/results/method_precheck13/checks.json) **29/29**。详情见[README §3.12b](research/chapter3_experiments/README.md#312b-调度层强化与辅助整数连续化的分项预检)。

**完成边界：** 研究参数、评价器和求解器选项未改；未重建或求解原基准、未扩大预算、未运行正式对照。本轮证明并核对的是表达及安全接口，未证原规模首解或总耗时收益。能量下界强化尚未实施；下一次原规模调用及预算需另行讨论，不自动补跑。`formal_experiments_ready=false`。

下方K.82及更早内容为历史，当前以K.83为准。

**历史K.82：原MILP松弛与整数结构静态审查完成（D107／E525）。** 仅核K.81已有900秒日志、原矩阵和源码，未补跑、未重新构模或评价，参数及16项生产源码／配置与归档一致。详见[结构审查](research/chapter3_experiments/milp_structure_audit.md)和[静态计数](research/chapter3_experiments/results/structure_audit01/static_audit.json)。

**已证明的改进空间：** 6422个选项中4741个超过原请求期限，可按精确期限固定为零；580712条逐选项工作点锁定可替为21313条单位级汇总行，整数域等价且LP更强；75825个二元声明中69403个辅助量可由整数选项与原逻辑关系强制取整。后者不加强根LP，也不保证更快。条件热能耗行480330条；完整安全安排的物理下界约0.738286 J，已有根LP报告0，能量有效下界仍值得补强，但需区分物理能量与数值外包变量。

**下一小目标建议：先实现调度层等价强化并做小域投影核对。** 分项核原期限必零、按执行单元及频点聚合锁定，再单独核辅助整数连续化；保留原事件集合、物理行、400 ms尾段、5 ms合法起点和全部安全接纳条件。能量下界从已有导出条件行推导，暂不直接把物理下界塞入外包变量。没有重新授权原基准求解或预算；本次900秒诊断中的内部耗时仍未完全分解。正式实验保持未就绪。

用户本轮再次回复的资源／规模选项与D94／D95一致，继续保留同一平台改变可用设备、每请求三Stage固定链增加请求数，不新增研究选择。

下方K.81及更早状态保留为历史，当前以K.82为准。

**历史K.81：一次900秒完整诊断完成，已进入求解但未取得整数候选（D106／E524）。** 原`base__R1`、6422选项、数学表达与参数保持。输入0.015 s、构造25.235 s、独立MATLAB启动11.125 s、矩阵导出6.156 s，44.203 s收到求解器调用入口记录；179.187 s收到根节点LP回调，359.125 s收到割平面回调。截止900 s无整数候选、连续评价0、安全U为空，`UNRESOLVED / wall_time_limit`。详见[诊断摘要](research/chapter3_experiments/results/base_long_diagnostic01/diagnostic_summary.json)及[README §3.12](research/chapter3_experiments/README.md#312-一次900秒完整流程诊断)。

**验证及计时边界：** 实时接口18/18、方法计时29/29、桥接9/9、原MILP回归82/82通过；原数学／评价文件未改，输入与K.80一致，运行前后源码匹配。900.047 s方法返回含47 ms中断处理；清理15.547 s、归档0.343 s及源码归档0.032 s单列，不增加可用预算。迟到原生结果`exitflag=0`、最终整数可行点0，仅存档，不补认预算内证据。本轮一次调用、无补跑、无正式对照。

**下一小目标建议：先核原MILP松弛和整数求解结构，不继续把启动／构造当主要门槛。** 本次857.235 s用于等待求解及读取，内部下界只报告0，未得到安全能量收敛区间；尚不能区分条件约束松弛、数值条件、割平面成本与R2023b实现的作用。优先静态盘点这些具体结构，再讨论有依据的表达强化或正式预算；不自动加时、删合法选择或改物理参数。900 s是本次诊断授权，不是已确定的正式比较预算。`formal_experiments_ready=false`。

下方K.80及更早内容保留为历史，当前预算授权以D106为准。

**历史K.80：同一原基准完整方法级核查完成，60 s停于MATLAB启动，未进入求解（D105／E523）。** [完整调用01](research/chapter3_experiments/results/base_method_diagnostic01/result.json)采用原串行顺序：输入读取／展开0.015 s、模型构造38.344 s、MATLAB启动等待21.641 s，共60.000 s。完整模型91844变量、1172563行、8331273非零元；本次矩阵尚未导出，提交请求0、求解器调用0、连续复核未到达，`UNRESOLVED / WALL_TIME_LIMIT`，安全能量为空。

**改动与验证：** 仅增加完整诊断入口、Python交接分项记录、MATLAB内部计时及启动／求解状态区分，模型、输入、系数、评价器与`6b8edfd`逐字节相同。[计时10](research/chapter3_experiments/results/method_precheck10/checks.json)29/29、[桥接预算03](research/chapter3_experiments/results/bridge_budget_precheck03/checks.json)9/9、[实际MILP12](research/chapter3_experiments/results/milp_precheck12/checks.json)82/82通过。清理14.062 s、归档0.672 s和源码归档0.031 s单列；清理后虽有READY文件及许可成功记录，也不补认预算内就绪。详见[README §3.11](research/chapter3_experiments/README.md#311-原基准完整方法级调用核查)。正式对照未运行，本轮只作一次原基准调用。

**下一小目标建议：核独立MATLAB启动与模型构造在同一绝对预算内重叠的可实施性。** 当前启动握手只检查环境与许可，不依赖候选矩阵；可考虑计时开始后启动本次专用进程，同时构造模型，统一截止、独立缓存和预算外清理仍保留。此项尚未实现或验证，不从预算外预热、不复用其他调用的进程，也不先改60 s预算、合法域或物理参数。原串行调用不足以完成，不说明模型不可行或求解器本身慢；求解与评价原规模成本仍未知。`formal_experiments_ready=false`。

下方K.79及更早记录为历史，当前状态以K.80为准。

**历史K.79：控制状态与活动功率行等价复用完成；原基准完整模型及矩阵首次在60 s内完成（D104／E522）。** 复用精确右端与误差元数据、活动功率上下两行的系数转换及变量盒误差，共享不可变小数值／标签，保留全部行、独立可变记录和原顺序。数学表达、合法选择、参数与误差包络不变。[逐行07](research/chapter3_experiments/results/construction_precheck07/checks.json)198/198、[MILP11](research/chapter3_experiments/results/milp_precheck11/checks.json)81/81、[计时09](research/chapter3_experiments/results/method_precheck09/checks.json)24/24通过，对照`d870514`。

**唯一一次原基准核查：** [诊断06](research/chapter3_experiments/results/base_build_diagnostic06/result.json)保持6422选项、400 ms／5 ms与60 s预算，总计47.469 s，模型构造38.797 s、矩阵导出8.656 s。完整模型91844变量、1172563行、8331273非零元；两场景851／928个热区间均完成。控制状态4.891 s、活动行3.827 s、活动导出预备0.025 s、热条件行22.778 s、系数5.376 s。峰RSS1340.375 MiB包含矩阵导出阶段，不能与上轮部分模型直接作等规模内存比较。状态`CONSTRUCTION_COMPLETE`，求解器未启动，无安全解或最优性结论；详见[README §3.10](research/chapter3_experiments/README.md#310-控制状态与活动功率行的组装和存储复用)。

**下一小目标建议：核同一原基准的完整方法级调用是否可实施。** 现已跨过构造门槛，本次只余12.531 s给尚未执行的MATLAB启动、矩阵交接、求解及完整复核，不能据构造完成宣布正式实验就绪。先核这些环节与同一60 s计费的衔接，再决定是否接正式对照；不继续无目标优化、不改参数或补跑本轮诊断。`formal_experiments_ready=false`。

下方K.78及更早内容保留为历史，当前状态以K.79为准。

**历史K.78：命中组装、活动功率行及上界成本已拆清并等价优化；原基准60 s推进到第二场景热区间第732/928，整体仍未完成（D103／E521）。** 采用热等式双向成对模板、精确边界签名、有理系数与负号转换复用、重复舍入误差的精确计数求和，以及功率上界公共项提取；数学表达、合法选择、输入和误差包络不变。最终[逐行预检06](research/chapter3_experiments/results/construction_precheck06/checks.json)186/186、MILP回归81/81、方法计时24/24通过，对照`7bbe999`。

**同一原基准：** [诊断05](research/chapter3_experiments/results/base_build_diagnostic05/result.json)保留6422选项、400 ms／5 ms、60 s，60.000 s停止。29.031 s完成第一场景并进入第二场景，上轮04为57.829 s；第二场景控制层完成，热构造推进到第732/928区间。控制状态23.438 s、热条件行20.086 s、活动功率行9.978 s、系数4.653 s、功率上界0.216 s；峰RSS1066.492 MiB对应更多已生成内容。完整模型／矩阵未完成，求解器未启动，状态`UNRESOLVED`，无正式对照。详见[README §3.9](research/chapter3_experiments/README.md#39-命中后的组装活动功率行与功率上界)。

**下一小目标建议：优先核控制状态与活动功率行的重复组装／存储。** 当前功率上界不再是主要成本，不继续泛化为Python慢；不自动改变参数、合法域、安全保证或预算。保留中间剖析未变快的结果和诊断脚本归档错误，不能凭单次进度宣称稳定求解加速。`formal_experiments_ready=false`；本轮一次原基准核查后停止。

下方K.77及更早记录为历史，当前优先级以K.78为准。

**历史K.77：条件约束模板复用通过逐行预检；原基准60 s已完成第一场景，但完整模型仍未构造完（D102／E520）。** 模板只复用有序系数、变量边界、右端及条件变量位置完全一致的数值行，逐行重编号，不删约束；数学表达、合法选择、物理参数和误差包络保持。[等价预检04](research/chapter3_experiments/results/construction_precheck04/checks.json)171/171、MILP回归81/81、方法计时24/24通过，参考提交为`720194e`。

**同一原基准结果：** [诊断04](research/chapter3_experiments/results/base_build_diagnostic04/result.json)保留6422选项、400 ms及5 ms，60.000 s停止。第一场景851个热区间全部完成，57.829 s进入第二场景，最终停在其控制区间第163/928；上次03停在第一场景热区间第205/851。模板命中226260次，完整计算3510项，未清理；热条件行25.378 s、系数4.420 s、热阶段观察0.213 s，其余约17.583 s尚未细分。完整模型／矩阵未完成，求解器未启动，仍为`UNRESOLVED`，正式对照未运行。详见[README §3.8](research/chapter3_experiments/README.md#38-条件约束模板复用)。

**下一小目标建议：只拆分模板命中后的键构造／重编号与非条件热能耗组装成本，再决定等价改进。** 不以本次进度直接宣称完整求解加速，不自动增加预算、修改参数／合法域或运行正式对照。`formal_experiments_ready=false`；本轮在一次原基准诊断后停止。

下方K.76及更早记录为历史，当前优先级以K.77为准。

**历史K.76：热能耗成本已拆分并等价优化，原基准60 s仍未完成构造（D101／E519）。** 本次复用同状态的精确Taylor矩阵幂、变量边界及系数转换，进度记录改为累计计数；数学行、合法选项、物理参数与误差包络保持。[等价预检03](research/chapter3_experiments/results/construction_precheck03/checks.json)157/157、原MILP回归81/81、计时检查24/24通过。

**同一原基准结果：** [诊断03](research/chapter3_experiments/results/base_build_diagnostic03/result.json)保留6422选项，60 s预算下于60.015 s检查点停止。首场景热能耗构造从上轮第74区间推进到第205/851区间；本次该阶段47.875 s中，系数查找／生成4.001 s、条件行组装40.010 s、观察0.139 s，其余差额约3.725 s。全程观察由上轮4.054 s降至0.203 s。完整模型、第二场景和求解均未完成或未开始，不能作算法收益结论；正式对照未运行。详见[README §3.7](research/chapter3_experiments/README.md#37-热能耗构造的分项核查与等价复用)。

**下一小目标建议：只核条件约束的重复模板及Big-M／舍入量能否等价复用，再过逐行预检。** 当前主要已测成本是条件行组装，不再泛称Python慢或热系数慢；不自动改变参数、合法域、安全要求、语言或60 s预算。`formal_experiments_ready=false`；本轮诊断后停止，不追加补跑。

下方K.75及更早内容保留为历史选择和阶段结果，当前优先级以K.76为准。

**历史K.75：等价构造优化及同一原基准60 s核查完成，完整模型仍未构造完（D100／E518）。** [新旧构造预检](research/chapter3_experiments/results/construction_precheck02/checks.json)138/138、原MILP回归81/81、方法计时23/23通过；五小域438条完整赋值、完整物理行、反馈后矩阵及原始误差记录一致。改动仅为有序索引、半开事件扫描、精确整数快速转换及纯参数复用；数学表达、全部合法选项和原配置逐字节保持。

**原基准结果：** [优化后02](research/chapter3_experiments/results/base_build_diagnostic02/result.json)保留全部6422选项。首场景全部851控制区间在10.188 s内构造完；旧01用58.968 s只到第297区间。新记录60.000 s停在首场景热能耗约束第74区间，已完成351组系数、创建74个能量变量，尚非完整模型；第二场景和求解器未开始。热能耗阶段49.312 s尚未细分；观察开销4.054 s已计费，Python峰RSS382.789 MiB对应更多已生成内容。两次都是构造诊断，未运行正式对照，详见[README §3.6](research/chapter3_experiments/README.md#36-等价构造优化与语言选择)。

**下一小目标建议：仅拆清热能耗阶段的系数生成、条件约束组装及观察成本，再选择等价改进。** 本次已证明当前构造组织可以改善，尚无Python／MATLAB语言对照依据；暂保留Python可靠数值构造＋MATLAB求解，不直接整体迁移，也不改400 ms、5 ms、工作负载或热保证。完整矩阵未可用，`formal_experiments_ready=false`；不自动追加原基准补跑。

下方K.74及更早阶段保留为历史记录；本段为K.75完成时的建议。写作对齐记录独立保留。

**历史K.74：统一方法计时已落实；原基准一次60 s构造诊断未完成（D99／E517）。** 输入读取／单例展开、构造、MATLAB独立启动、导出、求解、连续评价和反馈共享绝对截止期；清理及归档另列。方法预算预检23/23、实际桥接11/11、MILP小域回归81/81通过。400 ms、5 ms及全部物理／工作负载参数保持，正式对照未运行。

**原基准结果：** [base_build_diagnostic01](research/chapter3_experiments/results/base_build_diagnostic01/result.json)保留全部6422选项，60.015 s停在首场景控制状态约束构造，第297/851区间已开始；已生成17988变量、107151行，控制状态阶段58.968 s。热系数组和能量变量均为0，矩阵未完整，MATLAB未启动；峰RSS159.078 MiB，进度观察耗时0.593 s。只能定位当前实现的构造开销，不能判断求解器速度、完整问题无解或方法收益。详见[README §3.4—3.5](research/chapter3_experiments/README.md#34-已落实的方法级计时)。

**下一步建议：只做保持数学表达与合法域等价的构造改进，再验收同一基准。** 优先核重复选项扫描、精确时间转换和约束组装；先过小域等价检查，不自动删频档、改粗起点、扩大预算或降低热保证。当前`formal_experiments_ready=false`，HEFT／SA及正式批量执行继续待接；本轮不追加原基准补跑。

下方写作对齐记录独立保留；本段及K.73以前的“下一步”为各阶段完成时的历史建议。

**写作对齐（2026-10-16，主线6）：** 已按用户要求修订[研究现状讨论稿](research/国内外研究现状与本文问题定位_讨论稿.md)：保留异构推理、热管理与热约束节能三类主体，重写“多场景共享部署”及本文定位；Kim作为共享具体部署的继承来源，转换类四篇移附录备查。沿用S1／I1／G1及当前第三章，不引入场景切换、跨场景热历史或新模型假设。取舍及原文定位见[修订记录§6](research/国内外研究现状与本文问题定位_审查记录.md)。本项仅更新写作材料，不改变当前实现阶段与下一步安排。

**当前阶段K.73：完整热能耗MILP与连续反馈已接入，小域预检81/81通过（D98／E516）。** 实现共享具体部署、Stage有限选项、逐忙段工作点及空闲保持；状态条件仿射递推和完整窗口能量进入MILP，候选由原共同评价器独立接纳。系数余项及浮点行向外包围，明确违规反馈保留其他合法时序；安全上界与求解器报告状态分开。400 ms、5 ms及原功热／工作负载参数逐字节保持，正式95问题／675调用未运行。

**可复跑证据：** [milp_precheck04](research/chapter3_experiments/results/milp_precheck04/checks.json)81/81，独立检查438条小域赋值；六方案完整能量与MILP选择一致，段内峰温的真实求解—检查—反馈闭环通过。01—03失败记录保留：源码变化、文件发布竞态及默认整数预处理报告无解分别处理。最后一项以原矩阵隔离诊断，统一采用`IntegerPreprocess='none'`后通过；不改数学问题、不增加温限容差，不推断求解器普遍失效。全部实现细则和诊断入口集中于[README §3.3](research/chapter3_experiments/README.md#33-已接入的完整热能耗milp与连续反馈)。

**下一步建议：先核方法级共同计费和原基准规模的构造可行性，再接比较方法与正式执行。** 小域正确性通过不等于原6422选项问题能在60 s内构造或求解；尚缺HEFT／SA适配、独立调用与正式协议接入。当前`formal_experiments_ready=false`，本轮不自动运行正式对照或调物理参数。

以下K.72保留为评价基础层完成时的记录；当前进度以上述K.73为准。

**当前阶段K.72：共同连续热能耗评价器已实现，必要预检50/50通过（D97／E515）。** 新增[thermal.py](research/chapter3_experiments/thermal.py)，调用原完整安排检查与功率片段重构，按本地温度计算四节点漏电、连续传播、段内峰温和400 ms完整能量。CPU基准去重、边界外公共功率不注热、逐忙段工作点及空闲保持均沿原模型；`config_v01.json`与K.71逐字节相同。只有全部声明场景合法、完整、热安全且误差达标后才输出加权能量与安全上界。

**可复跑证据：** [thermal_precheck02](research/chapter3_experiments/results/thermal_precheck02/checks.json)50/50；首轮36/36及源码快照保留。闭式温度／能量、独立ODE、守恒双算、GPU／NPU活动、非整数结束、空闲导热内峰、零权重场景、跨温限包络未决和中断均有夹具。精度沿用1e-3 K、绝对／相对1e-6能量目标；保证来自定向区间与Taylor余项，ODE仅作实现核对。数值失败、资源不足与非法输入分列，预算内已有违规不会因外层超时丢失；未完成／不安全能量不参与汇总。预检是程序核对，不是95问题的正式比较或节能效果证据。

**下一步：接入第三章MILP候选构造与共同评价接口，并做小域编码／反馈预检。** 当前评价器能确认给定完整候选，尚未生成MILP系数或验证共享热反馈约束；HEFT／SA规则与正式计费协议随后落实。不改当前参数、不提前批量运行正式对照。数值方案与状态契约集中维护在[README第3.2节](research/chapter3_experiments/README.md#32-已实现的连续热能耗与数值协议)。

以下K.71保留为基础层完成时的记录，当前进度以上述K.72为准。

**当前阶段K.71：第三章首版输入与基础检查已实现，尚未运行正式对照（D96／E514）。** 用户确认暂保留已审阅的400 ms窗口、5 ms起点与功热参数，并授权逐步推进实验。新增独立目录[chapter3_experiments](research/chapter3_experiments/README.md)：`config_v01.json`转录数值，`inputs.py`精确生成19条件×5变体＝95项输入；完整安排检查器覆盖共享部署、逐请求期限、半开互斥、同域工作点及空闲保持，重构本地注热和完整窗口功率片段。

**可复跑结果：最新基础预检233/233通过，MATLAB R2023b与Optimization Toolbox许可签出成功。** 结果见[input_precheck03](research/chapter3_experiments/results/input_precheck03/checks.json)和[environment02](research/chapter3_experiments/results/environment02/environment.json)。预检01的224项、补充加速器夹具后的02的228项均保留；首次环境探针启动超时且清理遇错，原记录保留，第二次使用现有工作区偏好目录在提升执行环境下完成核查，未据此判断首次失败的单一原因。尚未运行求解器或连续热传播；合法性通过只输出`SCHEDULE_VALID_THERMAL_UNCHECKED`，没有研究能量、热安全或最优结论。

**下一步：实现共同四节点连续热能耗评价器及其必要预检，再接MILP和HEFT／SA。** 无需重新选择当前物理模型；还须落实连续误差包络、方法可执行规则及计时／中断协议。基本输入R1有6422个局部选项，两场景分别852／929个潜在事件，这是表达规模记录，不是完整安排枚举或已测求解瓶颈。正式95问题／675调用尚未开始，不提前把输入检查当作全部正式运行门槛通过。参数来源、窗口相关尾段能耗及有限起点限制保持。

以下K.70保留为数值提案阶段记录；当前授权与实施状态以上述K.71为准。

**当前阶段K.70：第三章基础配置、五组具体条件与共同比较规则已形成数值提案v0.1（D93—D95／E513）。** 详细数字集中维护于[配置草案第7—10节](research/第三章实验输入来源核查与配置草案.md#7基础配置数值提案-v01)。本轮按用户要求暂不深入HEFT／SA，先给齐合法OPP、Stage响应／活动功率、基准及本地漏电、四节点RC、入口／温限、期限／窗口／起点、样本与计费。所有新物理数字明确为自设或由自设输入派生，没有冒称同平台测量。

**已集中确认：资源组在同一2 CPU＋GPU＋NPU平台上改变可用设备，未使用设备仍有空闲功耗和热节点（D94）；任务规模组保持三Stage链，增加每应用请求数1／2／3，分支汇合先用于正确性预检（D95）。** 其余数字仍为可审阅草案：主比较采用本文方法、HEFT适配版、SA适配版，混合方法保留候选，连续反馈消融另嵌入预声明子集。19个去重条件×5个工作负载变体=95个问题，SA各5次，另10次消融，共675次调用；每次60 s为本轮计算限额建议，理论方法计时上限11.25 h，尚未执行。

**下一步：集中审阅剩余数值包与实现可行性，再补实现必要的算法规则和数值预检协议。** 不将D94—D95的范围回答升级为全部物理参数／网格／预算冻结。先后顺序按D93调整，不再先单独深入HEFT／SA；不新增研究方向或实验组。本轮仅文档与代数核对，未改正文、实验代码或旧参数，未运行仿真／求解器。

以下D92／K.69内容保留为此前交接，当前推进顺序以上述K.70及D93—D95为准。

**对照方法交接（主线6，2026-10-15，D92／E512）：用户同意先按HEFT适配版和SA适配版考虑，详见[配置草案§6.4—6.7](research/第三章实验输入来源核查与配置草案.md#baseline-selection)。** 原文依据、适配要求及待定规则集中维护于该处；建议主对照为本文MILP、HEFT适配版、SA适配版及固定部署／次序的混合方法，另用仅整表排除的MILP做热反馈消融。混合方法比较提前固定决策的质量／成本，消融核查热反馈作用，两者不替代。具体规则、数值和运行安排未冻结；只交付文档，未改模型／代码或运行实验。

**实验规划更新（主线6，2026-10-15，D91／E511）：用户已确认五组实验问题，见[配置草案第6节](research/第三章实验输入来源核查与配置草案.md#6第三章五组实验规划)。** 按“不同场景／资源、任务规模、期限松紧、热条件、任务频率响应下，各算法的能耗、可调度性或求解时间表现”组织，供主线7参考。具体参数、算法规则和运行安排仍待确定；本轮只整理文档并提交，不改正文、不编程、不实验。当前模型与K.69输入准备阶段保持。

**当前阶段K.69：第三章实验输入来源核查与配置草案已形成（D90／E510）。** 已定向核对Kim、HaX-CoNN、Da Costa、Zhou、F-DTM、Chantem及ASPLOS 2025 NPU功耗论文的实验章节、参数来源和计量边界，交付[输入来源核查与配置草案](research/第三章实验输入来源核查与配置草案.md)。用户确认首版采用文献指导的抽象仿真；来源方法、原文取值、推导值及自设值分列，不将跨平台数据拼装成同平台实测。

配置草案建议2个CPU单元＋1 GPU＋1 NPU、3个控制域和4个本地热节点，以A＋B／A＋C两场景展示共享部署；具体规模、合法支持、OPP和权重均未冻结。完整配套的响应、局部温度功率与RC数值仍须建立。已核论文主要支持构造与标定方法；Kim低频1/f推算、HPC整机响应、稳态热参数和传感器采样都不能直接替代本题输入或连续保证。本轮只写研究材料，未改论文正文、模型、研究程序或旧结果，未运行实验。

**下一步建议：集中形成数值输入包、对照算法规则表及纸面一致性清单。** 沿当前3.2—3.6和配置草案，给齐场景／共享身份、工作点／响应、来源功率／热网络、期限／窗口／权重、有限起点及数值执行要求，逐项标来源与单位；补清HEFT构造、SA邻域与失败处理、混合方法固定变量、消融唯一差异。一次审阅关键取舍，不按预期收益筛参数。具体起点间隔、预算及求解选项尚未确定，不默认旧1 ms／20 ms／60 s。输入、规则和预检协议确认后再实现、运行预检与正式对照，最后补3.7。本轮结束于文档交接，不自动进入下一项。

**实验组织参考补充（主线6，2026-10-15／E509）：** 用户要求将师兄实验的公共规则、多组实验分工、结果叙述及三四章衔接写入文档供主线⑦参考，已补入[87号第5节](research/87_师兄第三章实验设计思路复盘.md)。建议按“验证问题—公共规则—输入与分组设计—对应结果—质量与成本总结”组织实验材料；当前K.68模型和下一步输入／预检准备不变。旧87号第4节标为历史迁移判断；本轮没有确认新的实验组数、算法或数值，不改正文、不编程、不实验。

**历史阶段K.68：落实3.2—3.6逐节讨论中的叙述改善，转入实验准备（D88／E508）。** 用户已逐节讨论系统模型、功耗与温度、问题定义、形式化及求解流程，并授权把优先阅读问题改入`research/latex/chapter03.tex`。本轮保持公式、模型和求解规则，补概念例子、输入分类及流程分支；不填仿真结果，不改研究代码或参数。预览仍为[多场景第三章初稿](research/latex/build/main_multiscenario_draft.pdf)，批注版原样保留。

**K.68当时的下一步（D89，文献输入核查现已由K.69推进）：先核文献中的实验输入依据，再集中准备第三章配套输入与实现预检协议。** 借鉴87号第5节的实验组织，具体配置重新核查相关文献及其参数来源，不能直接采用师兄或旧实验取值。先盘点可复用的数据和代码，区分已有来源、可派生参数与需共同确认的场景／资源／窗口权重／启动集合；同时说明连续多节点检查、系数误差和求解接口怎样预检。未确定项集中讨论，不自行冻结旧1 ms／20 ms／60 s或补造实测数据。输入和协议确认后再实施预检，通过后运行正式对照，最后填写3.7。

以下K.67文字保留初稿交付时的状态，其中“先审阅正文”已通过本次逐节讨论推进。

**历史交付K.67：第三章模型与方法LaTeX初稿已形成（E507）。** 用户已授权按八节安排开始写作，并确认`research/latex/chapter03.tex`为主版本，`chapter03_new.tex`作为批注参考原样保留（D87）。当前稿完成3.1—3.6、仅含理论内容的3.8及章末推导／符号表；3.7留实验组织，没有数值结果。预览为[多场景第三章初稿](research/latex/build/main_multiscenario_draft.pdf)。

沿用S1／I1／G1、D76及D82—D84，未增加物理假设。固定事件下的温度递推与完整能量积分、有效残差界、逐忙段控制、状态条件热反馈及有限域保证已集中写入正文和补充推导。数学与叙述辅助复审修正了入口点覆盖、窗外选项筛除、安全候选续解、窗口末点活动结束及能量区间上界等边界；这属于纸面审查，不是代码预检或实验通过。

**K.67当时的后续安排：先共同审阅3.2—3.6是否准确、易读；无基础调整后，一次准备配套输入与数值实现／预检协议，再实现并运行实验，最后填写3.7和实验小结。** 尚缺具体场景、物理参数与来源、窗口／权重、启动集合、系数误差处理、一般多节点连续检查及求解配置。参数数值不影响先写符号模型；实现正确性和性能结论必须分别由预检与正式实验支持。本轮不自动开始这些工作，不追求预先写出收益。

以下D85—D86交接文字保留其当时状态；“尚未整合”“只记录目录”不代表当前正文仍未写作。

**当前推进顺序已由用户调整（D85）：先理顺符号模型、问题定义、问题分析与MILP形式化，再准备具体实验输入。** 主线7先读[独立审查§9](research/Kim多场景共享部署_求解路线独立审查.md)。现有核心模型与主要公式保留，具体参数暂用符号；下一项依次统一模型及索引、一般／受限问题、形式化理由、完整目标MILP与连续检查反馈，不直接进入小规模实例设定。本阶段不写代码、不做实验、不改既有物理假设。

本轮仅交付推进顺序与待补清单，尚未完成上述整合。D82逐忙段调频、D83有限启动参照、D84本地温度／注热及S1／I1／G1不变；参数未赋值不等于模型缺失，符号定义／映射／有效条件不明确也不能交给实验填值代替。完成边界为可集中审阅的模型与形式化材料及分类待办，不要求本阶段获得数值结果或证明收益。

**写作安排补充（D86）：沿用第三章八节骨架，目录及子小节见[独立审查§9.5](research/Kim多场景共享部署_求解路线独立审查.md)。** 系统模型按任务与多场景、处理器、执行模式与时长三节；功耗与温度按功耗组成、CPU、GPU、NPU、系统能耗、瞬态温度六节。主线7后续先形成模型与方法初稿，参数保留符号；3.7实验部分留框架，3.8不预写实验结论。先审阅初稿，再准备输入、实现预检与实验。本轮只记录目录，不改正文或开始上述工作。

**已完成K.66：第三章MILP输入与表达清单已整理（E506）。** [共同接口§11](research/Kim多场景共享部署_共同模型与求解接口.md)合并D82逐忙段调频、D83有限启动参照、D84本地温度与注热，分清三类：共享部署／选项／资源期限／域控制可直接线性编码；物理输入给齐后，固定事件的温度传播与完整能耗可条件仿射编码；连续热安全、有效域及数值误差须由独立检查与有效反馈闭环。

完整E进入MILP目标，活动能量不重复累加，外部评价复核同一目标；不退回活动代理或每场景一次OPP。清单列出九组输入、可由输入派生的量及待制定的数值协议。窗口覆盖最大期限不等于默认取该值；组跨多个域时物理参数须覆盖完整控制状态。无新增用户选择，不写代码、不实验；正式模型、R86和论文正文均未修改。

**K.66原下一步建议（已由D85后移）：一次整理配套的小规模第三章输入草案，先核资料来源与缺口，再集中审阅实例范围、窗口／权重及有限启动集合。** 待符号模型与形式化理顺后再安排；不拆成每个参数单独提问，不复用旧1 ms／20 ms／60 s作为默认，不要求制造收益。生成事件和系数等工作属于数据给足后的技术派生，数值误差及连续检查协议仍待落实；本轮不自动实施。

**历史K.65：用户已确认按来源使用本地温度计算温度修正，并在本地节点注热（D84／E505）。** [共同接口§10](research/Kim多场景共享部署_共同模型与求解接口.md)区分温度取值、功率来源分配与节点间导热，以两个CPU单元的教学例说明总电功率相同不代表空间注热相同。共享基准单计并另给分布，Stage活动注入执行单元节点；CPU单元和GPU／NPU设备热粒度不变。不以组平均温度替代节点温限。

已追加[R86-v1.1（原表§7）](research/86_实验基础模型与假设确认总表.md)，同步[系统模型§4及相关输入／能量式](research/第三章系统模型_审定稿.md)。这是空间接口细化，不声称只是给旧标量组表达填参数；旧版和理由保留。来源系数按硬件／工作点给定、工作与空闲共用，不新增逐Stage漏电参数。固定状态下仍为仿射热／电功率关系，可承接已有有限事件构造，但传播、能量系数及界须按本地来源重建。

**下一小目标：只合并已确认D82—D84，整理第三章受限MILP的输入与表达清单，核清待填数据及数值处理。** 不追加物理机制；一般模型连续，第三章采用尚未选定具体值的有限启动集合，保留逐忙段DVFS和连续温限。局部功率来源、基准分布和物理参数仍需匹配数据或显式L3，不能从整包数据任意拆分。本轮只更新五份研究文档，未改论文正文、研究程序、实验输入或历史结果，未运行实验。

**历史K.64：用户已确认第三章采用预先声明的有限启动集合（D83／E504）。** [共同接口§9](research/Kim多场景共享部署_共同模型与求解接口.md)完成范围比较与选择登记：一般模型保持连续启动，第三章另设有限起点参照；保留逐忙段调频、真实时长／结束、连续温限及完整能耗。起点限制可能遗漏连续域好解或可行解，最优／无解结论仅按所声明集合解释，不自动提升为连续域证明。

**下一小目标：只明确完整热能耗MILP构造的物理接口支持范围。** 当前表达需要已知完整域状态、线性／仿射代表温度与相容注热映射、有效温区及相应界；不得默认平均温度或均分注热。启动集合的生成方式、间隔、窗口、预算、求解器和数值误差规则仍未选定，不沿用旧1 ms等参数。本轮只完成比较与D83登记，未改正式模型、论文正文、程序或实验输入，未运行实验。

**历史K.63：逐忙段调频的有限事件MILP控制表达已完成纸面核查（D82／E503）。** [共同接口§8](research/Kim多场景共享部署_共同模型与求解接口.md)用逐段域状态、活动Stage锁点及“当刻无新启动则保持”三组线性关系表达原R86规则，无需预先编号忙段或另增换点决策。持续Stage锁住边界两侧；全体旧工作结束后可为同刻新启动换点，入口／空闲／尾段保持不变。有限起点、确定域状态及线性物理映射是这条构造的条件，未因本轮推导成为用户确认的模型限制。

同一合法选项域下，事件集和条件仿射热传播／完整能量／连续温限反馈可以复用；一次OPP专用链接须替换，不能冒称原编码已经支持。新增控制行量级与可达状态序列分开说明：矩阵量级可不变，实际求解成本仍未知。正文、R86、正式系统模型、程序及研究输入均未修改，未运行实验或数值预检。

**下一小目标建议：只确认第三章参照的启动域。** 有限集合能使片段长度成为已知量，但可能遗漏连续域方案；若接受，再明确物理接口支持及输入范围，不自动沿用1 ms或旧预算。若坚持完整连续域参照，本构造不能直接使用，须另审非线性时长关系。逐忙段选择继续保留，不因MILP表达完成而宣称已获收益或最优结果。

**D82选择时记录：一般模型保留逐忙段调频，一次工作点保留为简化版本或对照（D82／E502）。** 用户已接受这一取向；没有采用K.62建议包中的场景内一次OPP限制。沿原R86，在域内无持续执行Stage、下一工作启动时允许选新点，同域并发保持相容工作点，Stage执行中不改点，空闲及尾段保持最近点。该自由度用于区别配置不同响应的Stage，以及协调频率、并发、期限与热状态；尚不承诺节能收益或创新。

下一小目标只纸面补齐逐忙段调频的控制状态表达，说明相对K.62一次OPP草案新增哪些变量／约束、哪些温度与能量表达可复用。一般模型仍保留连续起点；有限启动域及其取值、线性代表温度／注热接口支持范围尚未由本次确认。完整MILP参照若只实现一次OPP，结论只针对该受限政策，不能代替逐忙段问题的完整参照。当前不改正式模型、代码或实验输入，不运行实验。

**K.62纸面草案历史：完整热能耗MILP参照的最小取舍与条件表达已完成纸面核查，等待范围确认（D81／E501）。** [共同接口§7](research/Kim多场景共享部署_共同模型与求解接口.md)建议首版采用有限启动选项、每场景每域首次启用后保持一个所选OPP，并明确线性代表温度／注热映射支持范围；这些仍是助手建议，R86和系统模型尚未改版。共享部署、非统一响应、多节点动态热、温度漏电、完整窗口能耗和逐请求期限保留。逐忙段DVFS原则上也可编码，一次OPP仅为控制范围／规模取舍，不是MILP化的必要条件。

有限起点与全部真实结束组成固定事件集；唯一选项、共享链接、半开占用和域首次启用逻辑确定控制轨迹。每段按联合OPP条件激活仿射温度转移与完整能量积分，完整E直接进入MILP目标；段内违规可生成按状态激活的必要温限，可靠整表排除可保留为最低完整反馈。已给双向对应、符号规模和数学／数值保证分层；只证明条件表达可构造，不证明运行成本、最优已获或算法新颖性。候选域限制、数值系数误差和限时未闭合分别报告，不重开MILP认证支线。

本轮读最新提交81e6bee，暂缓K.61作为默认路线；其有限局部搜索留作方法备查，不能替第三章完整参照。直接回核Chantem的稳态MILP／温度功耗编码与瞬态启发式分工，未借其零热容简化。下一步只集中确认上述首版范围及代价，再修订模型与MILP表达；本轮未修改正式模型、正文、程序、参数或运行实验，不自动推进第四章。

**历史K.61：完整能耗驱动的时序调整与配置重选建议稿已形成（D80／E500），等待共同审阅。** [共同接口§6](research/Kim多场景共享部署_共同模型与求解接口.md)提出一条具体有限工程路线：固定共享部署／模式／实际冲突方向后，在无热可行多面体内以LP生成调整方向，沿连续凸组合试探，每次重建OPP与完整热能耗；按安全能量上端改进移动时序中心。外层以最好全场景安全方案为中心，查询共享Stage换设备、场景域工作点改变、冲突换序三类邻域，完整加权U下降后重建后续查询。不是末端一次性评分，也不称全局精确分解。启动前无安全表先做有限可行性恢复；失败、未分辨和查询去重不作配置排除。非统一响应通过外层工作点改变时长和内层可行域；原模型不变。

本轮直接复核Bao TVLSI2012 §VI-A／图5与Huang DATE2011 §2—3.2，借热分析进入优化、片段热能量联合计算，不移植其单处理器、低功耗空闲、周期稳态或执行中切速。具体LP试探与邻域规则是助手建议，尚未作为用户已确认首版协议；半径、配额、预算、输入支持仍待审定。只做原文、代码静态及代数核查，不改系统模型、正文、研究程序或参数，不实验。下一项先共同审阅这份路线；确认后合并明确输入支持、方法限额与必要预检，不自动实现或增设机制。

**历史K.60：已读独立审查§5—7，下一步建议调整为“完整能耗驱动的分解路线可行性核查”（D79／E499）。** K.59表达不推翻；采纳审查提出的接口要求：完整能耗应指导连续起点更新，并影响离散配置重选，不能只给事先固定的候选打分。计划仅纸面落实一条路线，不选求解器、不实现、不实验；直接完整混合整数非线性求解保留备选，不并行展开。此为主会话建议，具体协议未获用户确认。

| 下一小目标内部顺序 | 必须形成的内容 |
|---|---|
| 1．核清可借方法与固定决策 | 定向回核Bao热分析—连续时间优化、Huang片段热能量计算，登记与本题的差异；列清MILP管共享部署、工作点、哪些必要次序，连续子问题还优化哪些起点 |
| 2．落实完整能耗的连续优化接口 | 以原E为目标，说明评价如何参与起点更新；处理跨设备事件次序变化、保持OPP、逐请求期限及连续温限；列出评价器必需且尚未补齐的输入关系 |
| 3．落实离散配置重选 | 完整能耗／热结果具体怎样影响下一轮设备、工作点或次序候选；覆盖已有安全表后仍改进、重复、失败、未分辨和停止，不把局部结果当全域切面 |
| 4．一次纸面走通与工作量盘点 | 用无数值例子走通“连续调整→完整复核→反馈重选”，列继承／新做接口、保证和限制，形成一份简短协议草案；无需构造收益或实验反例 |

**完成边界：** 能明确说明下一张时序、下一种配置如何由完整评价信息产生或选择，并保持所有场景安全接纳；还须区分搜索所查范围与原连续域。不以全局最优认证为准入门槛，不默认连续子问题凸或固定冲突次序已固定全部事件次序。若必须改变物理假设、加入启动网格或采用新的热模型近似，先列取舍并请用户确认；候选覆盖／求解近似也须显式说明，不写成已确认方案。结束于共同审阅草案，不自动写代码或实验。

**历史K.59：MILP表达与完整评价分工已整理（D78／E498）。** [系统模型稿§7](research/第三章系统模型_审定稿.md)明确共享部署、场景模式、连续起止、释放／依赖／期限及资源冲突的线性编码，给出模式激活的先后析取与由窗口导出的M；频率域完整编码须有明确控制状态输入。非统一响应在有限合法点上成为已知系数，活动能量可线性表达；保持工作点的基准积分和温度漏电／连续温限本轮交完整评价器。候选交接x、z及实际s，全场景合格才记录真实能量上界；一张超温表不能排除整配置。未冻结代理目标、连续时序再查或预算，未写研究代码、改正文或实验。只读子任务因服务容量未能执行，本轮由主会话完成代数与文档核对，不记独立审查通过。下一项只共同确定候选查询目标与连续时序覆盖方式。

**历史K.58：第三章问题定义已整理，等待共同审阅（D77／E497）。** [系统模型稿§6](research/第三章系统模型_审定稿.md)追加输入表、共享部署x／场景模式z／连续起点s、六组约束及加权完整能耗目标。响应沿D76，温度、OPP保持轨迹和能耗均由方案导出；同域换点明确按结束→换点→启动处理，零权重场景仍须安全。未定计量／温度／注热关系保留已知输入，不新增基础选择或实验数值。两项只读子任务复核通过，非主线6审查；未改正文／代码或运行实验。下一项只整理MILP表达与外部评价分工，不直接实现候选搜索。

**历史K.57：第三章系统模型已收拢，用户确认主要响应公式（D75—D76／E496）。** [审定稿](research/第三章系统模型_审定稿.md)按场景任务、处理器执行、任务响应、功耗温度四部分，区分已确认结构、待明确输入关系和未来实验数值。沿S1具体单元共享、I1场景独立完整入口、G1加权窗口能耗及R86；采用d=d_ref[(1−α)+α·f_ref/f]，α按Stage与设备给定，参数和适用范围后续按资料确定，同工作量／单元／工作点跨场景共用响应。代表温度和注热分布保留为明确输入，不默认平均或均分；基准与漏电修正共用注热映射仅为同分布特例。两项只读子任务复核通过，非主线6审查。本轮未选实验数值、改正文／程序或实验。按用户要求恢复“系统模型→问题定义→MILP求解→实验验证”的推进顺序，K.56候选讨论保留备查；下一项只整理问题定义，不继续候选协议。

**历史K.56：候选MILP—完整评价—反馈路线已说明，保证等级由用户确认（D73—D74／E495）。** [接口说明§5](research/Kim多场景共享部署_共同模型与求解接口.md)追加一条工程路线：以活动能量代理查询共享部署、各场景模式及实际冲突方向，构造连续时序候选，重建OPP并联合计算完整温度／电能，以实际安全能量择优；代表协议、配额和停止限额仍待审定。早／中／晚仅为可实施示范，未冻结旧三代表协议。I1下同一共享部署的各场景安全安排可分别评价并重组，全部场景含零权重须安全。反馈区分安全U、真实排名、违规见证、查询去重与可靠排除；结构no-good不证明热不可行，代理内部界不证明真实最优。用户接受首版连续域最优性未决；未改基础假设、数值、正文、程序或实验，未恢复MILP认证及旧无限切换。下一项只共同审定最小候选协议与必要预检，不直接实现。

**历史K.55：阶段一“共同模型与求解接口说明”完成（D72／E494），等待共同审阅。** [说明稿](research/Kim多场景共享部署_共同模型与求解接口.md)收拢S1共享部署与场景内模式／连续起点、G1完整片段能耗、I1有限窗口热安全，列出输入完备性和规划／评价分工。无热合法域可线性编码；工作点保持和温度漏电下的真实能耗及连续温限尚非完整MILP，代理目标与有效反馈留待下一阶段。组基准／漏电注热与实际单元活动注热分开，全部场景含零权重须合格。三项只读子任务核数学、物理及数据／来源，复审意见已落实，非主线6审查。未选数值、写算法、改正文／程序／R86或实验，旧无限切换问题族未恢复。下一项只讨论一条可实施求解路线，先明确真实目标与MILP候选规划怎样连接。

**历史K.54：用户更正能耗选择为G1，当前范围为S1＋I1＋G1（D71替代D70／E493）。** [更正记录](research/Kim多场景共享部署_一页方案.md#Kim能耗选择更正)：各场景完整评价片段按外给固定权重求平均系统能耗，具体权重及来源尚未确定；具体执行单元共享和每场景给定完整入口保持。G2为上轮误选，历史记录保留，不再作为当前目标。师兄作为参考之一，后续方案须结合其他文献、本题需求、数据和实现条件比较后共同确定，不因与师兄一致就默认合理。仅更正范围及协作原则，不设计算法、不实验、不改正文／程序／R86或数值，不自动进入下一研究阶段。

**历史K.53：用户确认S1＋I1＋G2，Kim候选的三项范围已收拢（D68—D70／E492）。** [确认结果](research/Kim多场景共享部署_一页方案.md#Kim范围确认结果)：同一应用Stage跨场景固定具体执行单元，各场景给定一个完整入口，目标为声明完整评价片段的等权平均系统能耗；工作点及时序仍可随场景变化。G2是师兄§3.5.4式(3-34)加权能耗目标的等权特例，目标形式继承，完整能量计算及连续热可行域按R86扩展。入口不衔接成任意切换保证，窗口／工作负载／数值尚未冻结。仅确认范围与解释目标，不设计算法、不实验、不改正文／程序／R86或恢复暂停实施；下一步由用户审阅已收拢边界，不自动推进方法。

**历史K.52：用户确认先保留Kim路线，正在共同确定范围（D67—D68／E491）。** [范围确认页](research/Kim多场景共享部署_一页方案.md#Kim范围共同确认)给出共享S、入口I、平均能耗权重G三组选项。用户已选择S1：同一应用Stage跨场景固定具体执行单元，工作点与时序仍可变化；I1单一完整入口、G1给定使用权重为助手推荐，尚待回复，不默认采纳。目标解释区分评价片段次数权重与时间占比，安全／期限逐场景满足；窗口与研究数值不冻结。仅讨论与记录，不设计算法、不实验、不改正文／程序／R86或恢复旧多模式实施；本阶段等待入口和权重选择。

**历史K.51：Kim整体建模的第三章增量审查完成（D66／E490），候选保留、范围未冻结。** [判定附记](research/Kim多场景共享部署_一页方案.md#Kim第三章实质增量判定)认为相对Kim增量明确、相对师兄属幅度中等的实质模型扩展，可支撑有内容的第三章候选，尚非强新颖性结论。核心变化是共同部署须满足各场景声明入口下连续温限，且温度漏电／空闲工作点保持使时序一般参与能量评价；非统一响应连接调频时长与占用／注热，但相对师兄不是新增表达能力。各场景入口外给时仅由共同映射耦合，不称跨场景热历史优化；共享依据及权重／窗口／入口仍待确认。两个只读子任务审查，非主线6审查。未设计算法、实验、改正文／程序／R86／参数或恢复暂停实施；建议不加因素，先审阅该成章定位。

**历史K.50：Kim路线三项关系整合完成（D65／E489），仍为候选讨论。** [整合说明](research/Kim多场景共享部署_一页方案.md#Kim三项关系整合)将多场景定位为共享部署要求、非统一响应定位为工作点代价刻画、热状态定位为完整安全与能耗关系；借鉴公式仍可形成自主整体建模，细化K.49“参数适配”判断而不认领新公式。补充A＋B／A＋C共用A2设备的例子和4／2.5ms教学算术，明确同域同频、参数校准及同表等价。Kim已有NPU／DVFS，师兄已有任意τ(f)和时序／检查反馈；拟自主任务为共享约束下响应、资源、期限、入口、功率保持与连续热能耗的自洽建模，方法尚未设计。两个只读来源子任务复核；非主线6审查。仅更新讨论材料，不实验、不改R86／正文／程序／参数，不冻结共享／入口／统计范围或恢复暂停实施。阶段结束于用户审阅三者怎样结合，不自动进入算法或验证。

**历史K.49：Kim一页方案的贡献归属审查完成（D64／E487），仍未选定方向。** [审查附记](research/Kim多场景共享部署_一页方案.md#Kim贡献归属审查)明确热状态及其能耗／连续安全关系是相对师兄的已核增量；师兄τ_j,p(f)已能接收逐Stage／设备／频点响应，仿真其他频点缩放未说明，不能将Kim的统一1/f假设自动归给师兄。响应表、RC物理与外部检查组织主要适配；共享部署下自洽热节能模型为实质扩展，具体有效热反馈／求解规则为方法候选，尚无新颖性或收益结论。两个只读子任务复核原文及归属，非主线6审查。未改一页原稿、R86／代码／正文／参数或实验，未恢复暂停实施；下一项只审阅贡献定位，不自动设计新方法。

**说明补充（2026-10-12，E488）：** 已核Da Costa的刚性／弹性公式、PELSI逐层profile、ASPLOS周期分段结构及实际拟合。当前第三章模式参数接口已可接收非统一响应；以两Stage教学算术说明其通过模式选择影响时长、期限和活动能量，未计算完整热／漏电、未形成研究案例或批准新设定。本项不改变K.49及待确认范围，不改正文或实验。

**历史K.48：Kim路线一页方案已整理（D63／E486），等待共同审阅范围。** [一页方案](research/Kim多场景共享部署_一页方案.md)建议应用Stage跨场景共用具体设备，场景内工作点及时序分别规划；共享部署、NPU、DVFS和开放时序属于继承，拟自主工作为声明入口下完整热能耗评价、有效反馈及对应规划方法。有限请求／完整入口／有限窗口为首版建议，不推出任意切换或长期保证；共享层次、入口及能耗统计仍未获确认。只读子任务审查无必要修正，非主线6审查。仅形成讨论稿，未选定主线、修改R86、实验、改代码／正文／参数或恢复暂停实施。下一项只一起确认方案范围，不自动细化算法。

**历史K.47：Kim共享部署下的热节能价值复核完成（D62／E485），未选定方向。** [筛选表第11节](research/本地文献逐篇能力边界与基座筛选.md#Kim多场景热节能价值)确认Kim已有NPU、DVFS及全场景固定映射，师兄已有共享部署／场景频点／连续时序；可展开的是声明入口下连续热安全、温度相关能耗及有效反馈。共同部署是先在的可实施契约，不以胜过允许独立换映射的理想下界作为立题要求。确定有限场景的轨迹核查比时长不确定事件族更直接，但不保证长期重复或任意切换。助手条件性推荐Kim优先细化，不冒称新颖性；共享层次、入口和目标口径未确认。两个只读子任务完成，非主线6审查；因师兄PDF哈希变化，已重提取关键正文核对，未覆盖旧记录。本轮只改研究记录，不实验、不改R86／代码／正文／参数或恢复暂停实施；下一项仅建议一页候选范围。

**历史K.46：Lombardi候选的热安全路线核查完成（D61／E484），仍未选定方向。** [筛选表第10节](research/本地文献逐篇能力边界与基座筛选.md#事件执行热安全路线)区分原文方法和拟用充分分析：Schor提供活动包络与热分析，原条件不能直接套工作点相关漏电；Pourmohseni提供峰功率安全摘要思想，不原样搬TSPD。有限DAG在待确认的最早完成事件策略下，可传播执行时间窗、构造包含基准／空闲保持／漏电的功率上系统，认证全部允许时长；包络超限只记未认证，有限细分不承诺完备。两项只读来源审查已完成，非主线6审查。旧Schor定理编号误写已追加更正。本轮只改研究记录，未实验、写程序、改正文／参数或批准范围变化；下一项仅建议收拢一页候选方案，讨论策略、区间依据与能耗口径。

**历史K.45：本地原生共同决策要求已核清（D60／E483），未选方向。** [筛选表第9节](research/本地文献逐篇能力边界与基座筛选.md#原生共同决策基座)保留两个主候选：Kim跨场景共用Stage映射，有SDK驻留／装载原因；Lombardi跨实际时长共用附加同步关系与事件执行策略，外部映射固定。前者与师兄同基座，热评价及规划仍需实质展开；后者区别较大，但引入时长区间及改变固定起点语义，须用户确认。Huang为共同累计寿命约束参照，不把可靠性换成峰温；SensiX++为共享传感器／计算图；NeuOS／μ-Serve为共同频率控制，不混作跨情况复用框架。μ-Serve为ATC2024。三项只读子任务复核通过，不是主线6独立审查。既有多模式、物理／服务设定和暂停状态保持；只读材料、追加比较并同步记录，未实验、改程序／参数／正文或重启实现。下一项仅讨论共享部署与共享规则及其范围，不以额外节能结果决定问题是否成立。

**历史K.44：三项工作的贡献归属与Jung／Pourmohseni对照审查完成（D59／E482）。** [一页稿审查附记](research/第三组_核心增量说明.md)明确三项是工作分解：状态／能量关系主要常规适配；重复／转换持续分析是条件性核心候选，尚缺具体判据；反馈候选规划目前主要常规求解组织。Jung已有全模式共同设计、未知具体序列下的吞吐条件及Base反馈；Pourmohseni已有全过程热保证、热耦合、DVFS／共享频率和DSE热反馈，不将这些能力重称创新。可保留的候选是利用合法活动时长、间隔和切换相位形成持续状态覆盖，在相同模型、服务、入口与保证下分析保守性，并用于节能选择；不是已完成方法或全领域新颖性判断。常规适配的论文价值与新分析贡献分开表述；不恢复额外共同节能准入要求。两个只读子任务复核未发现必要修正，非主线6独立审查。本轮只读原文并追加审查，不实验、不改基础设定、不选定方向或恢复实施；下一项仅建议判断这一集中后的技术增量是否值得细化。

**历史K.43：第三组一页核心增量说明已完成（D58／E481），仍为候选。** [一页说明](research/第三组_核心增量说明.md)将拟自主工作收拢为方案相关状态／能量关系、重复与合法转换的持续充分分析、分析信息反馈离线候选规划。直接对照Jung、Dziurzanski、Wang，并补核已有Pourmohseni正文：后者已有热标签进入DSE，不将这一能力、DVFS或共同设计重称创新。热适用范围为证明材料，必须覆盖既定合法历史，不允许以收窄范围、在线拒绝或新增温限取得安全。沿用已有使用目标、执行／转换语义与基础设定；MILP合法结构和外部完整评价分工不冒称精确完整MILP。两个只读子任务复核未发现必要修正，非主线6独立审查。未发现新的已证接口失效，未选定主基座或恢复实现、实验；下一步仅审阅这项技术交付及工作量是否合适。

**历史K.42：第三组可复用模式／转换与前两组已同尺度比较（D57／E480）。** [对照表第8节](research/本地文献逐篇能力边界与基座筛选.md#三组基座比较)区分一批已知任务的一张安排与一组跨合法历史复用的模式方案。助手条件性建议：第一组是成本较稳的热节能技术基座，第三组更贴用户重视的上层问题组织；Jung提供模式／转换共同设计，Dziurzanski提供映射／P-state及候选协调，Wang仅提供单周期热闭合依据。Jung原法及Base已有共同设计／反馈；转换概率不是平均能量权重；单周期闭合不保证任意模式切换安全。非统一响应作为模式输入，持续保证与公平方法对照仍有实质工作。此为已有暂停问题族的比较，不是新方向或恢复执行；旧无额外收益不再承担立题门槛。未选择基座、改变基础设定、改正文／程序／参数或运行实验。下一项只建议讨论是否接受该问题层次，再收拢一页继承／修改范围，不自动重启旧实现。

**历史K.41：前两组基座的继承／修改及问题示例已并排比较（D56／E479）。** [对照表第7节](research/本地文献逐篇能力边界与基座筛选.md#两组基座比较)给出同例比较：第一组继承热DAG节能主干，第二组继承端侧配置与执行评价。助手建议Zhou作热节能主参考、Liu提供调度／MILP表达，PELSI提供画像与计量，HaX选择性提供层组／多请求关系；不是用户已选。明确Liu稳态MILP不等于完整瞬态热漏电MILP，PELSI已有整网联合选择，当前不继承HaX争用与非零转换，两入口也可能落到同一数学问题，不据此制造两项创新或新的上层场景。未改基础假设、正文、程序、参数或运行实验。下一项仅建议用户选定主基座后收拢一页继承／修改／方法分工。

**历史K.40：本地文献逐篇能力边界与基座筛选已完成（D55／E478）。** [对照表](research/本地文献逐篇能力边界与基座筛选.md)覆盖76个既有逐篇材料及3项证据目录补充，共79项；76份papers完整PDF均有对应，Lee同研究两版本合并、Wang作者稿补齐，未完成下载不计全文。31项定向回核正文，其余48项复核旧笔记／证据，阅读等级逐项注明。区分主问题基座、方法组件、物理数据和低相关材料；优先比较热DAG节能、端侧完整执行两组，多模式来源保留不恢复。纠正F-DTM／Maity已有画像、Kim已有NPU／DVFS、HaX累计起点、Chantem瞬态能力及ASPLOS2025已有分段响应＋温度功耗的边界。只提出继承／适配入口，不以缺项直接称创新，不选择新方向；下一项建议从筛选表选一个主基座，形成一页继承／修改／接口／验证表。没有改正文、程序、参数或运行实验。

**历史K.39：有文献基座的三个替代问题族已比较（D54／E477），均未选定。** 用户澄清现有“不同热历史共用模式方案”可作为基座，随后用Stage、任务相关响应与热状态建立模型／方法，不以额外收益立题。本轮另外比较Q1多速率数据链时效（Verucchi RTAS2020）、Q2时长不确定鲁棒规划（Lombardi TC2013）、Q3调度／调频／休眠共同规划（Esmaili ASP-DAC2019），见讨论稿第8节。已重读本地正文，列出可借方法／实验与所需基础调整；Q1偏应用叙述，Q3偏完整实现基座，Q2后置。三类不叠加，原模型保留，未运行实验或批准变更；下一项只建议用户选择一类继续对应核查。

**历史K.38：用户纠正研究主张，撤销将额外共同节能作为核心的D50取向（D53／E476）。** 优先借鉴成熟框架，形成有应用依据的共同设计问题，再组织模型、方法与同问题验证；降低能耗仍是目标，但不要求先证明共同规划优于独立选择才能立题。停止K.36的收益补证优先任务，不再将K.37的P1一页重述作为新入口；P2未获选择。HT-1／TP-1的无额外收益、真实违规和安全证书均按原范围保留，不据此否定整个方向，也不改称已有创新。当前物理、工作负载、执行规则、安全标准及历史结果不变；本轮只记录纠偏，未运行实验或选择新方向。下一项建议只核成熟框架中一个有应用理由的共同设计要求及其方法分工，具体对象待讨论。

**历史K.37完成两条共同决策入口比较（E475），均待用户选择。** [讨论稿第7节](research/多模式热状态与节能联合规划_方案讨论稿.md)优先建议P1：同一模式方案服务不同合法热历史，这是既有A.2的共享关系，不是新增机制；P2为跨模式共享部署，需要应用理由、调整A.1及另行确认。借师兄共享／局部决策组织，定向复核Jung§6.1、Kim驻留及Schmitz／Schor来源；不将拼接当创新。D50、现有模型及TP-1结束状态保持，方法仍暂缓，未运行实验。下一项仅建议P1一页具体闭环及接口核查，未自动开展。

**历史K.36共同收益条件审查完成（E474），保留D50，方法实现仍暂缓。** [讨论稿第6节](research/多模式热状态与节能联合规划_方案讨论稿.md#61-比较对象与收益条件)明确：安全替代组合的热历史优势须超过局部劣势，才有严格完整能量收益；非零交互不足。HT-1三替代均不满足，TP-1的b_n自身重复已违规，两组仍无额外共同节能依据。目标可分与安全集合可分、首安全回补与全域完整复核分别处理；不预设共同法能胜过同域完整最优。下一项仅建议从已有全文核一套匹配响应／漏电／热参数的资料，不拼造实测、不选新数值；该资料核查尚未开展。当前模型、安全标准、TP-1结束状态及D50核心期望不变；只作旧区间有理数减算及自核，零热、能耗、搜索调用，没有新增独立会话审查。

**历史K.35方案与贡献收拢完成，D50已确认先补共同收益依据（E473）。** [讨论稿开头](research/多模式热状态与节能联合规划_方案讨论稿.md:5)更新共同模型、评价认证与候选求解状态。HT-1／TP-1尚不支持额外共同节能，CP1不足以证明新模型方法优势；用户保留额外共同价值为核心，选择先审查针对性依据，暂缓方法实现／性能对照。下一项只核前序热历史何时改变有效选择、收益条件及匹配证据缺口，并保留简单复核／回补足够的范围。不改模型或安全标准、不选新参数、不运行实验、不恢复TP-1或通用认证器开发。本轮仅文档收拢与自核，没有新增独立会话审查。


**历史K.34已完成，主线6独立审查通过（E472）。** [综合结论](research/thermal_pressure_diagnostic/CONSOLIDATED_RESULT.md)：两组持续安全、两组真实违规；新旧五项身份一致，故可将a_n b_c新持续证书与旧U1能量组合，证明其为四套固定方案内唯一U1最优，约108.862367mJ；全CPU约113.821979mJ。两者差约4.959612mJ，不是共同规划收益。35项只读身份／区间核对通过，未重跑热、能耗或搜索；K.31原未决及K.33仅安全状态保留。有效局部偏好与完整评价相同，b_n自身重复已超温，完整局部算法对照仍缺。[独立审查](research/thermal_pressure_diagnostic/reviews/consolidation01.md)无必要修订，TP-1诊断链结束；下一项只建议收拢论文主张，不自动加参或返回搜索。

**历史K.33已完成，主线6复审及最终证书审查通过（E471）。** [阶段结论](research/thermal_pulse_certificate/STATUS.md)：原a_n b_c取得持续安全，CPU≤8405/206°C＜41°C、NPU≤9996419/125829°C＜79.445°C，覆盖原四入口、任意长期重复及全部合法实数切换。93/93预检、16/16事后核对通过；一次正式安全证书、零热传播／能耗重跑。首审版本绑定缺口已修订，审查／预检／输入／源码摘要及字节SHA封存匹配，一轮实质修订。保留入口与操作准备失败、旧盒未决及47项旧文件；K.31记录不改，不产生新U或最优排名。[主线6结果审查](research/thermal_pulse_certificate/reviews/result01.md)无必要修订。阶段结束；下一项建议只读收拢新安全依据与原四组合结论，不自动加参、运行或恢复搜索。

**历史K.32静态路线审查完成（E470）：有简单、可实现的a_n b_c持续安全论证，建议下一项限定实现。** [一页结论及核查推导](research/thermal_pressure_diagnostic/SUSTAINED_ROUTE.md)：原四入口块、任意长期驻留／重复及全部间隔≥40ms的实数切换时刻均覆盖；排空使各轮延迟≤3.75ms，NPU脉冲1ms、起点间隔≥16.25ms；CPU活动能量包络0.46875h＋0.025J，联合导热与漏电得CPU<41°C、NPU<79.445°C。有理数与指数级数界纸面闭合，不扩大50°C盒。新增工作仅前提核验、标量证书和持续接口；不开发状态空间验证器。未运行仿真或修改输入／程序；K.31运行未决保持原记录，本轮新增数学依据尚未接为程序证书／安全能量汇总，也不证明共同规划额外收益。唯一下一项建议实现此证书及必要预检，未自动开始。

**历史K.31已结束：TP-1一次诊断及独立审查完成（E469）。** [结果](research/thermal_pressure_diagnostic/RESULT.md)：全CPU组合持续安全U=113.821979mJ；两含b_n组合有真实违规，且B-only本身在21.25ms超温；a_n b_c两条有限路径安全、等权108.862367mJ，但当次持续安全未决，不能声明四点最优或共同规划收益。局部b_n参考违规，完整局部排名／回补次序未形成；可核归因不改变两有限安全组合的能量偏好。正式1次28调用均<20秒，合计133.736秒；预检28/28、事后71/71。两轮执行前修订保留，输入／服务／精度不变，不补跑或加参。[独立审查](research/thermal_pressure_diagnostic/reviews/result01.md)核对33工件、21来源、8表及142片段通过，唯一显示修订已采纳；本阶段结束，后续是否补持续证据另行讨论。

**历史K.30：完整路径、局部评分、显式入口反例及预算接线预检36/36通过（E468），[独立审查](research/thermal_pressure_wiring/reviews/review01.md)通过、无必要修订，本阶段结束。** [接线包](research/thermal_pressure_wiring/README.md)在独立小夹具核对完整能量／入口热历史归因、B入口、迟到反例保留及有效能量拒绝；不把证书未决或有限安全升级。新源码纳入身份，旧模块不改；未运行TP-1正式四组合或局部分数集合，参数／精度／20秒不变。下一项绑定一次性运行入口、顺序和结果汇总，准入核对后执行原定诊断，不增加参数或案例。

**历史K.29：相同TP-1模型、精度与20秒预算下，数值内核预检已形成可审查结果（E467）。** [实现说明](research/thermal_pressure_numerics/README.md)：温升坐标缩放＋有界状态转移矩阵端点传播，80ms耦合空闲约3.47/3.69秒完成；脉冲及工作点变化约3.11秒完成。保留仅缩放失败与错误断言记录；30/31运行检查加2/2只读断言纠正，不冒称全部重跑。[独立审查](research/thermal_pressure_numerics/reviews/review01.md)已通过，无必要修订，本阶段结束。未接正式四组合入口、无新U1或排名；下一项只做路径、评分、反例入口与预算分流接线预检，参数、精度及预算不变。

**历史K.28：TP-1参数已获用户确认，独立输入与必要预检已实施，正式诊断未准入（E466）。** [预检入口](research/thermal_pressure_precheck/README.md)：静态／状态检查73/73通过；全CPU取得持续证书，三含NPU组合仅证书未决。新细分包装解决旧积分步长边界异常，快单节点解析核对通过；80ms耦合空闲夹具在20秒内仅覆盖约28.855ms，保留未决与失败记录，不补跑。未运行正式四组合或能量排序。[独立审查](research/thermal_pressure_precheck/reviews/review01.md)已完成，无必要修订；本阶段结束。下一项只处理数值实现能力，保持输入、精度及预算不变。

**历史K.27具体L3压力草案已独立审查通过（E465），新数值待用户批准：** [TP-1](research/thermal_validation_design/THERMAL_PRESSURE_DRAFT.md)提出NPU活动3→1 W，NPU环境导热0.10→0.015 W/K、耦合0.02→0.005 W/K，NPU热容0.02→0.000020 J/K；CPU环境导热、CPU热容和全部服务／入口／温限／U1不变。四方案已明确并消除F1排空等待混杂，最大轮长和8.75ms。全CPU可用50°C盒持续认证；含NPU候选不能由现有共同矩形盒认证，只能找合法真实违规，否则未决，不能据此宣布全CPU最优。一次性组合压力条件，没有现实平台标定或单因素因果意义。审查无必要修订，零实验／代码／原输入改动；[审查](research/thermal_validation_design/reviews/pressure_review01.md)与[收尾](research/thermal_validation_design/reviews/pressure_adoption01.md)。物理变化显著，批准后才进入必要预检，不自动运行。

**当前K.26输入变更审查完成（E464）：** [具体参数／候选表](research/thermal_validation_design/PARAMETER_REVIEW.md)经独立技术核对通过，仅修正来源哈希漏字。给出全CPU-L／CPU-L+NPU四表，最大轮长和12.25ms≤14ms；片段集为3或6项，但原59°C盒仍认证全部热安全；F1还有2ms排空等待混杂。不建议运行该草案，未改输入／代码或开展新实验。尚未取得新物理数值匹配依据；下一项推荐明确L3热压力的预先构造原则，再提出数值，而非重复换原CP1候选。该新增条件仍未冻结，平台标定不自动成为必需前置。

**当前K.25已完成（E463）：** [条件审查结论](research/thermal_validation_design/RESULT.md)与独立复审通过，一轮实质修订、零实验／参数改动，k25续接已暂停。原CP1共同59°C盒低于80°C，延长运行不激活热约束；四固定组合即使逐候选生成现有笛卡尔积仍同集，基础证书不能判清时序差异。方案已补所需集合／提交集合／给定盒契约、真实反例与未决、简单回补公平比较。建议下一项只准备一套L3参数及使用条件变更表，并先核候选差异与认证能力；新增输入及检查器扩展未获批准，不自动运行实验。K.23保持原结论。

**K.23阶段完成（E462）：** 一次正式四组合诊断与独立审查已完成；63/63预检、76/76事后核对通过。4候选持续安全、8路径完整，逐模式／共同均唯一选a₁b₀，J=112.226939 mJ；R/g归因相容，Δ=−0.765479 μJ可分辨，但没有改选收益。见[结果入口](research/thermal_history_diagnostic/RESULT.md)及[独立审查](research/thermal_history_diagnostic/reviews/result_review01.md)。自动阶段仅两轮实质修订（准备失败状态、事后未决分流），失败和逐项采纳保留；模型、参数、工作负载、安全标准及旧代码／结果不变。主线 (7)统一提交／普通推送；完成即暂停k23续接，不自动开展下一目标。结论限四固定组合及声明U1，不按没有翻转否定整个方向，也不将非零交互当收益。

## 当前阶段目标与推进表（2026-10-06）

**最终目标：** 形成具有可说明的研究差异和自主贡献、范围可控且可实现的端侧推理温度感知节能调度方案，完成“具体问题—统一模型—MILP参照与启发式—公平实验”的硕士论文工作闭环。当前优先研究入口为多模式方案及转换条件的共同设计；基本执行规则已确认，具体输入与求解实现尚待落实。

**本阶段大目标：** 收敛一份约2—3页篇幅的论文方案，先由用户与助手讨论，尚未与导师交流。重点回答“我们与具体已有工作有何实质区别、这种区别为什么值得研究、拟形成什么贡献”。按用户要求采用总分结构、分点说明，并用同一例子贯穿问题、共同决策、实现与验证。文献用于定位差异、支撑设想和提供可用工具，不以介绍借鉴对象和成熟基座为主线；不以先证明旧方法失效或先做实验作为构想前提。

**2026-10-06用户纠偏：** 研究重心是自身问题与贡献。借鉴和基座的作用，是说明构想有事实与方法依据，不是最终汇报的主要内容。每个小目标既需澄清设定，也需说明这些设定对应哪些共同决策或保证范围，以及与具体近邻的相同和不同之处。预期贡献与已经证明的新颖性分开；已有技术可以继承，不要求从零发明全部工具。

| 小目标 | 唯一要解决的问题 | 主要依据与交付 | 完成标志 |
|---|---|---|---|
| S1：离线边界 | 我们准备共同规划哪些方案、输出哪些保证，与完整已知序列及运行时重新规划有何不同？ | 用双模式例子交代输入／输出／运行时职责，Jung§4—5用于核对定义和差异 | 确认离线含义、研究范围及对原已知请求假设的必要调整，不将离线本身当作创新 |
| S2：模式与转换语义 | 哪些前后联系需要共同决定，为什么各模式方案要关联？ | 形成最小模式图及执行规则表，对照Jung／Dziurzanski／Omni指出具体相同与不同关系 | 明确模式、转换、工作衔接与驻留条件，并能说明所研究的协调关系 |
| S3：热与节能评价 | 跨模式热状态如何参与节能决策，相比已核近邻增加或重组了什么问题？ | 一页评价契约及概念例子：入口状态、转换范围、实时／热约束、能耗口径与前后决策联系 | 形成有依据的差异及价值论证；未给定序列时不虚设总能量，不要求先做实验才允许构想 |
| S4：方案闭合 | 我们的实质研究工作及贡献候选是什么，怎样实现和验证？ | 合并S1—S3，按总分结构和贯穿例子组织；文献来源作为支撑 | 简短讨论稿已交付，先由用户审阅差异、价值、工作量和可行性，不预设导师认可 |

**本阶段推进规则：** 每轮只处理一项。讲解先回答本题拟研究的关系及其价值，再用具体原文解释差异、依据和适配选项，确认涉及基础设定的选择；例行核查自主完成。小目标结果在本状态表与已有笔记中累积，不为每项另增长报告。新材料只有直接影响当前小目标时才补读。当前按D35完成连续候选原型与预检，研究对照仍按后续小目标确认，不自行扩大范围或填定研究输入。

**K.23输入草案历史（已由上方E462更新）：** K.23／E460已落实E459的完整输入与对照要求。D37确认复用CP1物理／响应／两路径、30°C逐模式参考，接受选择不变；提出A的5／3.5 ms、B的3／2.5 ms四方案，转换处共同L/H、无旧工作和候选相关等待，最大跨模式轮长和8 ms。温差须实际传播，未手填。明确40／45 ms A前缀、40／35 ms B参考评分、80 ms完整J及热历史残差，预先保留并列集；45 ms前缀不是独立W1窗口。共同安全盒纸面可复用，尚无新绑定运行证据。下一项形成可复跑输入与预检任务，再一次关系诊断；本轮未改代码／输入或运行实验，不以翻转为通过条件。

**K.20复审补充（主线（6），2026-10-08，E455）：** 配对的独立预算、共同签名归因与区间判据合理，但CP1对三代表有更强的限制：每模式单出口、共同期限D=14 ms时，C_M=(C_E+D)/2，C_L=D；故M的跨模式轮长和为D+(C_A^E+C_B^E)/2>D，L则为2D，任意合法结构的M/L均不能通过现有转换期限证书。CP1选项还保证C_A^E≥3、C_B^E≥2 ms，因此40 ms旧轮、41 ms转换已能对全部M给出至少1.5 ms的实际超期。并非仅前4结构碰巧失败。E-only／EML在CP1只能作实现回归及额外评价成本记录，不能检验安全M/L节能潜力；无需调参找正例。建议收紧K.20判定范围后，若需验收E-only可只配对一次并结束，不据此将E-only推广为一般模型下无损时序策略。没有执行对照、改变参数或确认新方法选择。

**K.21独立复审（主线（6），2026-10-08，E457）：** 本轮未发现阻断推进的问题。静态核对新增入口、隔离方法与计费包装；新包130/130、旧包354/354工件哈希及14项当前依赖匹配。独立有理数检查16张保存表的轮内合法性；共同4结构的E表、状态和安全能量区间相同，保存预检31/31、事后复核70/70属实。未重跑MILP或热评价。两法均因4结构上限停止，尚未证明最优；CP1热筛选不活跃、M/L必然超期，故只支持E-only实现回归与本次额外评价成本记录。此项可结束；下一步先定义跨模式共同规划要验证的具体关系及区分条件，不追加CP1运行、不据此确认一般E-only无损或修改基础假设。

**K.22独立复审（主线（6），2026-10-08，E459）：** 仿射入口能量及2×2交互关系与当前线性漏电代码一致，未发现阻断输入草案的数学问题；本轮未运行实验。先核安全方案间能量关系符合D36，不取消持续温限。下一份草案需一起落实：A的合法前序实际产生不同温度且对齐转换时刻／非温度状态；逐模式参考入口、评价长度及并列处理；四组合的完整能量与共同安全范围。联合四点最小值不高于其中的独立选择只是集合关系，本身不证明热历史价值；需报告实际改选、严格完整能量差及温度归因。条件翻转不是必须通过的门槛，不新增模型因素或反复调参找优势。

### 当前预检简化与能力覆盖台账（主线（6）审查，2026-10-07，E438）

用户允许简化后的小型预检，要求记录简化以防偏移。本表只追踪实现／验证缺口；基础模型仍查[86号](research/86_实验基础模型与假设确认总表.md)，多模式范围按D01—D30及后续变更。审查基线：`0755146`、V1 run05、V2 run02；本轮读取源码与结果并核对四个源码／依赖哈希，未重跑评价器。

| ID／类别 | 当前简化或未完成能力 | 不能据此改变的范围／补齐触发条件 |
|---|---|---|
| S01 测试缩小：平台 | B1/B2/B4为1个CPU执行单元＋1个NPU，B3为单CPU热部件；无GPU主夹具。V1有多CPU同域派生检查；V2同频派生例是CPU/NPU人工共享域 | 研究平台仍为多个固定CPU单元、设备级GPU/NPU；单元不自动等于物理单核。正式平台对照前补多CPU、多域、GPU/NPU、替代映射与耦合计量预检；不能改标签便称完整平台已验证 |
| S02 测试缩小：任务／响应 | 两模式、每轮两Stage链（B3单Stage），固定映射／工作点／偏移；时长、功率为L3常量，未比较同一Stage的跨频档／设备候选 | 不把一般模型限为两模式、两Stage或链。非统一1/f可通过参数表表达，当前未检验其选择影响；接规划器／正式实验前核DAG、轮内并发、候选模式与来源 |
| S03 首版接口：期限 | 每轮只有一个共同期限，request_id为轮级实例；B1用14 ms，B2保留原12 ms | D28仅允许首版预检简化，不替代一般逐请求期限；使用不同请求期限前增加归属、完成点及判定。不同期限夹具不能拼成同一方案的证据 |
| S04 首版接口：计量 | 每计量单元对应一个热节点，独立基准；确定性耦合RC与线性温度漏电。V2代码已纳入共享域空闲单元同步换点 | R86允许计量组与热节点不一一对应；共享频率不等于基准重复按单元计。共享基准／额外热节点需扩展去重与注热映射；完整平台覆盖仍缺。固定RC／线性漏电本身为既有模型假设 |
| S05 首版接口：入口 | 零周期相位、零切换年龄、无旧工作／待处理转换、即将首轮释放；给定温度盒及离散状态块 | 限制初始状态，不限制运行后合法切换相位／次数／驻留长度。声明任意运行中入口安全前需扩展；U1入口不能默认等于安全入口，组合时核包含关系 |
| S06 方法限制：证书 | 验证给定共同温度盒和期限充分条件；保守片段集合包含不可达组合，不自动寻找盒，未做顺序／相位精细闭合 | 通过可认证；失败无反例则未决。共同盒丢失部分时序信息，不证明精细时序收益；新方案证书不足时再讨论合成／精细层，不自动扩成当前必做项 |
| S07 方法限制：反例 | 只重放输入提供的有限过程；witness_trace当前从第一个入口块构造见证，不主动搜索 | 一个合法反例足以否定方案，没有发现不等于安全。若要指定其他入口或自动搜反例须扩展。安全证书核全部入口块，与此重放限制分开 |
| S08 数据与计费 | RC、温限、初温、期限、权重为L3；V1两路径等权仅核算术，V2不优化能量；60 s／30 s为诊断限额 | 不是实机收益、代表应用或公平方法对照。正式比较前统一输入、方案、路径与预算并落实来源；不能把诊断耗时当算法加速 |
| S09 方法限制：连续时序有限取样（2026-10-08，E449；E453更新实现状态） | K.17每个全模式“选项＋冲突方向”结构最多尝试全体最早／中点／最晚三张表，随后查询去重；K.19已实现并完成CP1运行期预检。活动能量引导结构，热／真实能耗用于评价接纳与比较，不定向产生新时序 | 一般连续时间域不变，但首版搜索不覆盖域内所有时序；串行链的三代表可仅为整链平移，遗漏Stage间等待；全模式三代表也不等于逐模式三代表的全部组合。未查时序记覆盖未决，不能据代表失败否定结构或以无收益否定时序价值；不称完整连续MILP或已有热反馈修复 |
| S10 诊断输入：CP1热筛选不活跃（2026-10-08，E451；E453更新实现状态） | K.18的[25,59]²共同盒对完整合法选项的8片段超集满足向内条件；在声明入口及物理模型下覆盖所有合法候选的热轨迹。K.19已接入运行期检查；M/L表被拒的依据是转换后期限，非热违规 | 可核热认证接线、能量计算及状态分流，不能验证热约束改变选配／时序的效果。窄盒失败仅核证明未决，B3复用仅核独立热违规分类。正式研究验证时另行明确有区分力的任务，本轮不调参制造热瓶颈；温度漏电对能量的影响仍保留 |

**原型复审更新（2026-10-08，主线（6），E453）：** 审查66503f9；354/354工件哈希匹配，precheck05／prototype02／postcheck01各13项当前源码与快照一致。保存的76/76和49/49记录属实，本轮未重跑求解／热评价；另独立核12表的输入区间合法性、安全U来源和预算内提交时刻，均一致。未发现阻断下一份对照协议的新增逻辑错误。S02在CP1已扩至两模式各3Stage分叉汇合及14行合法响应，替代映射／频率有编码预检；S01多CPU仅调度编码探针、GPU及完整多CPU热评价仍缺。S09/S10仅更新实现状态，不删除取样与热筛选不活跃的限制。4结构全CPU-L、4张E安全和8张M/L期限违规只支持原型接通，不构成联合规划的节能收益证据。

**已确认范围选择，不是待自动补回的遗漏：** 固定Stage、不抢占／执行中迁移或改频，固定CPU单元与加速器设备级独占，域空后切频与空闲保持；确定响应、忽略并发干扰及pair残差；不跨轮／跨模式重叠、T1、D≤P≤L及首版Z0。这些查R86与D03—D04、D13、D23、D25、D28；实际应用不满足时先讨论，不自行降低服务要求或换模型。R86原有限已知过程／窗口安全已由D02、D08调整，不得只看旧表恢复旧范围。

**本次结论及下一步核对点：** V2 run02保存48/48通过，当前源码／V1依赖与记录一致；基础证书与反例／未决分流与说明相符，不是完整平台或优化算法验收。下一步组合V1/V2，必须绑定同一平台、任务、方案、服务参数、执行规则与物理参数，另核U1入口／过程在安全保证范围内。不能直接把12 ms方案的V1结果与14 ms方案的B1证书拼接；采用14 ms测试方案时应从同一份明确的新输入调用两侧，保留旧记录。此为下步接口要求，组合代码尚未实现，不记作已发生错误。

**维护：** 能力补齐时按ID登记实现、检查及版本，标已覆盖／部分覆盖／未覆盖，不因程序能读字段便删除缺口。研究假设调整另记选择；本台账不授权扩实验或改另一会话程序。

**整合更新（E439）：** S03的12／14 ms错配拒绝、S05的U1入口／过程包含关系及S08的证据与能耗分列已作整合预检（69/69）；不代表这些行的不同期限、多状态入口或真实数据缺口已经补齐。S01、S02、S04、S06、S07范围不变。

**独立复审（2026-10-08，主线（6），E440）：** 审查`63717a8`，联合包20/20工件哈希一致，保存的69/69检查通过；未重跑整包。定向中断探针发现：J12在V2的`witness_committed`之后预算到期，内层保留`violation`及真实反例，联合入口却在`safety_returned`检查时退出，返回`unresolved`且`safety_receipt=null`。需保留内层预算内已提交的违规证据，同时继续禁止预算外新联合能量；补内层返回边界回归，V1的`path_returned`同类位置一并核查。此问题不推翻正常完成的五组结果，也不导致误报安全。可继续讨论规划变量，但整合中断验收尚有这一项待修；S01—S08未因接口整合而扩大覆盖。

**修复复核（2026-10-08，主线（6），E442）：** 审查`ea25296`，独立重做原J12内层反例提交后到期、J14安全结果迟返回、J12_late有限路径超期后迟返回三项探针：违规及1 ms超期见证保留，迟返回安全结果不接纳，均不补联合能量。51/51工件哈希及六项当前源码／快照一致；run03保存81/81通过，五组常规状态和能量区间与run01一致。本轮未重跑81项整包。E440所指返回边界问题关闭；本次审查未发现新增阻断项，S01—S08及尚无优化器的范围保持。

**规划讨论复审（2026-10-08，主线（6），E444）：** K.14／D33与既定范围相容，未发现本次新增的逻辑阻断；活动能量下界仅在文中非负剩余功率、固定释放及完整工作覆盖条件下成立。下一份输入契约须区分共同问题输入、候选Π与安全证明辅助材料：换候选需重核工作／空闲片段覆盖，给定证书盒失败仍是未决，不能把盒当成新增物理温限。MILP候选排序量不代替真实U1目标；同活动能量的不同时间安排仍可能有不同总能耗，后续须说明继续搜索／停止规则。本轮仅静态与代数审查，不要求立即实现精细分析，不修改代码、参数或S01—S08范围。

**连续候选原型更新（2026-10-08，K.19／E452）：** S02已在CP1核两模式各3Stage分叉汇合DAG、14行跨设备／工作点选项和轮内并发；S09三代表协议已实现，有限覆盖限制不变。S01共享域和双CPU仅增加调度矩阵探针，S04仍为原计量接口；S03共同轮级期限、S05入口、S06给定盒、S07给定反例、S08诊断数据均保持。S10运行结果确认本包热筛选不活跃。76项运行预检、49项事后核对不等于这些一般平台及研究效果缺口已补齐。原型正式结果入口为research/continuous_planner/results/prototype02/search.json；未新增用户基础假设选择。

### 选择路径与变更记录（唯一维护入口）

**D161（2026-10-20，用户“继续”）：** 确认K136建议的单一两遍生命周期实现与必要小域／mock预检，未授权本轮原规模求解。助手复用旧N1生命周期接缝，独立新入口仅第二遍采用既有增广运输；原默认顺序和协议回归保持，完整账本原子提交，余量不足时按R/k分片，实际底层worker状态及失败锁存控制续接。01通过后因R/k分支未被激活，只补测试子例并以新02保存最终99/99，不改生产／参数或原记录。关联E582；下一次质量验证另行冻结，不能将mock改善或回声闭环当研究收益。

**D181（2026-10-21，用户确认修复后仅续接37槽）：** 用户授权先修复账本写入及异常终态，通过必要预检并冻结协议后继续原未运行37次；前三次不重跑，各300秒，模型／参数／热安全不变、不延预算。采用隔离p0_resume执行层，原197源及K155证据／claims只读；新203绑定、精确原第4—40槽及总40／12000方法秒。沿原K155启动＋19200秒绝对日历截止，诊断／准备暂停也计入，不重新领取5小时20分。1秒有限原子替换、compact监督、方法回执先落盘、双独立终态与失败停止经167项纯预检；无研究调用。只有本次续接可消费新globalclaim，不恢复旧root、不重算前三次post、不借其候选。执行仍保留无收益／超时／未决并按原科学接口接纳；关联D180、E601。

**D180（2026-10-21，用户确认P0真实执行预算）：** 用户明确确认R1—R5共40次、每次300秒，要求先冻结／预检再执行，模型、参数及热安全不变，不补跑、不延长。助手固定K154原40槽／方法顺序及输入，不启动其他批；采用已提出的19200秒日历上限与独立60秒post预留，搜索证据仍只计300秒。真实一次性global／slot／post claim及账本前缀、故障停止、迟到拒收、完整U优先落盘和仅终止所属进程树已实现；163项纯检查通过。首轮4项沙箱临时目录错误留存，另在启动前核查中修正原方法自行创建目录的接口，均无研究调用。绑定197源后执行；结果不要求联动获胜或反馈触发。旧K154准备仍保留未授权历史，新授权仅由K155声明承接，不修改旧claim。关联D179、E600。

**D180执行回填（同轮，未改变用户选择）：** 163项预检与b419305冻结推送后真实启动。前2次及post完成；第3次HEFT原方法正常返回、核查记录形成后，ledger.pending→ledger原子替换WinError5，监督以1退出，消费3／900预留秒，37未启动。按冻结故障停止规则没有继续或补跑。仅对已成HEFT安排执行原定尚未开始的单次post，SAFE；未重算搜索或补记U。27项存档核对保留原账本／临时账本／153工件及197源，原RUNNING仅作为崩溃历史，由派生终态说明真实停止。独立小文件8项核查验证有界IO重试候选，未接入旧冻结；无新研究调用。关联E600执行补充，下一步只建议修复执行层及核查剩余槽的分段继续协议。

承接D178的P0准备）：** 用户“继续”授权准备R1—R5多问题入口及必要预检，本轮不据此推定40槽研究预算已获确认。采用隔离子目录保留178份旧源码，只参数化输入编号和两处存档回执的编号判断；派生函数逐项绑定原文及替换。139项预检／20项存档核对通过，40槽顺序、300秒拟议限额、五输入／191快照冻结，研究消费0。真实执行总控、claim和总墙钟机制留待具体预算确认后的启动冻结，不称已完成真实批量验收。保留用户先前确认的无NPU两档联动后置；R1不借先导结果。涉及新增条件、样本、方法、参数或预算变化时另版讨论；关联D178、E599。

**D178（2026-10-21，用户要求回到第三章正式实验安排）：** 用户明确先整理各组顺序、调用次数与预算，不直接启动115次，并保留当前模型和预消元联动版。本轮仅读旧配置／协议／结果及入口，整理新计划，0研究调用／构模／热计算、不改正文或方法。核到当前共享A.main=NPU0与两档无NPU资源不相容后，用户通过选择题确认“先后置两档的联动对照，保持当前版本（推荐）”；因此10个联动槽记后置、不消费、不当失败，A部署不改。P0 40槽、每次300秒、SA101—105、轮换方法块、额外时间预留及750槽全范围量级均为助手提案，未冒称获执行授权。K152单列先导；正式重复若未来获授权须事前声明并计新预算，不复用旧claim。涉及两档资源适配、请求／场景开放范围、版本、样本或预算改变时再讨论并另版记录。关联D177、E598。

**D177（2026-10-21，用户保留预消元版并授权最小同轮四方法）：** 用户明确整体MILP、预消元联动版、HEFT及SA101各一次300秒，先冻结协议／必要预检，原基准／参数／合法调度域／热安全标准不变，不补跑、不延时。助手沿用174份方法源码，只增四份执行／纯审计及测试文件；95项必要mock／存档检查通过，前两轮夹具失败留存，178源及输入／规则已冻结。四方法独立初始化，整体与启发式保留各自设备选择，联动保留4开2闭及本次种子设备限制；SA101仅探索。新配额4次／1200预留秒，1800秒外部监督仅包容清理／记录，不延长方法证据门。正常截止经因果和隔离核实后继续；未解释故障停止后续。事后全窗复核只验证原SAFE，不生成预算内新U。不恢复115次、温限扫描或自动外审。关联D176、E597。

**D176（2026-10-21，用户授权K151质量配对）：** 用户在K150“旧4开与预消元版各一次300秒，比较完整安全能量、首次改善和根LP”建议后明确回复“进行”。本轮仅2次／600研究秒，参数、4开2闭及安全门不变，独立初始化，不补跑、不延时。允许执行所需的最小包装、必要预检及结果核对；助手处理已确认的后审计截止误分类时保留冻结源和旧账本，仅追加校正并消费未开始的一次，不重跑旧方法。两份调用已用完；后续四法、批量或新邻域未由本记录自动获授权。关联D175；K151本次质量改善不扩成普遍排名。

**D175（2026-10-21，用户继续，按K149所列下一步实施）：** 用户在固定锚提案后回复“继续吧”，本轮据此限定为实现及必要正确性预检。助手保持4开2闭及全部原参数／安全门，选择默认关闭、只在第二遍显式开启的原约束预消元；用户未新增研究求解预算，原基准不补跑。已实现与已预检不等于已有质量收益；下一项质量配对须另行冻结。若需额外删合法安排、改输入／物理／安全标准或扩邻域，先讨论。关联D174，不覆盖其只读阶段结果。

**D174（2026-10-21，用户确认保留4开2闭并授权分析）：** 用户明确“先保留4开2闭，继续分析根LP和整数候选生成的瓶颈，提出一项针对性的改进”，原参数和热安全标准不变、先不补跑。助手本轮选用只读存档／源码分析与精确静态计数，提出固定锚约束预消元；实现、正确性预检与性能配对分别待后续安排，不能由本记录自行启动。D173两次旧配额已消费，不复用；自动外审仍按D172暂停。若改动需额外限制合法安排、改变部署／参数或安全门，先讨论。

**D173（2026-10-21，用户直接授权5开1闭配对）：** 用户“可以，你就按照你说的开始做实验吧”确认此前唯一建议。范围为最小包装／预检及原完整基准旧联动→5开1闭各一次独立300秒；5开只释放第二遍本地main，不动设备、物理参数、合法起点或安全门。每方从自身fresh seed开始，闭post取自身第一遍最后完整SAFE，禁止历史／跨方免费候选。一次配对后结束，无改善也保留。D172人工交接继续有效，D171旧夜间预算及自动闸门未重新启用；后续若改变物理模型、部署域或增加调用需另讨论。

**D173执行结果附记：** K148两次配额已消费，旧版更低；发生一次包装误报，按有据恢复记录只执行未开始的新方法。算法、参数、合法域与安全门未改，原误报与旧claim保留。当前保留4开2闭及下一项结构分析均为助手建议，不冒充用户再次选型或新增求解授权。

**D172（2026-10-21，用户恢复人工转述审查）：** 用户称自动审查先不弄，由本人转述意见。停止将自动交接作为当前推进方式；保留协议、验证、失败和监测归档，真实自动开关不启用。人工讨论／后续任务按用户直接授权开展，不代写外部reviews，不把旧夜间配额延续至新任务。当前仅核对和汇报已有进展，未授权实施5开1闭或新求解；自动化以后需用户重新明确启用。

**D171（2026-10-20，用户授权外部审查交接，后续追加有界科研）：** 原始请求只建协议／闸门／TEST_ONLY模拟，不得代替原ChatGPT审查方。用户确认审查任务每小时启用、身份YBEMR；先选验收后预算，随后明确授权验收后2轮／2次×300秒／600研究秒／总墙钟2小时／北京时间2026-10-21 07:00止，失败或无改善阈值1，不补跑。以后者新增记录为准，不继承旧6小时8次，也不把预算当逐项批准。执行端采用独立签名与仓库外配置锚，但真实来源／写回／受控执行链未验证，所以继续关闭；同账号只提供软件协议，不能宣称不可绕过。初始交接仅K146已有报告＋下一项只读审查提案，不将5开1闭补成已获实施许可。关联E592；重新启用须所有缺失前提完成且尚有本次剩余预算／有效期。

**D170（2026-10-20，用户授权已有方案差异分析）：** 只比较K142联动与K145 HEFT的部署、工作点、时序及能量组成，分析后再确定改进；不补跑、不改参数／生产方法。助手核条件成员、已有日志、K135／138全开历史与K140固定设备正例，关联E591。推荐仅下一项纸面审查5开1闭替换4开2闭的覆盖与成本，尚未由用户确认实施或执行；不把建议补为既定规则，不增加阶段或总预算，不把跨批次差距当新方法收益。

**D169（2026-10-20，用户明确授权冻结两方法执行）：** 接受K144独立协议，HEFT→SA101各一次300秒，保持原参数、完整合法安排和连续热标准，不补跑、不延时；完成后统一复核。实际消费2，HEFT正常完成、SA正常截止且末评估未决，旧完整SAFE保留；165源及K142原账本不改，关联E590。助手建议下一项仅已存联动／HEFT方案差异分析，尚未授权新方法改动或求解；单种子和不同批次不能升级为稳定四法排名。

**D168（2026-10-20，用户“继续”）：** 确认K143下一项最小分类／计时接入和离线预检，本轮不研究求解。助手仅新增6源（165总／159继承），不改原策略、物理、热标准或旧MILP运输；把完整回执门与正常／故障分类接入新独立HEFT／SA包装，22＋19＋22共63项通过。未知输入截止与明确身份错分开；01旧61凭据保留，02当前准入。原K142重放10项只检既成数据，不给搜索旧答案。关联E589；新独立两法已准备0消费，实际执行需另行明确授权；不把新source集合宣称旧整包重跑，不自动恢复四法同轮或115次。

**D167（2026-10-20，用户赞成仅离线审查预算结束分类）：** 确认正常总截止未完成末候选复核时，应保留此前独立有效的完整SAFE，末请求未决，不轻易把方法写作技术失败；真实数值／身份／传输／清理故障仍单列。K142原标签与消费记录不回写，新增离线解释关联D166及E588。用户要求后续正式实验单列MATLAB启动、阶段实际预算、首严格改善；助手将其写入独立HEFT／SA协议，各一次300秒／种子101，不拼K142与历史为完整四法同轮。本轮只审查、纯数据检查和准备协议，未授权或执行新研究调用，未改运行包装；新包装及准入需另落实，不自动恢复115次。

**D166（2026-10-20，用户明确授权冻结四方法各一次300秒）：** 执行顺序、原参数、合法域、热标准、独立初始化与无补跑／延时边界沿K141，不按结果修改策略。实际2次后联动在截止接纳／归档未完成，按事前技术阻断规则停止HEFT／SA；两个已成完整SAFE保留，未运行不等于方法失败。助手建议下一项仅厘清预算未决与真正数值／传输故障分类并补离线预检，尚未获新研究调用授权；不把建议写成已实现修复。关联E587，K141准备记录原样保留，若要改变停止规则应单独登记，不能事后追补此次对照。

**D165（2026-10-20，用户“可以，你继续吧”）：** 确认K140后返回第三章最小公平对照准备，先核四方法接口与当前凭据，不在本轮运行研究。助手沿既有300秒与SA101探索口径制定整体→联动→HEFT→SA101单次清单，保留三个参照的部署自由度、独立初始化及完整连续热接纳，不为对齐联动子域削弱基线。公共代码加载等外部成本单列，方法内全部工作仍计费。冻结159源／输入并通过25mock及24独审；关联E586。实际执行为下一阶段，出现故障停止，不从本次准备自动扩大为115次、温度扫描或新算法；如模型／安全／输入需变更，重新讨论。

**D164（2026-10-20，用户“继续”）：** 承接K139提出的唯一下一项，冻结并执行旧N1→联动版各一次300秒原基准质量配对。保持原参数／auto-L／完整连续安全、固定全部设备，第二遍只开A整链＋local.pre并保留第一遍后缀；每方法独立fresh输入、seed、worker及缓存，不注入历史答案。允许必要包装和mock门，不改155继承源，不补跑、延时或新热条件。最终新增阶段取得严格完整节能，计算成本增加；关联E585。本轮调用结束；若后续主方法或公平对照需改合法域／安全／参数，重新讨论，不从本次正例自动扩大实验。

**D163（2026-10-20，用户“行，那你推进下一个小目标吧”）：** 确认单一联动邻域的设计、实现和必要预检，未授权本轮原基准求解。助手据约束确定AB／AC各开A整链＋本地pre，后缀闭合到本次第一阶段末完整SAFE；原fresh种子只固定设备，A共享unit与场景内OPP／时序分层。仅新增该块与协议分派，不追加多个邻域／切换规则。01 guard误拦保留，最小修正后02为66/66；静态计数与活动项机会不当SAFE或性能结论。关联E584；下一次原基准质量调用另行冻结，若该块需近乎全开放或实际无收益，再集中审查，不自动扩块／加阶段／加预算。

**D162（2026-10-20，用户明确授权质量配对）：** 确认原基准旧N1与两阶段版本各一次300秒，参数与热安全不改，记录两阶段各自能量／成本，不补跑或延长。按旧→新独立fresh执行完2次；新版第二阶段0完整U更新，最终对旧微差全部由第一阶段产生。采用完整区间严格比较及阶段归因，保留第二阶段无收益、启动成本差和中间／终态日志差异；不以形式上严格低于旧值替代实用改善。关联E583，研究调用已结束；任何新研究求解、模型／参数或范围调整另定任务，115次与温度扫描暂停。

**D160（2026-10-20，用户“按照你的思路来吧”）：** 确认D159后一项只读集中分析：核K135候选、模型结构、原生事件和预算组织，提出一项修订，不新增研究调用或改参数。助手建议“同一调用旧N1→全Stage两遍，保留自身完整SAFE并使用剩余总预算”，不把分析授权写成已实现或已冻结实验。原D159结果保留，新版无质量收益不回写。由于旧新候选出现在48.920／60.288秒，不采用无依据的60秒等分；第二遍片额仅建议，实施与实验须分别验收。域包含不保证性能，关联E581；若结构衔接成本或小域正确性不适合，集中说明后收缩，不自动加阶段、换模型或扫描。

**D159（2026-10-20，用户“继续吧”）：** 承接D158下一项，助手冻结原基准旧N1→新增广版本各一次300秒质量配对，scene60秒为合作式，不延时、不补跑、不改参数／合法域／热标准。两方fresh输入／种子与缓存独立，变换与原行检查计费；新wrapper19项与原方法60项分开准入。两个调用已消费、技术正常但新版只有种子，接受无质量改善，不转而寻找有利温限。关联E580；下一阶段只读集中方法分析是建议，未在本轮改算法或追加调用，已有SAFE／失败／分析更正均保留。

**D158（2026-10-20，用户“继续”）：** 承接D157建议，完成新版final／callback／动态反馈集成及必要小域检查，不授权本阶段原规模研究调用。助手选择独立入口保持旧方法，因真实小域非无损右端，将唯一表达适配为“逐行无损改写＋其余原式保留”；代数投影不变，非物理／工作负载／合法选择／标准不变，无需新增物理假设。142源冻结下60/60通过，旧入口及138源保持，零原生／研究调用。关联E579；下一次300秒质量配对为沿既有公平规则的建议，尚未启动，不把回声正确性或历史技术PASS当节能资格。

**D157（2026-10-20，用户“继续吧”）：** 承接D156唯一原生接纳建议，助手冻结180秒完整进程、135秒工作证据、原生MaxTime至多60秒和唯一worker／请求。仅使用存档AB、原x0与唯一已核增广表达，原输入、目标、容差与完整SAFE保持；离线检查及独审后只运行一次。数值门通过、总87.034秒守限，但实际原生62.960秒超过60秒2.960秒，保留偏差不补跑、不把raw PASS当全时间资格。未改生产、热重算或取得新U；关联E578。后续完整方法集成及新质量协议仍是下一阶段建议，不由本次同点技术结果代替。

**D156（2026-10-20，用户“继续下一步”）：** 承接D155的数值表达定位，助手事前冻结零优化器／MATLAB／候选热评价及至多一次120秒同AB技术重建。原条件token仅历史身份重放，独立技术时钟约束，不生成新SAFE／方法凭据。全部8数组相同后使用行标签；阶段内选择拒绝不精确全局取补，保留局部增广补变量为唯一助手推荐，离线原型通过但未接生产或原生运行。原参数／合法安排／安全与K131证据保持；接受精确投影与浮点接纳域不同的限制，未来须阻断原行复核失败。关联E577；一次180秒技术接纳是下一阶段建议，非本轮已执行事实，不升级为质量对照授权。

**D155（2026-10-20，用户在K130排故验收后“继续吧”）：** 承接D153／D154既定新版质量验证，助手按原配对规则另行冻结两次独立300秒调用；同一approved_host上下文、fresh输入／种子／缓存，首要标准仍是新版完整SAFE包络上端低于本次旧N1下端。两次已消费，不重开K129失败账本；新版数值接纳与原生exit−2冲突即停止，余量不补搜索。共享A具体unit与场景OPP／起点仍分层，未改变物理／安全假设。现有SAFE保留，策略质量未判；先只读核现存载荷，再讨论必要修复，不以不利结果调参或加调用。关联E576；重新运行须新阶段明确协议。

**D154（2026-10-20，用户“先排除故障吧”）：** 用户授权先修运行问题，不运行研究求解。助手在阶段内选择不存在文件读取／原子发布及无求解MATLAB握手，按真实新证据补同Python顺序生命周期与受影响复测；全部事前声明技术上限、首错即停，原记录不覆盖。已核沙箱清理权限限制、强制退出码误判与父子退出确认竞态，选择本次所属进程身份核验和原40秒内有界确认；普通文件分析不升级权限，MATLAB生命周期用获批host上下文，不修改全局配置。最终129回归与两会话真实验收通过；这是实现选择，不是新物理／安全假设。原Errno22根因未证，若再现或所属身份未决，保留原始证据并停止受影响调用。关联D153／E575；本轮不启动新版质量比较。

**D153（2026-10-20，用户支持同预算严格节能标准后“那你继续推进吧”）：** 接受沿D152推荐实现固定本次新种子全部设备、开放各scene全部Stage OPP／起点的独立版本；跨场景A具体unit不在本次重选。助手在授权范围内冻结旧N1／新版各一次300秒、scene60秒、Cut10／CDF off的有限比较；首要成功为新SAFE上端低于旧N1下端，HEFT只作历史事后质量参考。原参数、完整物理／安全标准、合法域保持，不新增温度条件或算法组件。预检通过后两调用均已消费，新版技术失败不补跑，保留原132源／错误；故障修复只做必要预检，不将新凭据升级旧调用。首要质量标准尚未验证；后续若需要改变设备范围、配额、初始化、物理或安全条件须另行明确，不能因本次失败自行扩大。关联D152、E574。

**D152（2026-10-20，用户“那你继续下一步吧”）：** 接受先进行HEFT—N1方法集中分析，分开跨场景共享A具体部署与场景内A工作点／时序，不启动115次或温度扫描。助手据现有结果、约束和代码提出固定全部设备、开放全Stage OPP／起点的首版修订；这是待确认建议，不补写为用户已同意其实现或预算。纯存档代数确认现N1活动项已达独立最低；新活动项机会不保证期限／热可行或总能量收益。无新研究调用，旧K127保持。E573。

**D151（2026-10-19，用户夜间有边界授权）：** 明确允许K126后自主完成热证据设计、最多2组热条件／4次配对及可行时四方法最小比较；每方法≤300秒、合计≤8次、全夜≤6小时且最迟次日07:00。以先到的04:50:19截止执行；不改物理／工作负载／安全、不借旧见证、不补失败调用、不调参找胜利。助手事前冻结1组52°C及6项调用，必要适配／预检后全部执行，方法合1385.875秒、0技术阻断；0反馈及HEFT本次优于N1均原样保留。6份全窗SAFE，独立最优未证，未用余下2次；本阶段结束。后续候选覆盖修订仅建议，待讨论，不自动展开。见K.127／E572。

**D150（2026-10-19，用户“开始吧”）：** 确认K125提出的一次原基准N1质量诊断：总300秒、每scene60秒合作片，原共享A与参数／安全不变，CDF off／Cut10，仅本地main＋post开放。运行前冻结54源、原输入和明确Stage实例ID，消费唯一claim；一次正常完成，无重试／延时。相对本次新SAFE种子严格降低10.9119%，2个新安排；0热违规／反馈，局部界不升级全域，最优未证。结果只作为本模型及N1下的单次质量证据，不拿旧初始化作control。后续热约束／反馈协议是助手建议，尚未冻结或执行，见K.126／E571。

**D149（2026-10-19，用户“继续吧”）：** 承接K124唯一下一项，授权接通N1方法级生命周期与必要端到端预检，不含原基准或正式比较。实际采用既有确定性构造器在只过滤共享部署设备的完整视图上生成本次候选，原输入全部SAFE后才建立N1；构造器调用组织可能改变旧partial种子，故只对本次初始化归因。模型视图供x0／反馈，原输入复核及原聚合供全U，局部界不升级；截止保留已成SAFE、违规和L₀。最终45项及真实小域检查通过；研究输入／物理／安全不变。下一项一次原基准质量诊断的具体预算和调用协议仍待确定，见K.125／E570。

**D148（2026-10-19，用户“可以继续下一步”）：** 确认按K123推荐实现N1条件接口及必要小域校验，不包含原基准求解或研究调用。采用完整原输入／同Budget完整SAFE种子回执，设备全固定、开放本地Stage的原OPP／起点，其余精确固定；条件与共享部署分开，不扩大一般跨场景共用范围。实际默认None不变，候选仍回原输入复核，原回执不改写。一次43项检查及默认旧源码身份、真实小域闭环通过；物理参数、研究输入和历史结果未改。仅实现接口，未运行方法搜索或证明节能；下一项方法生命周期及研究预算／调用仍待后续。详见K.124／E569。

**D147（2026-10-19，用户要求审查最新提交建议并推进下一步）：** 审查f60469d后执行K122已提议的只读能耗／时序盘点和N1/N2比较，不包含原基准求解、新热评价或参数变更。独立两脚本仅用标准库读取既有完整SAFE／输入，精确分数统计与字节一致复现完成；原生产／输入与结果保持。助手据活动能耗、期限和局部选项／事件，推荐每scene仅本地main＋post固定设备、开放原OPP和起点；这是方法子域建议，不是用户确认的新模型假设、已实现接口或已批准研究调用。N2和其他合法安排在原问题仍保留，新增条件须独立绑定，不扩大共享A到跨场景同频同起点。下一项薄接口实现／必要小域校验尚未实施，实际研究预算和调用数待后续确定。详见K.123／E568。

**D146（2026-10-19，用户“继续”承接K.121的同预算配对提案）：** 授权一次CDF关闭／开启单因素配对，均CutMaxIterations=10，原base__R1首A＝CPU1→NPU0→CPU1、完整AB／AC三Stage链及本地模式自由；各自300秒方法总上限、每scene一个60秒合作式片，先off后on，不使用历史结果作control／种子／缓存。原400 ms／5 ms、自动L、物理／温度／合法域和SAFE标准保持。仅新增独立入口与必要mock预检，复用K.121未变的39源依据；出现技术、数值冲突或清理pending停止后续调用并保留已成证据，不补跑、不延时。本阶段完成即止，不据局部分数强化预设更低能耗；后处理不新解码、热评价或求解。详见K.122及对应预声明。 唯一配对现已正常结束，两版均无初始化外新安排／能耗改善／反馈；11项入口与6项后处理检查通过，累计开关仍默认关闭。总耗时差受启动及合作片实际耗时影响，不认定CDF加速。

**D145（2026-10-19，用户“继续”承接K.120后的可选接入）：** 授权落实默认关闭的累计前置开关及必要小域等价核对，不包含原基准性能调用。实际新增生产helper及末尾CDF行，原期望行保留；既有scene／partial builder_options接受严格bool，默认五键和默认归档保持，shared仅补参数用途说明。原物理／输入／域／热安全／原生设置不变；两次预检合计16个结构夹具构模、3个小物理构模（含旧源1个）、2个局部y／依赖行容器，零LP／MILP／MATLAB／热轨迹／研究调用。预检01权限受限false保留；同源沙箱外02为62/62，矩阵身份及190行复用核对通过。新凭据绑定39源，不替代旧记录；下一项关闭／开启配对是助手提案，预算和调用尚未因本记录获准。详见K.121／E566。

**D144（2026-10-19，用户“继续吧”承接K.119后的依赖松弛审查）：** 本轮只核现有期望依赖与累计前置的数学关系、必要局部代数及既有档案静态成本。采用直接边、全部不同后继启动阈值、精确结束和one-hot前提；原期望行保留，首版只删已证恒真／精确重复行，不做变量删项、DAG预滤或跨场景按标签去重。11项单测只执行一次并保存原输出；持久化成本脚本单次复现与原内联记录逐字段相同，薄核验另查全部190条及已存初始化y。未改生产模型、工作负载／物理／热安全，不求LP或MILP、不补跑原基准。下一项可选接入与小域表达预检是助手建议，性能调用尚未授权或执行；不因数学强化成立承诺节能。详见K.120／E565。

**D143（2026-10-19，用户“继续下一步吧”承接K.118单因素配对提案）：** 授权落实单个CutMaxIterations可选开关及必要预检，并按已声明首共享条件、10／1各一次300秒／scene60秒执行诊断。固定共享部署只是本次条件范围，不将一般问题改成固定映射；本地决策、原物理／启动域／热安全不变。两调用独立读入／构模／初始化／worker与缓存；不借历史见证、不补K.116、无重试或延时。新增源变更只限桥接／worker的求解设置传递及独立薄入口／后处理，不把求解设置当算法创新。数值冲突、显式清理错误或现有cleanup_pending标记停止后续调用；K.117原73/74 false及自然退出局限保持。验收看本次初始化之外的完整SAFE严格能量改善，零改善也结束，不扫描其他割轮数。详见K.119／E564。唯一配对现已结束，实际10／1、首矩阵与其余设置核对匹配，两版U相同且均无初始化外改善；不推广1为新默认，不延展扫参。

**D142（2026-10-19，用户“可以，继续下一步吧”承接K.117后的既有日志分析）：** 仅核K.116九次原生记录及静态源码，未运行新优化或改程序。助手据7次已有根LP结果／种子重报和第7次cutgen记录，推荐先单独验证`CutMaxIterations=1`；这是待检工程设置，不是用户已确认算法或已证原因。累计前置强化、DAG余量过滤、加长片及换启发式均不叠加。本次提出首共享条件的10／1各一次、各300秒配对诊断作为下一轮最小范围，尚待确认，不能用本条或旧claim启动。已有源／物理／旧数据保持；无新安全U、节能或热反馈结论。具体提案与停止条件见K.118／E563。

**D141（2026-10-19，用户“行，先进行修复吧”）：** 仅修K.116第10请求文件读取失败。采用固定2秒／10毫秒的传输重试，属于助手在修复权限内选择的工程限额，不改物理参数、合法安排或安全标准；不重试完整求解或研究调用。首次原Python mock受沙箱临时目录权限限制未进入测试主体，同源宿主12项通过，失败记录保留。一次180秒原生小接口六请求完成，读取分支符合，原整包73/74 false及进程自然退出限制保留；独审按范围接受修复，不把删除失败项当全包通过。没有更改原研究结果或补跑K.116。下一项仅依据已有日志收敛求解质量改进点；若需新研究调用、调整模型／参数／预算，另定范围。详见E562。

**D140（2026-10-19，用户“下一步吧”承接K.115后的一次原完整链诊断）：** 按K.114既定原`base__R1`、900秒总上限、60秒片及16条件首遍执行；先冻结29源及唯一claim，未共享旧见证／缓存或更改参数。唯一调用因第10次请求读取错误于763.156秒停止，已有SAFE保留，未重试／延长。5套完整初始化和最终U相同的最佳值如实登记，0内层改善／0反馈；没有将接口故障解释成不可行或将SAFE解释成技术通过。本轮只新增薄入口、只读后处理及结果，不改已准入的搜索／物理内核。助手建议下一项仅修复请求读取及必要预检，未自动执行另一研究调用。若需重跑、调整片或改变输入／安全标准，先另定范围，不沿用已消费claim。详见E561。

**D139（2026-10-19，用户继续K.114后的外层实现与必要预检）：** 用户回复“继续”，承接外层调度／时间片接口实现及必要预检。本轮按K.114完成单时钟单worker、固定片与来源归因，执行模拟及仅一次180秒小域原生接口预检；该授权未用于900秒完整链研究调用。内部独审发现最小上端初始化不一定具有最小真实能量，助手采纳`最终上端 < 全部初始化下端最小值`的严格证书；同时统一规范排序键、显式断开模型引用环及片末不加无后续用途反馈。原分组、首遍不回访、裸MIP回退及D134物理规则保持，未增加算法组件或放宽接纳标准。失败与修订见E560；独审为线程内，非主线⑥。下一项执行范围仍限K.114一次900秒完整链提案，不从本次实现授权恢复旧批次／Goal；若需更改输入、预算或补跑，重新审查。

**D138（2026-10-19，用户授权收拢下一次完整链诊断）：** 用户在K.113提交后回复“那你继续下一步吧”，承接确定完整三Stage共享部署搜索范围与统一预算的建议。本轮只完成协议，不将其扩大为执行授权。助手推荐一次900秒原`base__R1`诊断、按A.main设备分组轮转16名义条件、各场景固定60秒合作式片、单worker单时钟且不回访；是计算组织提案，未改D134控制策略、数值参数或安全标准。选择分组以尽早接触不同设备，保留按全局L_a排序作为后续可比较的简单替代，不宣称该顺序更优；本次不做排序消融。必要新原生接口预检最多一次180秒另列，未运行。两个只读内部子任务核对范围／预算接口，非主线⑥跨会话审查。完整协议与理由见K.114／E559；后续有输入／控制变化、接口不能保持总截止，或需要补跑／改配额时重新审查，不自动继承夜间范围。

**D137（2026-10-19，用户继续K.112后的统一预算小域接入）：** 用户回复“继续吧”，承接内层求解／热反馈与全场景U更新、先小域端到端的建议。助手在授权实现范围内选择先形成全场景初始化见证、原场景顺序共用剩余预算、一个新worker；未改研究对象、物理参数或安全标准。无／拒收x0时保留SAFE并允许完整模型裸MIP，是本轮新增运行回退策略，不等同旧包装；将来正式比较须统一或列明，不记作用户另行确认的基础假设。预检协议预先固定39项模拟代数准入后仅一次180秒原生夹具，无mock见证／候选／缓存共享，已完成且不补跑。源与旧档案绑定、验收修订及结果见E558；小域改善不是原规模收益或热反馈有效证据。外层部署排序／配额、原完整链研究调用及其总预算仍待确定，不从本次授权扩为正式比较或恢复夜间Goal。下一项只收拢完整链诊断协议，规则变化仍按D134重审。

**D136（2026-10-19，用户继续K.111后的接口实现）：** 用户回复“继续”，承接上一步“适配自动L的MILP控制与部分固定部署表达，先小域等价性预检，再进入求解诊断”。本轮接通表达／物理补全及部分固定／合并，未改变D134模型、参数、工作负载或热标准；仅运行必要正确性夹具，无原生优化器或研究方法调用。首轮测试预期错误保留，71/71最终凭据见E557。此项不授权原规模或正式对照，不确定外层排序、配额和方法预算，也不恢复已结束夜间Goal。下一项建议内层生命周期与统一预算的小域端到端接入；若控制开销、跨场景状态或服务约束变化，重新审查D134分解依据和本次凭据。

**D135（2026-10-19，用户要求继续K.110之后的最小实现）：** 用户回复“继续”，承接已确认的D134规则与下一步建议。本轮落实共同控制轨迹／连续评价及必要小域预检，没有新增物理参数、工作负载、基础假设或研究运行预算。实现将新策略显式版本化，原配置和旧hold路径保留；未适配方法暂拒收新策略，待共同适配后再作公平比较。最终凭据为67/67；首轮66/66及旧源码基准固定修订均保留，见E556。后续研究调用数、外层排序和配额仍待阶段协议确定，本次不继承已结束的夜间Goal范围。若改变D134的零额外开销／立即降频或加入跨场景状态，重新审查控制与分解，不能直接沿用本预检。

**D134（2026-10-19，用户确认首版空闲规则并要求推进下一小目标）：** 上一答明确推荐“保留共享域、整域空闲且同刻无新工作时立即L、全部OPP转换额外时间／能量为0”，并标注待确认；用户随后回复“可以”，强调“模型决策先于性能比较”和“分解目标是预算内更低安全能耗，不能只验证变小变快”。据此按上下文确认该首版公开抽象，承接D133的未定时机／开销，不再重复询问。保留旧hold版和全部历史结果，不把自动L称为硬件实测或算法创新；若以后纳入非零转换成本／延迟、入口未完成工作、跨场景热状态或新服务约束，重新审查规则与分解。K.110完成规则／部分固定接口及纸面核查，实际程序／config_v01尚未切换；新策略须共同进入所有方法、评价与相关下界后才能性能比较。外层排序／配额、正式调用数和总预算仍未确定；不继承D132夜间自动运行授权，不重启115项或Q1。下一步建议最小实现与必要预检，以真实后续安全能量和来源为质量验收，规模／构模时间只作成本指标。

**D133（2026-10-19，用户认可结构化优化重心并要求明确推进顺序）：** 用户赞成利用多场景共享部署结构，在合理预算内寻找更低能耗安全方案；认可只固定真正跨场景共享Stage的方向，纠正此前将全部应用部署放到外层的建议。当前AB／AC外层只含A的三个Stage、16种名义单元组合，B／C留在各自子问题；场景入口独立、无其他跨场景约束及加权可加目标为可分条件，条件变化须重审。用户倾向保留CPU共享域、全域空闲后自动L，要求集中说清自动与否、延迟及切换时间／能量；允许该规则确认与分解接口分析并行，不等新模型全套实验。助手提出立即L＋所有OPP切换时间／能量0作为首版公开抽象选项，截至本条记录尚未收到该选项答复，不视为已冻结新模型。五步顺序及接口方案为本轮助手建议，具体实现、方法规则、调用数和统一预算待后续阶段明确；不继承D132已完成六次Goal的自动运行范围或重启旧115项。改变空闲策略须新版本完整复核，旧结果按旧模型保留，跨模型差不作算法收益。本项承接D132结果后的下一阶段研究选择，不覆盖原选择理由；若新增共享应用、跨场景状态／约束、非零切换开销或服务需求变化，须重核分解与控制接口。

**D132（2026-10-18，用户确认夜间有界自主执行）：** 用户希望离开后自行推进，收到“原三个R1条件×current／prefilter、各300秒、共6次最多30分钟研究运行；先实现／预检／独立审查；不改参数、合法安排与热标准，不补跑／延时／扩案例”的一次性确认选项，询问总预计时间后回复“可以，那你开始吧”。据此启动本线程有界Goal并执行本阶段，允许实现细节自主选择、失败记录及最多三轮实质审查修订；真实技术错误或需变更基础条件时保存成果停止后续研究。原正式115项不重启、新调用不共享候选／向量／缓存／见证。完成后审查、同步记录并按长期授权提交普通推送，不要求出现收益。此项替代D131“具体调用与预算待确认”的状态，只授权当前六次范围，不扩为整夜无限调参与实验。

**D131（2026-10-18，用户要求强化MILP效果及热证据）：** 用户要求结合d597c0c和当前状况确定后续方向，争取MILP多数条件下优于对照，并验证热约束、热反馈。本轮确认的是研发优先级和审查请求，不将期望结果写成实验完成标准或已得结论。助手提出优先期限前置过滤／事件重建、伴随已有能耗归因，后续再定完整链诊断；该具体改进顺序、调用范围和预算仍为建议，不从本次讨论推定获批。原任务／物理参数／合法域／安全标准不变；若需变更另议。保留初始化收益与MILP后续收益、热筛查与反馈计算收益的区别，不改写原115项。

**D130（2026-10-18，用户要求先解决MILP异常）：** 用户“嗯，那先把这个异常解决掉”授权核查K.105内部无解与数值接纳初始点的冲突，进行必要修正和预检。三次预声明、各自有界的隔离诊断后，助手依据固定原逻辑子问题的直接配对，将LP预处理显式设为none，并加本次x0／内部无解冲突保护；这是工程兼容决策，不是用户改变模型假设。原物理参数、任务、合法安排、矩阵容差和热标准保持；不据诊断改写原115项、补研究U或自动补跑。原自由调度诊断仍未取得候选，后续若出现新冲突或性能问题，应重新核查，不能把本项外推为所有模型数值正确或优化有效。公共115项与原生13项通过后本项结束，返回结果整理。

**D129（2026-10-18，用户接受仅续行未启动110项）：** 用户“继续”承接“下一步仅续行尚未启动的110项，已执行5项不重跑”。沿原顺序、各300秒／最多33000秒；不重跑MILP、HEFT、SA101—103，不修正103技术失败为成功。原批次只读，续行独立目录／批准／凭据及一次消费，允许必要的入口和只读汇总适配，不改变算法规则、物理参数、工作负载或热安全标准。续行若出现技术错误或源码变化仍停止，不临时加时或自动再续行；没有收益可完成阶段。此为新的续行确认，不把原115次批准重新激活。

**D128（2026-10-17，首批正式比较范围与预算确认）：** 用户“我确认，你继续吧”承接本会话明确提交的15问题／115次／各300秒清单。选择完整执行115次，而非仅首例8次；按原顺序逐次独立计费，先验首例技术正确性，不要求取得SAFE、改善种子、触发反馈或证明最优。沿D127原规则、原完整链及功热参数；批准绑定manifest `ce240771dea8fbadd4b8ec28b91699d3f4c4d80ebee66e3070d39eb1ac69f56b`，只消费一次。技术错误或源码变化停止后续，已完成调用不重跑；资源／预算／数值未决如实保留，不以无收益追加运行。此项仅冻结既有首批范围与预算，不授权新物理输入、DAG变化、Q1重跑或调参。

**D127（2026-10-17，用户接受推进首批正式对照准备）：** 用户“可以，你推进吧”承接“回到完整链正式实验”的大目标。本轮自主落实HEFT／SA与反馈消融规则、代码、统一计时及必要小域预检；规则来源、适配内容和SA自设常数写入唯一正式协议，未改变物理输入、工作负载或安全标准。首批115次／每次300秒仍按D121—122提案集中提交确认，没有把本次推进或Q1的D126授权推定为9小时35分批量已获批。主线⑥`ea3c9ab`的P0先完成正式比较建议采纳，P1新Stage／DAG仅作后续备选；划分Stage会开放独立映射／频点并受5 ms起点对齐影响，不能视为纯规模变化。本次96项正确性检查不作为研究性能结果，Q1不追加调用；若正式运行暴露技术错误，保存记录后停止后续调用，不自动补跑。若用户确认具体清单，另追加确认记录，保留本项历史与范围。

**D126（2026-10-17，用户授权完整推进Q1实验）：** 原文“这部分你暂时可以不用分得这么细，比如你就把下一个小目标定位完成Q1的实验吧，不用经常停下来，你有问题先按照你推荐的选项选择即可”。据此冻结D125推荐的{0,45} ms及两方法各一次／各300秒；自主完成实现、必要预检、执行、结果整理和独立审查，不把助手取舍伪记成用户逐项选定。源自原main最快H时长的起点、原期限／物理／入口／温限保持，main只用于Q1，正式完整链不缩减。无法完成遍历、无安全解或没有改善均允许阶段结束，不补跑／扩时／换参；真正改变物理参数、工作负载范围或安全标准时再讨论。只冻结Q1两次调用，不自动授权正式115次运行预算，也不恢复认证研究。

**D125（2026-10-17，用户接受继续整理Q1运行及必要预检协议）：** 用户“继续吧”承接D124后的协议整理，未直接指定起点或秒数。本轮提出显式域接口、首解辅助整体MILP与联合遍历／局部复用、L0及覆盖协议，不开发主算法或认证工具；继承现首解／x0失败时未进入求解器的限制并如实记录，不悄悄增加冷启动分支。已经集中询问Q1的{0,45} ms和两方法各300秒（备选900秒）是否冻结，尚待回复；本条不作为实现／运行授权，不改变完整三Stage链的正式实验。确认后先进入实现及必要预检，任何主实验预算不得由Q1回复自动推定。

**D124（2026-10-17，用户确认Q1的main子工作负载及限定用途）：** 原文“接受main子工作负载，Q1只作为第三章的小规模优化质量参照，正式主实验仍然使用完整三Stage链”。因此选择D123中的main分支，不采用完整链作为这一小型参照；原完整链主实验不缩减。取舍是保留共享部署／合法设备／工作点／资源竞争和完整热能耗，以减少参照规模，结论只及该子工作负载，不验证前后处理依赖或完整请求最优性。{0,45} ms等具体项沿现有Q1提案整理，执行协议和统一预算仍需冻结，本条不新增实现／运行授权。若以后将Q1用于主实验或作完整链最优依据，必须重新审查；输入正确性错误或无法完成遍历应按既定未决／修复规则处理，不自动换负载。

**D123（2026-10-17，用户要求继续下一个小目标）：** 用户“那继续推进我们的研究吧，继续下一个小目标”。本轮只把K.99的一个质量参照输入具体化并讨论删Stage／限起点的必要取舍，不启动实现／实验。助手建议Q1主计算子工作负载、起点{0,45}和沿原期限／功热参数，已说明不能代表完整请求链；与完整链仅限起点并排比较，规模数均为代数筛前或单项期限过滤计数。选择题尚待回复，不能将“继续”当作接受删Stage、具体起点或300秒预算。若不接受Q1，保留此设计记录并继续其他已授权准备，不运行多版本挑选，也不改变完整链主实验。

**D122（2026-10-17，用户接受外部审查的有边界处理并要求继续）：** 用户“可以，那你继续吧”接受本会话对审查的分项判断：复用已有正确性和旧模型实验，补一个小型质量参照及精简热约束证据，不发展认证系统、完整温限扫描或层层准入。本轮将其落实为K.98计划v2（K.99）；一个实例、质量两次／热补充最多四次及统一T为助手提出的可审阅上限。具体Stage／起点限制、温限数值、首批方法／清单、300或900秒尚未确认，不把原则授权扩成新输入冻结、实现或运行授权。补充未决时不阻塞无关准备，无最优／翻转／收益不触发扩时或重挑参数。

**D121（2026-10-17，用户要求提交当前状态及后续确认项的计划供审查）：** 用户要求“把我们目前的状况、进展以及接下来需要确认的写一个计划提交吧，我审查一下”。本轮只整理K.98审查稿及关联状态；保留D120停止无限诊断的约定，建议暂缓K.97、先定首批正式方法／输入／预算／重复和消融。15问题／115调用、300秒、MILP首解版本等是助手待审建议，不记录为用户已选，不据此运行或修改参数。旧95问题／675调用／60秒为历史完整提案；最终范围以用户审查后的冻结协议为准。

**D120（2026-10-17，用户确认由助手把握验证停止点并回到正式实验安排）：** 用户“嗯，你觉得验证到合适的地步了就可以回到第三章正式实验的安排了”。据此不把原规模最优或连续工程改进作为章节实验的前置要求。助手判断K.95—96已有正确性证据足以开始收拢第三章最小实验安排；D119固定部署原规模诊断保留为可选补充，部署／预算尚未确认，本条不授权新运行。若选择该诊断，单次结束即回实验安排；真实正确性／安全／计费错误才触发受影响修复检查，不因缺少改善而自行扩时、堆组件或修改输入。正式执行仍需冻结比较规则与必要预检，不将本次约定记为实验已就绪。

**D119（2026-10-17，用户接受继续整理原规模诊断安排）：** 用户“可以，你继续吧”承接K.96下一项，先明确固定部署来源和一次性总预算。助手提出复用历史SAFE的单元部署、保留全部相容工作点／起点，建议300秒、备选900秒；这两项是待确认建议，不记录为用户已选，也不恢复旧900秒授权。条件子问题不冒充整体优化；改变范围／预算需回到本项讨论，超时不自动扩时或换部署。已通过异步选择题集中询问，当前尚无回复。见K.97协议；K.96源码／协议与旧结果保持。

**D118（2026-10-17，用户接受固定部署单场景的小域原生接入）：** 用户“继续”接受K.95下一项，接通MATLAB候选求解、原连续温限反馈和统一计时。助手事前声明三个既有正确性夹具（双场景、真正重分段链、解析内部峰），各一次180秒完整调用；180秒沿用既有小域接入尺度，不冒充用户逐项指定或修改正式预算。纯Python37项门槛与源码／协议哈希先通过，随后实际三次调用完成，无补跑或扩时。真实研究输入、参数、合法选择与安全标准不变；解析夹具复用已有单元检查定义，不计研究案例。新模块不加首解、修复或外层算法；已有视图／场景SAFE及违规跨中断保留，内部界和无解仅solver-reported。本阶段原生28项门槛和独立终审通过后停止。任何原规模诊断的部署／限额尚未确定，须下一项先讨论，见[协议](research/chapter3_experiments/scene_method_protocol.md)。

**D117（2026-10-17，用户接受固定部署单场景接口实现与小域核查）：** 用户“继续”接受K.94下一项，实施固定部署的单场景构模／未加权评价适配，保留全部相容安排并重核新事件的物理包络；期限前置过滤可对整体与固定部署表达共用。助手采用默认关闭的显式构模选项、新增单场景回执及同预算汇总接口；这些是实现选择，不新增物理假设或固定研究部署。仅用既有小域及明确标为正确性用途的期限／入口边界夹具；原参数、研究输入与安全标准保持。不运行原规模或正式对照、不确定外层算法。本阶段227＋44项当前门槛通过后停止；后续MATLAB接入和任何新运行另行推进，不把Python残差接纳冒称求解器实际接纳。

**D116（2026-10-17，用户接受固定部署结构核查）：** 用户“可以，你继续下一个小目标吧”接受K.93推荐。范围为固定完整共享部署后的条件证明、源码接口及静态规模计数；不改物理参数、合法安排、安全标准或生产模型，不构造／求解MILP、不运行热仿真、不补原900秒或选定分解算法。助手用已有首解的单元身份作尺寸示例，并把期限前置过滤与部署过滤分开归因；这是审查口径，不是用户指定部署、更改原决策域或给后续方法注入答案。独立入口、无跨场景共同约束及启动触发切频／空闲保持是分离与缩控制的适用条件；这些规则改变或场景跨热历史关联时须重审。见[核查](research/chapter3_experiments/fixed_deployment_structure_audit.md)。下一项适配实现与小域核查仅为建议，尚未自动执行。

**D115（2026-10-16，用户授权首解辅助的完整方法诊断）：** 用户“欧了，那你继续下一步吧”接受K.91下一步，核原规模MATLAB实际接纳及后续优化。助手事前沿用一次900秒总诊断尺度，不修改正式预算；首解在本次调用重新构造／连续评价／补全计费，保留K.88四项开关及原参数、完整合法域、安全标准和求解选项。先过当前源码的必要预检，独占声明后只运行一次，不补跑、扩时或正式比较。初始回执先保存，初始U和MILP后续改善分列；求解器重报种子不算优化收益，收到x0不自动称已接纳。异常、预算及数值未决保留已有证据；任何后续运行另行讨论。见[协议§7](research/chapter3_experiments/initial_point_protocol.md#7首解辅助完整milp调用的预声明)。900秒为助手沿用既有尺度的本次限额，不冒充用户逐项重指定的数值。

**D114（2026-10-16，用户授权原规模有限见证／接纳诊断）：** 用户“那你继续下一步吧”接受K.90推荐，继续核原`base__R1`的安全见证构造与完整初始向量接纳。助手事前声明一次180秒工程上限，保持K.88四项表达开关、原参数、完整合法安排与连续热安全标准；不补跑、不延长、不进入MILP优化或正式比较。新入口先做小域生命周期核查，原规模只检查Python全行数值接纳，MATLAB实际接纳记未测试。已形成SAFE在补全拒收／中断后保留。此180秒是助手选择的本项诊断限额，不冒充用户指定数值或正式预算；若失败需调整规则、物理参数或预算则集中讨论，不自动改动。具体预声明见[协议§6](research/chapter3_experiments/initial_point_protocol.md#6原规模见证与数值接纳诊断的预声明)。

**D113（2026-10-16，用户授权首解构造与接入小域预检）：** 用户“行吧，就按照你的思路来，有问题及时和我沟通”确认K.89下一步：固定简单构造、三层接纳和尝试上限，实现可选初始向量并做小域预检；未授权再次原基准900秒或正式对照。助手采用最多三档域工作点模板、固定共享单元／期限优先就绪表及最早合法格点；它们仅作种子规则，不限制主MILP逐忙段调频、具体映射或时序。名义浮点补全必须经过原容差的全量数值检查，SAFE始终由原连续评价器给出，已有见证在拒收／超时后保留。保持原参数、模型、目标和安全标准；若需复杂新求解器或模型调整则讨论。协议见[首解接口](research/chapter3_experiments/initial_point_protocol.md)。

**D112（2026-10-16，用户授权能量下界强化后的单次900秒诊断）：** 明确开启能量下界强化，保留期限必零、单位级频点聚合和辅助整数连续化，原`base__R1`、参数及连续热安全标准不变。完成必要接入核对后，只运行一次900秒绝对总预算诊断，记录根LP、首次合法候选、首次安全方案及后续收敛。采用新目录和独立一次性声明，不补跑、不延长、不开展正式比较；900秒不自动改为正式实验预算。新开关仅本次显式True，默认设置不改；入口或资源失败也作为本次记录，任何再次原规模调用需讨论。

**D111（2026-10-16，用户授权热能耗条件约束强化与小域预检）：** 承接K.86无首解记录，从现有表达推导有效下界，再做小域等价性预检；保持原参数、完整合法安排与热安全标准，不补跑原基准。助手采用从已导出条件能量行及变量盒推导的每片段共享斜率下界，独立开关默认关闭，不改M、原物理行或评价器；这是本轮实现选择，不是新增物理假设。若推导不能保留原数值外包整数点，或需改服务／安全标准，则停止并讨论；原规模性能及后续运行仍未授权。

**D109（2026-10-16，用户确认两项调度强化后的单次900秒完整诊断）：** 采用期限必零与单位级频点聚合版，辅助整数连续化暂不开启；保持原`base__R1`、参数和热安全标准，记录首个候选、首个安全方案及后续收敛。先核源码／预检凭据，使用同一总墙钟900秒，不补跑、不临时延长、不正式对照。该授权仅覆盖本次调用，不把900秒确认为正式预算；具体执行与证据见K.84，后续变更须另记。

**D110（2026-10-16，用户确认辅助整数连续化后的单次900秒诊断）：** 在期限必零与单位级频点聚合基础上，仅本次显式开启辅助连续化；先补必要数值接纳预检，全部通过后原基准一次900秒总墙钟，记录首次合法候选、首次安全方案及辅助量解码。参数、完整合法安排和热安全标准保持，不补跑、不扩时、不正式对照。此项接续D109，落实K.85建议，但不确认性能收益或正式预算。预检若发现实现缺陷，保留失败记录并修正，原规模调用不得自动重试。

**D108（2026-10-16，用户授权调度层等价强化及分项小域预检）：** 承接D107，先落实期限必零和单位级频点聚合，再单独核辅助整数连续化；保持原参数、完整合法安排及热安全标准，不补跑原基准。助手实现原行完成后收紧必超期选项上界、精确单位级聚合及独立辅助整数开关；默认主版本只启用前两项。165/165分项、82/82MILP反馈、29/29计时检查通过，覆盖数学合法域及原物理行，不将更少整数声明自动解释为加速。辅助连续化保留可选版本是本轮实施安排，不构成用户已选定正式比较版本；后续若启用应明确记录。原规模运行、预算、参数或安全标准变动仍须讨论。

**D107（2026-10-16，用户授权原MILP松弛与整数结构静态审查）：** 承接D106，核查15分钟仍无首个整数可行解的表达原因及保持原数学含义、完整合法选择的改法。原参数不变，不补跑、不扩大预算；助手可读归档矩阵并作可复跑计数与代数证明，不自动修改生产模型。K.82确认期限必零、单位级频点聚合、辅助整数性推导及能量下界接口；尚未证明各项实际耗时收益。下一步先提出小域等价强化实施范围，未将建议当成已实施／已授权新的原基准运行。若需更改物理模型、合法选择、数值安全标准或运行预算，先讨论。用户重发的资源和规模回答沿用D94／D95，不覆盖原路径。

**D106（2026-10-16，用户授权一次15分钟总预算完整诊断）：** 承接D105，用户选择先用事先声明的900秒让原基准进入求解，观察首次候选、首次安全方案及后续收敛，再决定正式预算。原输入、数学表达、全部合法选择和参数不变；计时从输入读取前开始，包含构造、独立MATLAB启动、数据交接、求解、连续评价和记录。仅作一次，不补跑或临时延期，不做正式对照。助手采用不可变回调事件和同一绝对预算内的独立复核，安全回执与内部界分列；重复完整安排仅在本调用复用回执，未决前缀不作安全上界。启动与构造仍串行；本轮900秒仅为诊断授权，不自动替换正式协议。若需改变数学表达、工作负载、参数、安全标准或正式比较预算，重新讨论。

**D105（2026-10-16，用户授权同一原基准完整方法级调用核查）：** 承接D104，用户要求检查MATLAB启动、交接、求解及连续复核能否共同纳入60 s，保持数学表达、合法选择和当前参数，暂不正式对照。助手保留串行生命周期及独立新进程，仅加固定原基准完整入口和分项记录；29/29计时、9/9桥接、82/82实际MILP预检通过后仅调用一次。60 s内完成模型，但MATLAB未及时就绪，后续环节未到达；没有安全输出。建议下一步核预算内启动与构造重叠，此建议尚未实施；不自动放宽预算、跨调用复用进程或修改输入。

**D104（2026-10-16，用户授权控制状态与活动功率行组装／存储的等价优化）：** 承接D103，用户要求保持数学表达、合法选择和参数不变，先通过小域逐行预检，再作一次原基准60 s构造核查，暂不正式对照。实现选择为右端不可变元数据复用、活动功率双向系数及误差预备、不可变数值／标签复用；全部约束、可变行记录及错误包络保留。198/198逐行、81/81回归、24/24计时通过后，唯一诊断06在47.469 s内完成模型和矩阵，无求解器调用。本轮不涉及新模型或参数选择；下一步完整方法级可实施性核查仅为建议，改变参数、合法域、安全要求或预算仍须讨论。

**D103（2026-10-16，用户授权命中组装及剩余成本分解与等价优化）：** 承接D102，用户要求拆清模板命中后、活动功率行、功率上界等成本，保持数学表达、合法选择、当前参数不变，逐行预检后一次同原基准60 s，暂不正式对照。助手仅调整精确表达的重复构造和计时记录：成对模板、精确边界签名、转换与负号复用、精确误差计数求和、状态公共功率项。最终186/186逐行、81/81回归和24/24计时通过后仅作诊断05；整体仍未完成。下一步控制状态与活动行组装／存储核查为建议；若需修改模型、输入、保证或预算，仍须先讨论。


**D102（2026-10-16，用户授权条件行模板复用）：** 承接D101，用户明确要求保持数学表达、合法选择和当前参数不变，先过小域逐行预检，再核同一原基准60 s，暂不正式对照。助手采用模型内完整行模板及编号重映射，键覆盖有序系数、边界、右端和条件变量位置；不同键继续原计算，不合并或删行，不改变保证。171/171逐行检查、81/81回归和24/24计时检查通过后，仅运行诊断04；第一场景完成，整体仍未完成。下一项成本拆分仅为助手建议；若后续需要改变模型、参数、预算或安全标准，须重新讨论。


**D101（2026-10-16，用户授权热能耗构造成本拆分与等价优化）：** 用户要求继续拆清系数计算、约束组装和记录成本，保持数学表达、合法选择与参数不变，小域预检通过后核查同一原基准60 s构造，暂不正式对照。承接D100，助手在既有正确性夹具内剖析，采用本次模型内精确矩阵幂、边界及转换结果复用，记录累计计数；不采用近似矩阵指数、不改变误差包络。预检通过后运行一次诊断03，完整模型仍未构造完，主要成本已落在条件行组装。下一项模板复用为助手建议，尚未实施；若需更改数学域、参数、保证或预算仍须讨论，不能自动把实现困难变为模型简化。

**D100（2026-10-16，用户授权等价构造优化及同基准核查）：** 用户要求先优化模型构造开销，讨论Python与MATLAB的适用性，保持数学表达、合法选择和当前参数不变；先过小域等价预检，再核同一原基准60 s构造，不运行正式对照。承接D99，助手选择有序索引、精确整数快路及本次构造内纯参数复用，不删除约束／选项、不改误差保证。138项等价核对及受影响回归通过后，运行一次原基准02；控制层改善但完整模型仍未完成，结果按未决保存。暂不整体迁移语言是基于本次定位的实施建议，不是用户新模型选择；若后续需要改物理输入、合法域、安全标准或预算，仍须讨论。本轮不自动再跑原规模。

**D99（2026-10-16，用户授权构造成本核查及统一计时）：** 用户要求“继续核查原基准规模的模型构造成本，并落实方法级统一计时；保持当前参数不变，暂不运行正式对照”。承接D98，仅在原`base__R1`作一次60 s构造诊断，不启动原规模求解器、不扫描条件或补跑。助手实现单例输入展开、绝对截止期和可观测构造记录，属于计费／诊断适配，不改变共享部署、忙段调频、响应、功热参数及安全要求。原规模构造未完成后停止，保留未决；后续等价构造改进为建议，若涉及数学域、工作负载、物理参数或预算调整须再讨论。

**D98（2026-10-16，用户授权MILP接入与小域正确性预检）：** 用户要求“继续接入MILP候选生成与反馈，先做小域正确性预检，保持当前参数不变，暂不运行正式对照”。承接D97，保留共享具体部署、逐忙段工作点、本地温度漏电、400 ms窗口与5 ms启动集合；完整能量进入MILP，不退回活动代理。助手在既定表达内选择区间系数外包、由变量盒推导M、MATLAB R2023b桥接及最多50轮的未决保护，记录为实现细则，非新增物理约束。独立小域与解析热夹具仅核程序正确性，不替代原95项研究输入；未批准修改物理、工作负载或安全标准，也未运行正式方法对照。若正式规模不可实施或需要改变已定条件，应带具体构造／运行证据讨论，不自行删状态、改粗启动集合或削弱热要求。

**D97（2026-10-15，用户授权实现共同连续评价及必要预检）：** 用户明确“继续实现共同连续热能耗评价器和必要预检，先保持当前参数不变，有需要选择的地方及时讨论”。承接D96，仅推进连续评价基础层；沿原四节点、局部温度功率、400 ms窗口及5 ms有限起点，未改物理／工作负载数字或安全标准。助手在该范围内选择60位定向舍入、18阶Taylor余项、温度坐标缩放及子段细分，并保存数学依据与独立核对；它们是数值实现选择，不是新的物理假设或用户指定算法。仅运行正确性夹具，正式95问题与方法比较不在本轮执行。若误差无法达到、模型温区不相容或接入方法必须调整参数／安全标准，应说明证据并再讨论；不能以扩大温度容差换取通过。

**D96（2026-10-15，用户保留数值并授权逐步实施）：** 用户在听取400 ms窗口、5 ms起点及功热参数的来源与限制后表示“这些参数先保留”，要求核查实验还缺什么，并可着手逐步推进。承接D93—D95，当前数值作为首版实施输入；不把它们升级为实机参数、不推定窗口中性或网格损失可忽略。首步落实独立输入包、基础合法性／功率片段检查和环境核查；普通算法与数值实现细则可在现有范围内制定并记录，必要预检通过后逐步推进。正式方法与数值协议尚待完成，保留原60 s／SA五种子为待落实的运行提案；不得暗改模型、参数、工作负载或安全标准来换取可运行或有利结果。若必须改变这些已确认项，集中说明原因并与用户讨论。

**D95（2026-10-15，用户确认首版固定链增加请求数）：** 用户集中选择“先用固定链增加请求数：采用当前完整数值包，先完成首版”，对应问题明确为每请求三Stage、每应用1／2／3个请求；分支汇合先用于正确性预检。承接D93，确认正式首版负载族及规模轴，不改变一般DAG模型，不将回答扩展为全部物理参数、网格和预算的冻结。若需要对任意DAG拓扑作实验结论，先增加声明图和配套参数，保留本版结果范围。

**D94（2026-10-15，用户确认同一平台改变可用设备）：** 用户选择同一2 CPU＋GPU＋NPU抽象平台，比较CPU、CPU＋GPU、CPU＋NPU及三者齐备；两个CPU均保留，未供任务使用的加速器仍保留空闲功耗、入口OPP和热节点。承接D93，只改变任务合法设备集合，不模拟关机或实体芯片变化。若以后比较物理设备数量，重新配套基准、分布和热网络，不套用本组的能耗解释。

**D93（2026-10-15，用户确认先形成具体实验草案、暂不深入基线细则）：** 用户认可“一套基础配置＋五组具体变化条件＋共同比较规则”，要求数值附来源和选择依据，先不代码、不实验，关键选择集中讨论。承接D91—D92，暂缓单独深入HEFT／SA；主方法、HEFT、SA作为首版比较方向，混合方法保留候选，反馈消融嵌入预声明子集。授权准备数值提案和静态核对，不授权自行将未确认数字变成正式输入或启动实验；本次具体提案集中在配置草案§7—10。

**D92（2026-10-15，用户确认首版先考虑HEFT适配版和SA适配版）：** 用户要求将两组比较依据、必要适配及混合方法／热反馈消融分工写入文档并提交GitHub，供主线7参考，先不代码、不实验。承接D91，HEFT与Zhou相比优先保留时长表、优先级和插入骨架，避免直接继承本题不再满足的能量排序分解；SA与GA相比先控制交叉／种群／修复的实现负担，不预判性能。Zhou与GA保留备选。具体HEFT多场景构造、SA邻域与接受规则未确认；固定部署／次序后再用完整能耗MILP的混合方案是交接建议。热反馈消融保持完整目标和安全检查，仅改变违规反馈，不被混合方法替代。适用范围为当前S1／I1／G1、D76及D82—D84；若适配无法保留关键决策、实现代价明显超出预期，或已有可靠GA／贪心实现改变成本判断，再集中比较，不因预期输赢更换基线。此项不冻结参数、算法细节或授权自动运行实验。

**D91（2026-10-15，用户确认五组实验规划及简明表达）：** 用户明确要求“把这五组实验规划整理进文档，提交到GitHub”，保持“不同条件下各算法的表现”这一表达，具体参数暂不确定、暂不做实验。承接D89—D90，采用配置草案§6.1的五组问题：场景／资源、任务规模、期限松紧、热条件及任务频率响应。相对于原草案三个问题类别，改用五组易读标题；原模型对照、反馈对照和有限域检查保留为按需小对照，不自动增加实验组或要求全部运行。确认范围仅为实验组织，不批准具体数值、算法、样本或执行；现有共享部署、独立场景入口和完整热能耗模型保持。若配套输入或求解成本需要调整分组，或拟改变基础模型，先集中说明取舍再讨论，不按预期收益删改实验。

**D90（2026-10-15，用户确认首版采用文献指导的抽象仿真）：** 本轮核查尚未凑齐同平台的Stage响应、局部温度功耗和耦合热参数，向用户比较“文献指导抽象仿真”与“先锁定具体设备补数据”；用户明确选择前者，保留CPU/GPU/NPU及当前模型，区分文献取值、推导值、自设值，结论限定于声明模型。承接D89，不把获得完整实机数据作为首版准入条件，也不据此任意调整参数制造收益。配置草案的具体规模、OPP、功热数值、服务条件、起点集合与预算仍待集中审阅；这不是自动批准任何数值。若以后取得匹配设备数据，或目标转为实际设备收益，重新核对支持范围、参数与标定误差；原抽象结果仍按原输入保留。

**D89（2026-10-15，用户确认实验组织与配置依据分开）：** 用户明确主线⑥的实验组织参考可供借鉴，但具体配置不能直接使用，应继续学习相关文献。沿87号第5节组织验证问题、公共比较规则、分组与结果；工作流／场景、合法资源与工作点、响应、功耗／热参数、期限／窗口、样本及求解设置分别核查来源与适用条件，再形成配置草案。优先复用本地已读全文，按缺口定向补查，不为凑完整参数表混合不同平台的数值。文献可提供构造方法而不一定提供可直接迁移的值；数据不足项明确保留仿真假设或待确认，不冒称设备实测。本项承接D88与E509，不改变模型、批准新实验组数或冻结数值；若数据适配需要修改基础假设，再集中讨论。

**D88（2026-10-14，用户授权落实逐节叙述改善，后续准备实验）：** 在逐节讨论3.2—3.6后，用户要求“把刚才每个章节……需要优先改善的地方，都分别改善一下”，并提出后续准备着手实验。本轮据此修改正文的概念引入、例子、输入分类、公式解释和流程分支；保持D87主版本及既有模型、公式、求解范围，不把叙述修订作为新建模或实验结果。当前阶段结束后准备集中输入包与预检协议；具体参数、平台与实例规模、启动集合、预算仍需按来源和适用条件讨论，此授权不等于这些未定输入已确认。若改写触及执行语义或保证范围，应先还原并单独核查；有益例子仅供说明，不自动变成冻结研究案例。

**D87（2026-10-14，用户确认正文主版本并授权开始初稿）：** 用户要求在条件允许时按已整理目录开始写作，先完成仿真结果之外的内容，再共同安排实验；遇到必要前置工作可先核查。异步选择明确回复“是，以chapter03.tex为主版本”，`chapter03_new.tex`仅作为批注参考原样保留。承接D85—D86，已核模型与数学推导可以先成稿，数值参数、实现验证和实验结论后补；不以写完正文视为实现完成。若推导发现必须改变基础设定、或预检表明表达与执行语义不一致，再讨论并修订。写作开始前保存用户现有正文和批注快照，吸收其叙述意见，保留旧结果和旧证明的历史材料，不维护第二份当前正文。

**D86（2026-10-14，用户要求补录第三章目录，先写初稿再实验）：承接D85，沿用既有八节组织并补齐写作职责。** 确认依据为用户“我们之前不是讨论出来一个第三章的章节安排吧，那个你也写进文档里面把，后续我计划让主线⑦按照这个去写一版出来，然后再开展实验”。章节顺序为引言、系统模型、功耗与温度模型、问题定义、问题分析与形式化、MILP求解流程、仿真结果与分析、小结；系统与功耗温度子目录及各节分工见[独立审查§9.5](research/Kim多场景共享部署_求解路线独立审查.md)。八节骨架有75号及现有LaTeX依据，按当前模型补充的职责／小标题不冒称历史逐字确认；不直接继承旧方法名或结果。区别于D85仅交接待补清单，本项明确后续按目录形成3.1—3.6初稿供用户审阅，3.7保留框架、3.8仅总结已完成内容，然后再安排实验输入与实现验证。本次授权是记录目录，不是当前会话直接写正文、运行实验或向其他会话发送任务。保留D82—D84与符号参数；如实际推导需要调整小标题，可保持职责调整，若涉及基础模型／保证范围则另行讨论。

**D85（2026-10-14，用户确认先理顺符号模型与MILP，再准备实验输入）：调整K.66后的推进顺序，关联D82—D84，模型选择不变。** 确认依据为本会话用户：“先把模型、问题定义和MILP形式化理顺，具体参数保留符号，暂时不写代码、不做实验”，并授权整理文档、提交GitHub供主线7参考。相对于K.66原建议先形成小规模输入草案，本次先整合系统／任务／功耗／温度模型、完整问题定义、问题分析与MILP表达及连续检查反馈；实例数值和具体求解设置后置，参数的含义、单位、适用域及编码成立条件仍须先说明。待补清单见[独立审查§9](research/Kim多场景共享部署_求解路线独立审查.md)，不是整合已经完成的记录。不新增物理机制，不更改有限启动、逐忙段控制、本地注热或完整目标；本轮只改交接和状态，保留旧计划及理由。若形式化必须改变已确认假设，或存在无法仅用符号条件解决的关键关系，再集中讨论该项；不因尚无数值或未发现节能收益自动换方向。完成后再按确认范围准备实验输入与数值协议，不自动开始代码或实验。

**D84（2026-10-14，用户确认本地温度与来源注热）：采用按来源分别计算的物理接口，更新R86-v1.1。** 确认依据为结构化选择“按来源分别计算：各单元／设备用本地温度计算温度修正并注入本地节点；共享基准另按给定分布处理，需要细化现有接口”。另一个候选是保留组代表温度及整体固定分配；没有采用，因相同组总功率不一般保证相同空间注热。当前用\(\lambda_{gn}(\xi_g)(T_n-T_g^{\rm ref})\)表示本地修正，系数按来源及工作点、工作与空闲共用；组基准只算一次，分布另给。保留既有节点、控制域、活动可加及有效范围，不增加逐Stage斜率、不假定均分、不选具体数值。修改P3／H3及相关输入，原R86-v1留存，正式模型同步；有限事件的仿射结构可保留，具体系数／界不得混用。若后续只有整包计量、无法辨识来源，或发现真实共享功率需要未声明节点／非本地关系，先回审输入或本项，不由实现补造。关联D83、K.65／E505；不授权编程、实验或改论文正文。

**D83（2026-10-14，用户确认第三章有限启动参照）：一般模型连续，第三章MILP采用预先声明的有限启动集合。** 确认依据为结构化选择“采用有限启动集合（推荐）：沿当前完整热能耗MILP构造推进，最优或无解结论限定于该集合”。取舍是用已知事件片长承接完整瞬态热能耗表达，同时接受可能遗漏连续域安排；本次没有确认损失很小或已获得连续最优。D82逐忙段调频、真实时长及连续热安全不变，未选每场景一次OPP；集合不必等间距，具体间隔、生成规则、实例参数、物理映射及数值实现均待后续明确。两章同域比较时使用同一声明集合；如将来必须给连续域最优／无解保证，或有证据表明离散限制改变研究判断，回审本项而非偷偷扩大保证。下一项先明确物理接口支持范围，不授权直接实现或实验。关联D82、K.62—K.64；旧一般模型连续启动不被覆盖。

**D82（2026-10-14，用户确认暂保留逐忙段调频）：一般模型沿R86保留域清空后的工作点重选，一次OPP仅保留为简化版本或对照。** 确认依据为对比两种调频粒度的研究作用后，助手建议“一般模型暂时保留逐忙段调频，一次工作点保留为简化版本或对照”，用户回复“嗯，就先听从你的建议吧”。理由是该自由度可利用Stage响应差异，并使不同忙段的频率参与热状态及完整能耗协调；不是已经验证的收益。该选择暂不采用D81／K.62的一次OPP建议，历史推导仍对其受限政策有效。不把此回复扩大为已确认有限启动域、线性温度映射、求解器、数值参数或实现授权。下一项先补逐忙段控制表达和成本；若实际输入只有单工作点、单忙段，或实现成本与研究价值不匹配，再讨论收紧范围。第三章参照与后续方法比较须明确采用同一调频政策，不将受限参照的最优／无解外推一般问题。关联D81、R86及D76。

**D81（2026-10-14，用户授权完整参照取舍核查）：优先核查第三章完整热能耗MILP参照，审查哪些简化可降低实现难度且保留实质工作。** 确认依据为读取最新提交后的讨论及用户“行吧，那你进行下一个小目标吧，看哪些地方可以简化，但是又不会让问题过于简单，从而保有一定的工作量和创新性”。沿独立审查§8的参照目标推进；D74的有限工程搜索及K.61保留备选，不再作为第三章默认完成标准。授权的是纸面表达、来源核查和取舍说明，不是确认有限启动域、一次OPP、线性物理映射或任何数值参数。K.62提出三项范围建议并交代所失能力；保留S1／I1／G1、D76及原R86，等用户选择后再改模型。关联D75、D80及提交81e6bee；若输入不支持线性映射或有限事件规模不可承受，再只讨论相应一项范围，不自动删漏电或扩新机制。

**D80（2026-10-13，用户确认按K.60计划继续纸面路线）：先讲清完整能耗指导时序调整、再反馈配置重选，不代码、不实验。** 确认依据为用户“ok，那就按这个计划继续吧”，有需选择处及时询问。K.61据此核查一条分解路线；授权的是路线论证，不把本轮提出的可行方向／回溯、三类邻域、次数限额或具体求解器登记为已确认算法。沿S1／I1／G1、D76和D74；本轮没有需新增确认的物理假设，完整控制、代表温度与注热依然是必需输入。若采用该方法草案须显式接受有限方向／邻域的覆盖限制；需要改变启动域、热模型或保证等级时另行讨论。关联D79，旧“活动能量生成后再择优”不作为完整反馈接口已完成的依据。

**D79（2026-10-13，用户授权读取独立审查并制定计划）：读取《求解路线独立审查》第7节后收拢下一步，不等于确认其中全部方法建议。** 本轮核对审查§5—7及K.59，主会话采纳完整能耗须进入连续优化与配置重选这一计划要求，建议优先核查分解路线；具体反馈、求解器、覆盖协议和实现仍待共同审定。保留S1／I1／G1、D76及D74工程保证范围，没有改变物理／任务模型。若后续无法形成有限、可实施的连接，或需要基础假设／近似调整，集中说明接口与取舍后讨论，不自动退回纯代理评分或发展全局认证系统。关联D78。

**D78（2026-10-13，用户授权MILP表达分工整理）：明确可直接编码的变量／约束、需外部评价的能耗／温度及交接方式，不写代码、不实验。** 确认依据为本轮用户明确请求，有必要选择及时讨论。K.59沿§6与D76，不新增基础选择；模式／冲突编码及能量分解为助手代数推导，代理目标和时序查询只是待审定方案，不因本项授权而生效。完整控制映射、代表温度与注热仍作为必须明确的输入保留，不默认补值；如具体输入不能形成相容域状态，或要求完整真实目标连续域最优证明，再共同审查。关联D74、D77，未改变安全接纳标准。

**D77（2026-10-13，用户授权问题定义整理）：先明确输入、决策变量、目标函数和约束，不写代码、不实验。** 确认依据为本轮用户明确请求，需新增选择时及时讨论。K.58在已有系统模型稿追加问题定义，保持R86、S1／I1／G1与D76；本轮未发现必须新增确认的基础选择，输入参数与物理映射不自行赋值。共享部署和场景内工作点／起点分开，真实加权完整能耗不降为活动能量代理。后续先共同审阅，再展开MILP表达分工；D74允许工程级最优性未决不等于放宽原问题或批准具体搜索协议。关联D75—D76。

**D76（2026-10-12，用户确认主要任务响应形式）：采用可缩放部分＋固定部分的表达。** 确认依据为结构化选择“采用这一公式作为主要表达（推荐），参数与适用范围以后按资料确定”，对应d(f)=d_ref[(1−α)+α·f_ref/f]。α按Stage和执行单元给定，为参考时长中可缩放部分的比例，范围0—1，不是优化变量；参考时长、参考频率和适用频率范围待匹配资料或显式L3输入。原文依据为Da Costa（2025）§3.3式(5)，Stage化索引为本题适配，不宣称原HPC资料验证所有CPU／GPU／NPU。改变参考点须重新换算参数；没有选择分段响应或温度相关时长。相同工作量／配置跨场景仍用一致d与q，活动功率独立提供。若配套资料不支持该形式或有效范围，先讨论修正，不为公式改变数据。关联D75及R86-D1／D2。

**D75（2026-10-12，用户调整阶段顺序并授权系统模型审阅）：按系统建模、问题定义、MILP求解、实验验证推进。** 确认依据为用户要求先确定任务、处理器、响应、功耗／温度等模型，再形式化和求解，并回复“可以，那你进行下一步吧，有问题及时和我沟通”。本轮只收拢已确认模型与真正待定关系，不要求先填实验参数，不继续早／中／晚等候选协议；缺失的基础选择须共同确认。D74工程级保证范围保留为已接受选项，但不使助手提出的候选细节自动生效。R86和S1／I1／G1保持；先交付系统模型审定稿，再共同进入问题定义，不自动写代码或实验。

**D74（2026-10-12，用户确认首版求解保证等级）：采用工程级候选搜索，允许连续域最优性未决。** 确认依据为结构化选择“先形成可实施的候选搜索路线（推荐）：MILP生成合法方案，完整评价后择优；可保证输出安全，但允许连续域最优性未决”。未选先建立完整真实目标全局最优参照；不因此删去温度漏电、离散化启动或降低安全接纳条件。安全保证仍以声明模型、入口、有效范围及完整误差核查为前提。活动能量查询、有限代表和反馈组织是本轮助手建议，具体代表覆盖、重访、配额与预算待后续审定；本项不授权程序实现或实验。若以后必须给原连续域最优／无解证明，重新审查可靠界与覆盖接口，不把当前工程输出升级。关联D68—D73。

**D73（2026-10-12，用户授权接口路线说明）：讲清MILP候选、完整能耗与评价反馈，不写代码或实验。** 确认依据为用户“继续下一个小目标……先讲清楚MILP怎样生成候选、评价器怎样计算真实能耗，以及评价结果如何反馈”，需选择处及时提问。沿S1／I1／G1及R86，只在既有说明稿追加阶段二，不改正文／研究程序／参数，不自主补选温度映射、代表配额或旧实验预算。关联D72，保证等级另见D74。

**D72（2026-10-12，用户同意开始阶段一）：形成共同模型与求解接口说明，先收拢问题，不自动执行后续阶段。** 确认依据为前轮四阶段计划及用户“ok，开始推进吧”。本阶段交付共同决策图、变量／约束／能量温度关系、MILP与评价器分工及输入完备性；验收为问题完整、评价一致、已明确和待设计接口分开。不选研究数值、不设计算法、不运行实验、不改正文；S1／I1／G1及R86沿用。参数选择、完整求解方法和实验需在后续阶段共同落实，不能把开始阶段一解释为自主补齐全部未定假设。关联D67—D71；不以先证明共同收益或旧方法失败作为本阶段门槛。

**D71（2026-10-12，用户更正G2为G1；替代D70）：采用外给场景权重的平均系统能耗。** 确认依据为用户“我选错了，我想选G1的”。保留S1／D68和I1／D69；D70作为误选历史保留，不再生效。目标为Σp_c E_c，p_c非负且和为1，权重对候选与方法固定，表示声明完整评价片段的相对出现次数；具体值、使用统计来源或抽象实验假设仍待确认，不能自动等权或补造真实概率。所有声明场景含零权重仍满足期限与连续热安全；窗口与工作量仍按原待定范围。若输入仅有驻留时间占比，先核清评价边界并讨论换算，不直接代作次数权重。此更正不是算法／实验授权。用户同时明确师兄未必最合理，后续须结合其他文献和本题实际条件提出方案共同讨论；长期规范登记于AGENTS，不以沿用师兄作为充分理由。

**D70（2026-10-12，用户选择G2）：采用声明场景完整评价片段的等权平均系统能耗。** 用户回复“我选择l1、G2”；所有场景权重固定为1／场景数，不采用助手此前推荐的G1不同使用权重。等权是比较偏好，不补称实际出现概率；每场景窗口及工作量由输入声明，候选和方法之间固定，不要求所有场景同长，不自动解释为每请求能量或时间平均功率。所有场景都须满足期限与连续热安全。若以后有可信使用统计并希望优化实际加权能耗，再讨论替换本项，不自行改权重。关联D67—D69；目标形式与师兄式(3-34)的等权情形一致，能耗口径及热约束仍按本方案说明。

**D69（2026-10-12，用户选择I1）：每场景给定一个完整入口，逐场景核查有限评价窗口。** 用户回复“我选择l1、G2”，按上一轮入口选项上下文将l1记录为I1。入口含各热节点温度、各控制域初始工作点，首版无未完成工作；不同场景可有不同入口，但同场景所有候选共用同一声明入口。未选I2入口范围覆盖，不推出实际切换重置温度、任意历史或无限重复安全。若需覆盖入口区间、遗留工作或实际切换接续，回到本项重新讨论。关联D67—D68；确认范围而非冻结入口数值。

**D68（2026-10-12，用户选择S1）：跨场景共享部署固定到具体执行单元。** 同一应用的同一固定Stage在不同场景使用同一具体CPU单元／GPU／NPU设备；工作点与时序仍可随场景改变。未采用S2仅固定设备类别；理由为保持Kim／师兄共同映射契约，用户通过选项明确确认。适用前提是该具体单元合法支持Stage；若后端只要求设备类别驻留、具体编号可自由重选，或研究需要入口相关设备重选，需回到此项讨论，不能自动放宽。关联D67；入口I及权重G尚待确认。

**D67（2026-10-12，用户确认保留路线并要求共同定范围）：先保留Kim路线，讲清共享部署、场景入口和能耗目标，需选择处给选项与例子；不设计算法、不实验。** 这是当前推进路线的用户确认，承接D66，尚不等于冻结全部模型范围或最终题目。K.52只整理三项边界并请求选择，不以助手推荐补成既定假设，不恢复此前无限多模式实施。

**D66（2026-10-12，用户要求客观评价整体建模）：判断相对Kim／师兄的实质增量是否足够支撑第三章，先不设计算法、不实验。** 本项仅授权模型与成章价值审查，不是最终采用Kim或批准新范围。K.51的条件性认可、贡献强度及不追加因素为助手判断，用户尚未确认；关联D63—D65。共享部署、声明入口、统计归一化及原暂停状态不因评价结论自动改变。

**D65（2026-10-12，用户要求按整体建模理解重梳Kim路线）：说明非统一1/f、热状态和多场景共享部署的结合、借鉴与自主工作，并举例；不改正文、不实验。** 承接用户“已有公式写入整体模型仍有自主思考”的判断，K.50细化K.49／D64的归属表述，分别说明公式来源、模型构建和待验证贡献。授权的是候选解释与讨论材料更新，不等于选择Kim为最终主线，亦不确认共享层次、入口、统计口径或新算法。关联D63—D64；R86及暂停状态保持，教学数字不成为研究参数。

**D64（2026-10-12，用户要求客观审查增量）：区分相对师兄的常规适配与潜在实质贡献，先不实验。** 仅授权原文对照及贡献归属审查，不是选择Kim为主基座、采纳新增方法或批准入口／共享／统计口径。K.49将热约束节能模型列为扩展、具体热反馈列为方法候选，属于助手判断；关联D63／D62，未改变R86及暂停状态。师兄是否在实验中实际用反比缩放仍待明确信息，不以缺失说明补成事实。

**D63（2026-10-12，用户要求Kim路线一页方案）：说明共享对象、相对Kim／师兄的增加内容、热保证范围及实质工作，先不实验。** 授权整理候选稿并一起审阅，不等于选择Kim为最终主线或接受具体设备绑定、有限场景入口、无遗留工作、权重／窗口及能耗归一化。K.48中的范围及方法分工仍为助手建议；关联D62／D60／D53。R86、历史结果及暂停状态保持，基础选择须后续集中确认，不能用一页稿代替用户决定。

**D62（2026-10-12，用户要求比较Kim多场景对题目的研究价值）：核清继承与热节能增量，不选定基座。** “同样的，再看看”授权与Lombardi同尺度的原文核查及条件分析，不等于接受跨场景共享映射、特定入口集合、使用权重或恢复多模式实施。K.47／E485的有限场景首版、入口上角分析及优先细化Kim均为助手建议。关联D61／D60；既定R86与暂停状态保持，后续改变共同部署／服务范围须集中确认。

**D61（2026-10-12，用户同意继续一起审查）：只核Lombardi候选是否有可控热安全分析路线。** 前序对话要求解释扩展的研究价值，本次“继续下一步”授权原文核查及条件推导，不等于接受不确定时长、事件执行、最小等待或某种能耗目标。K.46／E484的时间窗比较路线、一页方案及可选细分均为助手建议，未冻结或实现；不恢复旧多模式、不运行实验。关联D60，进入候选基础调整时须集中确认。

**D60（2026-10-12，用户要求寻找原生共同决策基座）：从本地文献核清共用什么、为何需要共用及可扩展内容，先不实验。** 授权定向阅读和比较，不等于选择Kim／Lombardi或批准共享部署、时长不确定、事件执行、寿命约束、共享计算等范围调整。K.45的两候选及分标准推荐为助手建议；先有共同契约再评价方法，不要求先出现额外共同收益。关联D59／D58／D53，历史结果和既有模型保持；后续进入任一范围前集中讨论，不自动恢复暂停问题族。

**D59（2026-10-11，用户要求客观审查三项工作的贡献）：对照Jung和Pourmohseni区分常规适配与核心候选，先不实验。** 仅授权贡献归属、原文能力及实质差别审查，不是确认第三组为最终主线、批准新判据或恢复多模式实施。K.44将任务1／3主要列为基础适配／求解组织，任务2列为条件性核心候选；具体判断属助手审查结论，不冒充用户选择。关联D58／D57／D53，既定服务、基础设定、安全范围及历史结果不变，不将简单方法有效或旧无额外收益作为否定整个方向的依据。后续细化或实施仍按阶段范围讨论。

**D58（2026-10-10，用户授权第三组一页核心增量说明）：只明确具体任务、近邻区别及实质工作。** 用户要求以第三组为例，不实验、不扩方向；不是确认第三组为最终主线或恢复旧多模式实施。K.43一页说明中的持续分析及规划反馈为拟开展工作，不视为已实现或用户批准新增方法规则；原模型、参数、服务范围和安全标准保持。关联D57／D53，不重新要求额外共同节能作为立题前提。若后续要改变基础设定、扩大认证范围或进入实现，先说明并讨论；本轮结束于一页候选稿。

**D57（2026-10-10，用户要求“再比较一下第三组”）：继续比较可复用模式与转换基座，不做实验。** 授权承接D56比较第三组的原文能力、继承与修改、问题例子及工作量，未授权选定方向、变更基础假设或恢复多模式执行。K.42／对照表第8节提出“第三组作上层问题基座、第一组供热节能技术”的条件性分工，属于助手建议；不将故事辨识度等同新颖性，不要求先证明额外共同节能。关联D53／D54及D55；旧模型、暂停状态和历史结果保留，具体持续保证与方法效果仍待研究。

**D56（2026-10-10，用户要求并排比较并给推荐）：先比较前两组，不做实验。** 授权核清热DAG节能与端侧配置两组的继承、修改及问题例子；未授权助手选定基座或改变基础设定。K.41／对照表第7节建议第一组作主骨架、第二组作输入及表达参考，属于助手建议。两组原能力和需适配范围分别保留，第一组不承担首次联合优化主张，第二组不被误写成局部贪心。关联D55，下一项一页方案以用户选择为前提，不恢复暂停问题族、不启动实验。

**D55（2026-10-10，用户要求先逐篇梳理再筛选）：以本地全文和既有阅读笔记重核能力边界。** 授权按端侧推理、任务相关频率响应和热状态逐篇盘点，再讨论可继承基座；用户接受提出更好筛选方法，不等于已经选择新问题。K.40完成79项材料对照与三组比较建议，保留旧评价及实验记录；未批准改变模型、在线边界、服务语义、参数或运行实验。下一步一页继承／修改表是助手建议，尚未确定主基座。关联D54／D53，不恢复暂停问题族，也不以旧合成实验的无额外收益淘汰全部方向。

**D54（2026-10-10，用户连续澄清并要求查找）：以文献问题为基座，再运用本题工具。** 用户确认“不同热历史共用模式方案”可以提供基础，后续使用Stage、非统一1/f与热状态设计模型和算法；额外共同节能不承担立题门槛。纠正K.38将现有P1不再扩写理解成不适合作基座的范围，不撤销D53。授权查找其他有文献依据、可借模型／方法／实验的基座；Q1／Q2／Q3均为助手比较，未获选择，不批准多速率、不确定性、事件启动或休眠等变更。原热历史基座保留，具体新颖性及算法效果仍待核；本轮不运行实验。

**D53（2026-10-10，用户直接纠偏）：不以“共同规划带来额外节能”为核心故事。** 用户明确希望借鉴师兄的研究问题组织方式，而非继续以旧合成实例的额外收益作为立题依据。本项替代D50的核心收益要求及D51的补证优先级，保留二者历史理由。能耗优化目标不变；方法仍须在相同问题／约束下作公平验证，贡献需交代应用理由、继承与自主适配。K.37的P1只是已有结构，不作为新方向；P2仍未确认。此次不批准基础模型变更、参数调整、实验或跨场景问题族自动恢复；以后如讨论基础调整须单独说明。重新审查触发条件为具体候选形成后发现应用理由不足、高度重复且无自主工作或不可实施，不以简单方法有效自动换题。

**D52（2026-10-09）：用户要求借鉴师兄思路并融合本题，提出可继续的入口。** 授权概念比较与材料核查，不等于批准共享映射、在线选方案或其他基础变更。K.37／E475提出P1现有共享方案结构与P2新增共享部署备选，推荐P1；用户尚未选择。D50的额外收益期望保留，尚未由新的贡献口径替代，不运行实验或推进方法实现。

**D51（2026-10-09）：用户“继续下一步”批准执行D50已定的共同收益依据审查。** 本轮只核既有模型下的收益条件、HT-1／TP-1证据及简单复核／回补能力，记录K.36／E474；未批准修改物理、工作负载、基础假设、安全标准或运行实验，也未恢复方法实现。下一项定向参数资料核查为助手建议，不改记为用户确认；额外共同价值仍按D50保留为研究期望，尚无新增收益证据。

**D50（2026-10-09，用户选择题直接确认）：先补共同收益依据。** 在“先明确安全节能求解对照／先补共同收益依据”之间，用户选择后者，将跨模式共同选择的额外价值保留为核心，暂缓方法实现，先审查针对性依据；未采纳助手优先整理方法对照的建议。只改变验证优先级，保留当前模型、使用／服务条件和安全标准。下一项先核条件与匹配证据缺口，不扫描参数、扩规模或运行实验；若关系依据仍不足，先报告并讨论，不自行改研究重心。关联D49／K.35／E473；不覆盖此前选择理由。


**D49（2026-10-09）：用户“继续下一步”批准承接K.34整理论文方案与主张。** 本轮只收拢已有问题、文献分工、实现与证据状态，不改基础设定、运行程序或恢复TP-1。两项后续优先级仍待选择：先形成同问题方法对照（助手推荐），或先补额外共同节能依据。没有将继续整理等同于批准改变贡献重心、安全范围或实验输入；E473。

**D48（2026-10-09）：用户“ok”同意承接K.33，按既有下一项建议只读收拢四组合证据。** 只结合新持续证书、原能量和反例，核身份／区间，交主线6审查；不修改参数、服务、入口、安全标准、旧代码或历史结果，不重新评价热／能耗、不恢复搜索。四点内排名是综合证据结论，不冒充原程序新输出或全域最优；E472。结束后仅建议收拢论文方案，新的研究取舍待讨论。

**D47（2026-10-08）：用户“继续下一步吧，记得让主线6审查”批准限定实现及独立审查。** 承接D46／K.32，仅核原TP-1 a_n b_c活动间隔证书、必要预检及持续安全接口；参数、工作负载、入口、安全标准、原程序与历史结果不变。审查通过后保存新证书，不重新运行有限路径能量，也不自动形成新的四点最优结论。主线 (7)统一Git，主线 (6)只写独立审查。E471。

**D46（2026-10-08，承接K.31）：用户认可小范围持续论证审查，要求覆盖全部声明入口、长期重复及全部合法切换时刻。** 本轮只核a_n b_c最长NPU活动、最短活动间隔和转换影响，不以40/45ms路径或A/B分别安全代替持续保证，不仅扩大50°C盒。交付简单路线／覆盖／工作量／实现或停止判断；不修改物理、服务、输入、程序或运行案例。E470建议实现是助手建议，尚未视为用户批准进入实现；若改变轮内表、周期、切换间隔、入口或功率／热参数，需重新核此前提及充分界。

**D45（2026-10-08，承接K.30）：用户“继续”授权绑定一次性入口、核查后执行原定TP-1诊断。** 沿原四组合与F1/F2、A/B单模式探针；每评价20秒，零参数／服务／精度变化，不重跑超时、不扩案例。阶段内独立审查和必要实现修订由主线统一推进，结束于本次结果与审查，不要求发现收益。E469。

**D44（2026-10-08，承接K.29）：用户“继续”授权完整路径、局部评分、反例检查及预算分流接线预检。** 本轮使用独立小夹具，不自动执行TP-1正式四组合；保留原物理、服务、精度、安全标准和20秒限额。E468。通过并独立审查后再绑定一次性正式入口。

**D43（2026-10-08，承接K.28结论）：用户“继续”授权解决数值积分计算能力。** 在TP-1物理、服务、精度与20秒预算不变的条件下，自主选择等价数值实现并做针对性预检、独立审查；本轮不运行正式四组合或修改安全标准。E467。实现无法通过时保留未决，不调参数或扩预算。

**D42（2026-10-08，承接D41）：用户确认TP-1参数及必要预检。** 用户在K.27具体参数及审查交付后回复“可以”。C=[.02,.000020]、G=[[.105,-.005],[-.005,.020]]、两NPU活动1W及四方案按K.27，仍为L3。E466。原CP1／HT-1不改；预检通过前不开展正式诊断，不调整参数寻找违规或收益；数值实现受阻时保留失败，不默扩20秒或放松精度。

**D41（2026-10-08，用户继续推进；推荐取向按上下文执行）：形成一套L3条件构造草案。** 用户在“按预先声明条件构造L3／先取得匹配平台数据”提问后说“继续吧”；本轮按推荐的L3口径提出具体数值，不重复追问取向。该继续不视为批准未见过的显著物理修改；TP-1数值及新增b_c方案仍待整体确认。独立审查只验证推导和范围，不代替用户批准；无新实验或参数落盘到运行输入。

**D40（2026-10-08，用户“继续吧”）：准备具体参数及使用条件变更草案。** 承接D39／K.25建议；允许本轮提出具体表并独立审查，不视为批准新物理数值、工作负载或安全标准。K.26只改文档；来源透明L3仍为推荐方向，尚未决定新热压力构造原则，不补写成用户确认。

**D39（2026-10-08，用户直接授权自动协作、范围按紧邻提议）：K.25验证条件审查。** 用户在认可“先审查检验内容及输入依据、再运行”的建议后要求“继续像之前那样自动迭代”。沿D38协作方式授权主线 (6)审查与主线 (7)修订／Git，最多三轮；本轮只形成对照条件和必要变更清单，不新运行实验。修改物理、工作负载、基础假设、安全标准仍交用户；完成方案或出现用户待决即停止续接。L3新包为助手建议，未把数值或工作负载调整写成用户确认。

**D38（2026-10-08，用户直接授权）：K.23阶段内自动协作。** 承接D36/D37；完成输入与预检，通过后一次四组合诊断并独立审查。主线 (7)统一推进、审查派发、逐项采纳、Git；主线 (6)只写独立审查文件，不并发Git。最多三轮实质修订；参数／工作负载／基础假设／安全标准变更交用户。没有优势也是有效结果，完成立即停止。20秒调用上限和先输入审查后正式运行是助手记录的实现组织，不补充研究假设。若授权范围需要改变或三轮仍有实质分歧，保留成果并等待用户，不能自行续开新目标。

本表于2026-10-06建立，D01—D07为依据对话及既有记录的补录，日期不冒充每项原始确认时刻；D08—D09为本轮确认。范围是当前多模式主线的选择路径，早期研究沿革保留在原报告及证据记录中，不宣称已重建全部历史。

**路径概览：** 多模式方案共同设计 → 放宽“实际序列全部已知” → 热状态与节能优先 → 首版不跨轮重叠 → 平均能耗目标与硬安全分开 → 抽象任务模型 → 声明条件下持续安全。

| 编号／状态 | 选择及未选方向 | 确认依据与取舍理由 | 适用边界／重新审查触发条件 |
|---|---|---|---|
| D01 已确认优先方向 | 重点研究离线共同设计多模式方案与转换适用条件；完整已知序列规划保留备选 | 用户：“可以先重点讨论第二种，第一种保留为备选”；E393、E399。研究对象从一次固定组合扩展到可反复使用的模式方案及其前后联系 | 这是研究入口选择，尚不等于已证新颖性；若应用只有一次已知任务过程，重新比较备选的必要性 |
| D02 已确认范围调整 | 模式模板、参数及允许转换已知，实际切换顺序不必预知；离线生成方案，运行时按方案执行、不重新求解 | 用户明确选择“接受这一离线边界”；E400。无需把实际未来完整提供给优化器 | 替代新方向中的“全部实际请求／到达已知”，不改R86历史结论；若需运行时按热状态选配或拒绝转换，应另议职责 |
| D03 已确认研究重心 | 侧重热状态与节能，不研究切换等待优化；采用旧工作完成后进入新模式，不跨模式重叠 | 用户：“切换等待不是我们想研究的重点”；随后同意推进；E401—E402。借此集中研究热状态延续与能耗 | 不取消模式内合法等待；转换成本与响应要求仍需输入定义。若服务要求必须跨模式重叠，重新审查执行边界 |
| D04 已确认首版限制 | 同模式轮次也不交叠，轮内允许并发；暂不加入跨轮流水线 | 用户指出目标是能耗而非吞吐，并要求保留将来复核条件；E402 | **如果应用必须多轮重叠才能满足既定到达率／帧率、期限或积压要求，必须重议**；不能为保留限制而降低服务需求 |
| D05 已确认目标 | 按使用情况优化平均能耗，对声明允许运行范围保证期限与热安全；未选最坏能耗最小化 | 用户明确选择该目标；E403—E405。平均用电代价与硬安全分别处理 | 统计与权重待定，无实测分布时标抽象评价。若目标改为硬电量保障或使用统计不再适用，重议能耗口径；低概率不免除安全要求 |
| D06 已认可方案主线 | 共同评价模式方案的热状态、能耗与前后关系；MILP参照与启发式服务同一问题 | 用户在S4讨论稿后表示“认可”；E406。以问题—模型—方法—验证组织论文，先核定问题再定算法 | 认可研究构想不等于认可某个新算法、求解器保证或收益；目前尚未与导师讨论 |
| D07 已确认建模顺序 | 可以先采用抽象任务模型，不要求先选真实应用；先定义输入与决策，参数以后落实 | 用户质疑“必须要实际应用吗，不能像师兄那样抽象吗”，随后授权模型整理；E407 | 模型定义不是授权新增简化。若后续主张实际平台收益或应用可部署性，需匹配数据及服务要求验证 |
| D08 已确认安全目标（2026-10-06） | 选择声明条件下持续安全，未选仅保证指定有限时段 | 本轮用户回复“确认”；承接E408的两选一。理由：方案预期反复使用，实际转换序列和运行长度不必完全预知 | 初始状态、负载、驻留和转换须遵守声明规则；持续安全尚待证明。有限仿真不是替代证书，任何退回有限保证的范围变化须再讨论 |
| D09 已确认协作规则（2026-10-06） | 保留选择路径及变更历史，不仅记录最终结论 | 用户：“把我们选择的都记录一下……回溯看我们之前的选择路径” | 新决定追加编号；变更关联旧编号、记录原因及确认依据，旧项保留。不把助手推荐自动升级为用户决定 |
| D10 待用户选择（2026-10-06） | 推荐P1：切换请求同时提出B首轮工作，等待计入期限；备选P2：启用后释放、另约束转换响应 | E410、讨论稿附录C；助手建议理由：工作需求与期限基准不随方案快慢改变，便于共同评价节能与服务。原文提供协议定义依据，不是对本题的直接证明 | P1要求相应输入已就绪或有固定释放偏移；P2仅适用于工作确实在启用后产生的语义。尚未选择，不能覆盖D03；排队、驻留与准备成本未随推荐冻结 |
| D11 已确认P1（2026-10-07，承接D10） | B切换请求同时提出首轮工作；系统可等A完成再执行B，等待必须计入B期限；P2本轮未采用 | 用户明确回复上述选择；E411。D10保留为当时提案快照，其待选状态由本项结束 | 从切换请求时刻计首轮服务期限，不能因实际进入较晚而后移；依赖与数据就绪仍约束实际执行。未同时确定驻留、请求排队、准备成本或后续轮次释放规则 |
| D12 待用户确认（2026-10-07） | 推荐R1固定周期轮次、轮内期限≤周期、外部切换请求间隔L_m≥P_m；请求时停止旧模式未来释放，已释放工作保留。同刻切换优先于旧轮释放。备选R2事件驱动且限制最小间隔 | E412、讨论稿附录D。助手建议理由：固定服务节奏与负载密度，便于保留离线热节能重心；周期、MRC及转换协议有原文依据，但本组合是本题适配 | 新增范围限制尚未获确认，不将时间下限冒称Jung的完成次数MRC；实际进入不重置周期。若需求必须更频繁切换、跨周期积压或跨模式保持连续流，须重议。数值与使用统计未冻结 |
| D13 已确认R1（2026-10-07，承接D12） | 用户选择“固定周期提出工作＋规定最小切换间隔”，采用D12所列首版规则；R2保留未采用 | 本轮用户明确选择并授权继续；E413。D12保留提案快照，其待选状态由本项结束 | 固定的是规则形式，不是周期、期限、间隔或开销数值；不能通过优化器延长周期、修改外部请求或少做工作节能。D04应用适配触发条件继续有效 |
| D14 已确认“主线（6）”的审查职责（2026-10-07） | 按用户明确的会话名称：“主线（7）”负责主线推进；“主线（6）”解释当前进度，同时从旁观者角度审查进度与下一步计划 | 用户要求“主线（6）”协助检查另一长对话可能出现的幻觉或偏移，并于同日明确两会话名称。不能只复述报告或将另一会话结论直接当成事实；核对已确认选择、原始证据、逻辑、范围及计划必要性 | 这是协作分工，不改变研究模型；审查职责不因其他会话读到此表而自动转移。审查指出具体依据、问题影响及最小纠偏建议；未查原文的判断标明待核，不以审查为由重启无休止的选题筛选。不自动改另一会话成果或向其发送指令；分工调整另行记录 |
| D15 已确认逐项协作（2026-10-07） | 暂不由助手自主完成整个研究阶段；基础内容共同商量，后续实验在协议明确后再自主执行 | 用户明确指出风险既包括改动已确认设定，也包括把未定项自行补成假设；随后授权当前使用信息核查。例行阅读与出处核对仍可自主完成 | 影响任务语义、评价口径或保证范围的补充需用户选择；条件推导不自动成为正式假设。本项不改变D14会话分工，也不撤销既有提交／推送授权 |
| D16 待用户选择（2026-10-07） | U1完整使用路径及权重（助手推荐）；U2使用过程统计规律 | E417、讨论稿附录H；U1便于逐条核对工作、温度历史与能耗，适合日志或抽象测试分布；U2适合有依据的过程统计输入 | 只讨论平均能耗的使用信息，不缩小持续安全范围；未选择初温／初始状态分布、路径、权重、窗口末端处理，不默认马尔可夫性、稳态或冷启动 |
| D17 已确认U1（2026-10-07，承接D16） | 平均能耗采用完整使用路径及权重；U2过程统计规律未选 | 用户明确回复“U1吧，你继续”；E418。D16保留当时提案及推荐理由 | 各路径共用一套模式方案；加权评价不替代全范围持续安全。不同时确认具体路径、权重、初始分布、窗口或冷启动条件 |
| D18 待用户选择（2026-10-07） | 评价入口I1直接给定各路径起始温度与工作点（推荐）；I2从给定运行前史传播取得 | E418、附录H.4。I1与R86给定入口一致，便于同条件比较；I2可计入前史造成的候选相关入口，但需明确前史及计量边界 | I1不等于冷启动或所有路径入口相同；I2不等于稳态。不允许切换重置温度，不默认加入未完成任务；原安全初始集合及认证方式另待落实 |
| D19 已确认I1（2026-10-07，承接D18） | 直接给定每条评价路径的入口温度与合法工作点；I2前史传播未采用 | 用户回复“嗯，就用L1吧”，按紧邻上下文对应I1直接给定入口，并非新增选项；E419。D18保留提案与原推荐理由 | 同一路径对各候选使用同一入口，路径内连续继承温度；不等于冷启动、所有路径同入口或每次切换重置。具体数值、安全初始范围及认证方式未同时确认 |
| D20 待用户选择（2026-10-07） | W1共同固定窗口覆盖窗内全部已释放工作的期限（推荐）；W2任意时段截窗并保留跨窗工作 | E420、附录H.5。W1便于比较同一路径完整工作及空闲尾段能量，需先核查各路径与共同窗口是否相容；W2保持任意观察边界但只报告窗内能量 | 不提前停发、取消周期工作或令截止期提前；W1只约束能耗评价路径／窗口的选取，不缩小持续安全允许域。不存在共同边界时须另议，不能随方案完成时间改变W |
| D21 已确认W1条件性优先（2026-10-07，承接D20） | 首版抽象实验优先W1；先核查既定路径能否共享相容边界，不满足再讨论W2 | 用户明确提出条件性采用，不能反过来扭曲工作负载；E421。D20保留原提案 | 不为迁就W1删选路径、改变权重、周期、切换请求、释放或期限；W由输入核查确定后对各候选固定。不满足时不自动采用W2，不增加停发／排空运行规则；具体边界尚未验证 |
| D22 待用户选择（2026-10-07） | 首轮受阻后T1整轮平移（推荐）；或T2保留释放锚点、另定延迟传播 | E426／附录K.5；任务书核查发现现有轮级例子未定义逐Stage晚启动处理，已向用户提出选择。T1保留相对间隔与并发，T2需额外执行规则 | 两者都不移动原释放／期限；未获回答前不得当作已确认执行语义。此选择不冻结准备成本、初态、数值或分析器实现 |
| D23 已确认T1（2026-10-07，承接D22） | 首轮受阻后整轮平移，Stage相对间隔和顺序保持；T2未采用 | 用户明确选择“整轮平移……两个Stage都晚3 ms，保留轮内间隔与顺序”；E427。D22保留提案及推荐理由 | 原释放时刻、绝对期限及后续周期不变；准备、初态、数值与具体评价器实现未同时确认。若以后要保留部分Stage原起点或在线调整，须另议 |
| D24 待用户选择（2026-10-07） | 首版Z0统一零额外准备（推荐）；或Z1逐转换给定准备片段 | E428／K.7；用户已被询问，Z0以模型／输入就绪为理想化条件，集中核热状态与节能；Z1需时长、工作点及功率／注热描述 | 两者都保留旧工作排空、等待功耗和热历史；Z0不等于真实设备零成本，不修改R86历史范围；未确认前不填κ=0，不新增迁移或搬运资源 |
| D25 已确认Z0（2026-10-07，承接D24） | 首版V1统一零额外准备，Z1给定准备片段未采用 | 用户明确选择模型／数据已就绪的理想化条件，集中核查热状态与节能；E429。D24保留提案 | 保留旧工作排空、原期限、等待功耗与温度延续；不代表真实设备没有成本，不取消DAG依赖，不扩成所有后续版本的永久假设；以后有加载／搬运需求须重新核查 |
| D26 已确认打包推进方式（2026-10-07） | 将V1时序、物理参数、初温、温限、误差要求和预期结果一次整理为完整小型输入草案，不逐参数拆轮讨论 | 用户本轮建议整体预检输入包，只为核对评价器，不刻意选节能收益参数；E430 | 这是数值草案整理授权，不把助手提出的具体数值升级为用户已确认参数；整体审阅后再决定实现，基础执行语义仍按既有选择 |
| D27 已授权V1实现与预检（2026-10-07） | 按现有小型输入包实现固定方案评价器，一次完成首批预检 | 用户在第1小目标计划后回复“可以，继续吧”；E432 | 本次允许使用草案数值核程序，不将其冻结为研究平台／收益案例；不同时授权V2、优化器、参数扫描或改变运行规则 |
| D28 已确认V2首版接口范围（2026-10-07） | 沿用V1共同轮级期限、零额外准备与现有计量接口，先落实反复运行和任意合法切换检查；多请求不同期限随后单独扩展 | 用户选择“先沿用V1预检范围……把持续检查做通，多请求不同期限以后单独扩展”；E434／K.10 | 仅限定首版程序预检，不缩小一般模型，不限制实际切换为网格或有限次数。安全入口集合、具体数值及较细闭合方法尚未确认；若真实任务要求多个不同期限或准备开销，须扩展接口后才可作适用性结论。本轮未启动V2实现 |
| D29 已采纳验收分层（2026-10-07，细化D28） | 基础持续检查与利用顺序／相位的精细检查独立验收；基础证书足够时直接给出持续安全结论，精细层分别报告实现、能力及成本 | 用户提出分列验收以控制工作量，助手核查G.4／K.10后采纳；E435。优先形成基础层预检包，不把精细层作为其完成前提 | 不缩小允许运行域，不把共同温度盒定义为全部可行域；基础条件失败无反例时仍未决。入口完整记录温度、模式、工作点、周期与切换间隔状态、未完成工作；首版维持初始无旧工作，具体入口值仍未确认 |
| D30 已授权V2基础实现与预检（2026-10-07） | 使用E436完整输入包，实现期限／共同温度范围证书验证、具体反例重放及未决管理 | 用户在预检包交付后回复“继续下一步吧”；本轮落实为K.12／E437 | 允许使用L3草案核程序，不将14 ms期限、初态或物理参数升级为研究数据；不授权精细层、优化器、参数扫描或更改既定运行规则。基础证书验证不含自动合成温度范围 |
| D31 已确认同输入整合与期限隔离（2026-10-07） | 从唯一候选输入调用V1与V2，核评价入口／路径属于声明安全域；12／14 ms分别保留，不交换证书 | 用户指出12／14 ms风险，助手提出共同输入、历史分离、两种期限独立核对、不替研究选期限四项规则，用户回复“ok，继续吧”；E439／K.13 | 授权整合实现和预检，不授权选择正式期限、修改V1/V2、优化器或新研究案例；两种期限属于不同服务问题，不能当同问题候选比较节能 |
| D32 待用户选择（2026-10-08） | 推荐A：直接共同规划全部模式的设备、工作点和轮内时序；备选B：给定单模式完整候选库后组合 | 用户授权继续讨论候选生成；K.14／E443提出一项选择题，尚未收到选择，不将A写成已确认 | 两种均不改变服务条件和U1口径；B结论限候选库，A仍需落实目标、时域及继续搜索接口。未同时选择网格、代理目标、算法或求解器实现 |
| D33 已确认直接共同规划（2026-10-08，承接D32） | 采用A：开放各模式Stage的合法设备、工作点和轮内时序，不先固定单模式候选库 | 用户在本轮选择题明确选择“直接共同规划（推荐）”；K.14／E443。D32保留为提出时的记录，待选状态由本项结束 | 只确认生成组织，未确定时间网格、代理目标、继续搜索规则或MILP实现；不改变周期／期限／转换范围，不默认现有评价器已覆盖完整平台 |
| D34 待用户选择（2026-10-08） | 首版规划器采用显式有限相对启动网格（建议），或保留连续相对起点 | K.15／E445；已提出选择题。有限域便于完整候选管理和单赋值排除，连续域保留一般模型但需另定失败后的继续搜索接口 | 尚无回答，不自动选网格或Δ；网格仅限制轮内偏移，实际轮基点、合法切换、时长／结束与温度检查保持原含义。一般连续模型不变，不预言精度损失或加速 |
| D35 已确认连续候选路线（2026-10-08，承接D34及E447） | 先沿连续时间表达制定首版候选搜索协议；有限网格保留备选 | 用户明确：“后续如果难以形成可实施办法时再回到备选方法”；本轮K.17／E448提出有限候选尝试协议草案 | 不自动改为网格，不同时确认步长、预算、响应数值或完整连续最优保证。具体实施受阻时说明原因再讨论回退；单次未决或无收益不是自动换域条件 |
| D36 已确认首次主线验证重点（2026-10-08，E458） | 先验证热历史是否改变持续安全方案的能量排序与共同选择；组合热违规保留后续 | 用户明确选择“先验证热历史是否改变安全方案的能量排序与共同选择”；利用已有完整能量传播与基础持续安全检查，先核能量关系，不同时扩精细分析 | 保留全部声明范围的安全要求；不要求热约束必须活跃，不预设收益。若全部候选不能获持续认证，或无法区分温度／等待／工作点继承，说明缺口再讨论；不自动缩小安全域或改模型。输入、逐模式对照口径与方法尚未冻结 |
| D37 已确认首版关系诊断口径（2026-10-08，E460） | 复用CP1已有物理参数、合法响应及两条使用路径；逐模式从既有30°C参考评价，再在真实连续过程统一复核；接受能量变化但选择不变 | 用户选择“采用：复用旧参数，接受选择不变”；避免新增参数找翻转。K.23四方案和具体评分公式是本轮可审阅实施草案 | 不把30°C当实机典型温度，不修改安全入口或物理运行温度；四组合仅诊断，不替代D33连续联合域。若对齐或区间分辨失败如实记录，不能调参强求收益；后续正式方法比较仍需单定范围 |

**D34建议更新（E447，2026-10-08）：** K.15的网格优先是历史助手建议。原文与适配核查后，当前建议优先落实连续时间候选表达的工程协议，有限网格保留备选；这不是用户确认，D34的待选状态不变。后续用户已通过D35确认连续方向，本段保留E447时的建议状态。

**仍未选择：** 周期／期限／最小切换间隔的具体参数、后续版本若需非零准备的描述（首版V1已选Z0）、U1具体路径及权重、评价入口数值与安全入口状态集合及其保证方法、真实应用与数值、具体MILP／启发式规则。超出声明范围的请求如何处置未建模，不默认拒绝或丢弃。温度入口集合、马尔可夫过程、稳态分布、在线选配均不能因上述原则确认而默认加入。

**变更方法：** 后续若调整D04等选择，新增一项写明“替代／修订D04”、调整原因、用户确认和受影响材料；D04保留原文并加后续关联。当前摘要随新决定更新，证据记录只追加。必要时标明“用户理由”或“助手建议理由”，避免把建议补写成用户原话。

**后续核查（不新增选择）：** E414／讨论稿附录F将D08持续安全和D11／D13的计时规则落实为输出契约；未将某种状态集合、保守界、运行时准入或证明算法登记成用户已确认方法。

**分析路线核查（不新增选择）：** E415／附录G提出可继承的期限与热分析路线及充分条件；属于推导和方法适配建议，不新增已确认决策编号，不承诺MILP可直接表达全部保证。

**用户审查纠偏（2026-10-07，E416）：** 共同温度范围只是充分检查，不定义原问题可行域；更精细持续保证尚未完成，不能称只剩实现；MILP候选层、外部分析器及结果保证必须分开。已据此修正文稿并合并一页定义。此记录收紧研究表述与完成判断，不改变D01—D13模型选择，也不改动D14会话协作分工。

### S1核查结果：离线共同规划的对象与输出（2026-10-06，E400）

**已确认范围：** 用户接受离线共同设计各模式的执行方案及允许转换的衔接方案，运行时依据模式请求执行预先确定的安排。实际切换序列不必预知，但任务模型、允许转换及支撑保证的运行条件必须预先给定。这将原“有限实际请求及到达全部已知”调整为“模式任务模板及允许运行条件已知”；是本阶段已获确认的范围调整。原R86及历史实验仍按原对象解释，不改写其历史结论。

| 环节 | 本题拟采用的职责 | 尚未确定的部分 |
|---|---|---|
| 离线输入 | 各模式任务与依赖、合法设备／工作点及响应、允许转换、实时要求和热参数 | 模式具体差异、重复执行／到达条件、转换时机、驻留及入口状态范围由S2—S3确定 |
| 离线决策 | 各模式设备／工作点／相对执行安排，以及与前后模式相容的转换衔接 | S2已采用旧工作完成后切换、不跨模式重叠；准备／搬运等代价仍待按给定协议确定，不能直接移植Jung的全部迁移语义 |
| 离线输出 | 模式方案、转换方案、适用条件与相应时限／热保证范围，能量评价按S3约定 | 同模式是否需多个温度表项、怎样覆盖连续转换仍待研究，不承诺任意切换都安全 |
| 运行时职责 | 识别外部模式请求、核对执行条件、调用已定方案及执行转换；不重新运行MILP／启发式搜索 | 若以后需要按温度选择候选或拒绝转换，须明确列为运行时决策并另行讨论 |

**与原文的关系：** Jung§2.2／图2用双模式不同时间与速率、跨模式映射变化解释转换代价；§4给定有限模式图、WCET、MRC和迁移代价，静态方案重复运行，模式决定可在运行时产生；§5分析转换对整体吞吐的影响。其已有能力是离线共同设计模式映射与时序并评价转换，本题不能把这一点单独作为贡献。本文拟研究的差异在跨模式热状态、完整能耗及实时要求的共同评价，具体价值与保证范围由S2—S3展开。

**保证边界：** 单独证明A→B和B→A在各自指定入口温度下安全，不足以保证反复切换安全；出口热状态必须落入后续方案的适用范围。S1只确定需要输出这种条件及证据，不提前构造热保证或能量权重。

**用户选择与下一项：** 已选择“接受这一离线边界：继续研究模式方案及转换条件的共同设计”。完整已知序列保留为备选。S2进展见下；不默认采用运行中迁移、旧工作丢弃、候选准入或按温度在线选配。

### S2已确认的取舍：热状态与节能优先（2026-10-06，E401）

**用户要求：** 侧重热状态与节能，切换等待不是研究重点，避免增加复杂度。按此取舍，首版采用旧工作完成后再启动新模式；Stage仍不可抢占、执行中不迁移。各模式可采用不同设备／工作点，转换衔接遵循给定协议，不另设跨模式重叠或主动冷却等待的优化机制。

**重点研究的关系：** 前一模式的设备、工作点和执行安排影响出口温度；后一模式继承该热状态，其可行配置与能耗随之改变。因此离线共同选择各模式方案，研究满足实时与温度要求的节能取舍。旧工作完成不代表温度恢复环境值，也不意味着各模式可彼此独立评价。

**转换代价的处理：** 完成旧工作所需时间，以及必要准备／搬运的时间、能量和功率仍计入评价与时限检查。它们按给定规则或配置相关代价输入处理，不默认为零，也不以重置请求起算时刻掩盖等待。此取舍不取消模式内部原本合法的调度等待；不把转换延迟最小化另列为研究目标。

**原文依据与剩余事项：** Jung§7.1的Blocked对照提供旧模式全部完成后启动下一模式的处理方式，仍允许跨模式映射不同；本题借用这一执行边界，不继承其全部迁移和吞吐设定。S2目前确认的是转换原则，尚需简要明确模式任务差异、重复执行与驻留条件；未确定数值或保证任意切换。下一小步仅补齐这些最小语义，再进入S3的热状态与节能评价，不展开切换等待方法设计。

### S2最小任务语义（2026-10-06，E402；轮次边界已确认，其余为建议）

**概念区分：** 应用模式描述当前要执行的任务模板及服务要求；执行配置描述用哪些设备、工作点和时序完成它。同一应用模式可以有多个可选执行配置。不同模式可由启用的工作流集合、输入规格或给定请求周期／期限区分；无需同时改变这些因素，也不把单纯更换频率称为应用模式切换。

| 项目 | 首版建议 | 来源与边界 |
|---|---|---|
| 模式内工作 | 每种模式给定一轮有限请求DAG、合法支持与响应；图内划分固定，轮内可有多个请求并发 | 保留当前DAG基础；Jung§4提供逐模式任务集合及参数，但本题不直接移植SDF令牌语义 |
| 重复执行 | 首版各轮工作在本轮内完成，轮次之间不交叠；轮内允许并发，重复调用离线方案 | 不交叠轮次是本题已选择的首版限制，非Jung的一般规则；周期与请求释放／期限须按实际服务需求确定，适用性触发条件见下 |
| 转换与驻留 | 允许转换图给定；在完成当前轮次且满足输入的最少驻留轮数后，依给定协议执行允许转换 | Jung§4的MRC为已知最少迭代次数；本题只拟借用输入组织，不优化驻留时长，不默认存在某个实际系统数值 |
| 请求与转换时限 | 释放与期限由工作负载／转换协议预先定义；不能用推迟释放来隐藏转换阻塞 | 若实际输入不可暂停、会跨边界积压，则不满足此简化，需另议；未假定可丢弃请求 |
| 温度 | 同模式重复及跨模式转换均继承热状态，轮末空闲和转换过程按实际功率推进温度 | 给定最少驻留不能证明热安全；无最长驻留时还需覆盖持续运行，留给S3评价 |

**概念例子：** 模式A每轮运行一个固定识别工作流，模式B每轮运行该工作流及另一个固定分析工作流；这是帮助区分任务模式与执行配置的示意，不指定真实模型或支持关系。离线可共同选择A、B各自的设备与工作点，研究A留下的温度如何改变B的可行性与能耗，反向影响A的选择。

**当前停点：** 用户同意以热状态与节能为主、首版不增加跨轮流水线，并要求保留应用适配时重新审查这一限制的条件。该选择仅确认轮次边界，未同时冻结具体模式、周期或最少驻留轮数。实际模式序列仍不要求提前知道；目标能耗的统计口径由S3另行明确。

**范围区分：** “不跨模式重叠”与“不跨同模式轮次重叠”是两项独立限制。首版均采用；周期由服务要求给定，不能由优化器任意拉长以降温。轮内多个请求仍可并发，轮末空闲仍计能量并延续温度。

**必须重新审查的触发条件（用户明确要求）：** 选定具体应用及服务指标时，检查不跨轮重叠是否能够满足其请求到达率／帧率、期限和允许积压。如果必须让多轮重叠才能满足既定服务需求，就重新讨论该限制，不能为保留简化而擅自降低帧率、延长周期／期限或丢弃请求。复核结果应写入应用适配记录；需要开放跨轮重叠时再与用户确定范围，不自动扩大模型。

### S3评价方案：热状态连续，能耗按使用过程共同评价（2026-10-06，E403—E405，目标已确认）

**结论：** 实际切换序列未知，不妨碍离线设计各模式方案，但必须声明节能评价所依据的使用条件。仅给模式占比不足以确定R86温度漏电下的能耗；即使A、B占比相同，长驻留与频繁交替也可能产生不同温度及能量。

| 已核来源 | 可借鉴内容 | 本题需要补充 |
|---|---|---|
| Huang／Xu，DATE 2010，§2.3式(1)、§3.4 | 每模式选一个方案，按使用份额／其分布形成共同节能目标；式(1)为活动能量除以整图期限的单位时间口径 | 不直接照搬为本题总焦耳数；原目标未按逐条转换轨迹累积瞬态漏电，本题需要热历史与完整计量 |
| Dziurzanski等，2017，§3.3、§4.2 | 模式运行能耗与迁移量共同权衡；转换概率影响其优先设计顺序 | 概率在该文中不等于完整的期望转换能量表达，更不能据此删除低概率转换的热安全要求 |
| Jung，TODAES 2017，§4—5 | 允许转换图、最少驻留轮数、重复执行与转换过程 | 提供允许运行条件，不能单凭转换图与最少驻留次数确定平均能耗 |

**最小评价契约（建议）：**

1. 每模式的设备、工作点和相对时序方案离线共同确定；同一组方案用于全部评价过程，不按每条过程预知的未来分别重选。运行时按方案执行。
2. 温度从前轮出口经过轮末空闲／给定转换过程传到下一轮入口。R86规定空闲保持工作点，因此相关域工作点也须按实际规则衔接，不能只传温度却重置空闲功率。转换开销是否非零仍需输入依据，不自行补数值或改写R86历史设定。
3. 计量包括模式工作、轮末空闲和已声明转换过程的全部系统功耗，温度漏电随轨迹积分。每种评价过程的工作量、请求释放、期限和评价窗口由输入固定；各方法一致，不能通过减少任务、改变模式使用量或提前截断窗口节能。
4. 热安全与平均能耗分开：每条纳入保证的运行过程都必须满足期限与连续温度上限，不能用低概率或其他过程低温抵消违规。有限代表过程只直接支持其自身；若声明覆盖所有允许转换及任意重复运行，需要证明初始状态被覆盖、模式内安全、可达出口与后继适用入口相容。该保证构造尚未完成，不据最少驻留或若干安全配对自动成立。

**推荐待选目标：典型使用节能。** 给定一组代表性使用过程h（含模式顺序、驻留／重复条件、入口状态和固定窗口），其权重w_h由应用记录或明确的评价假设提供，和为1；最小化J=Σ_h w_h E_h，E_h为该共同方案在过程h上的完整积分能量，单位J。有概率依据才称期望能耗，否则称加权评价能耗。使用过程作为离线设计与评价依据，不宣称实际未来必定按其中一条执行；未覆盖过程的节能效果仍需验证。该方案借鉴Huang的共同加权思想，但按热历史评价使用过程，是本题适配建议，非原文已有公式。

**备选：最不利使用节能。** 在明确的服务量、窗口、初始状态及允许过程集合内，最小化最坏过程能耗。它更保守，也需要明确过程集合与完整覆盖；不能在无界运行时长上直接取总能量最大值。本轮不同时发展两种方法。

**贯穿例子：** A有偏重NPU的低活动能量方案，也有更多使用CPU的方案；B也偏好NPU。若前一种A方案留下较高NPU温度，B的漏电或热安全要求可能使这组配置不划算。离线共同设计可以选择另一组A、B方案；这不要求运行时按温度重新选配。若热影响弱、配置选择不变，独立方案可能已经足够。

**此前停点：** E403提出典型使用加权／最不利使用两选一；用户现已选择前者并要求声明范围内安全，确认后的契约见下。未设权重、序列、热范围或数值，未把保证范围升级为所有无限转换。

**不以复杂度为依据的推荐（E404，随后获用户接受）：** 优先考虑“使用条件下的加权／期望能耗最小化＋声明允许范围内的期限与热安全保证”。前者回答正常使用能省多少电，后者保证低概率运行也不能超温；二者不是二选一。只有应用要求每次任务／任意允许使用过程都满足硬能量预算，或缺少可信使用统计且设计诉求明确为最坏耗电保障时，才优先考虑最坏能耗目标。无统计依据时，加权指标仅是声明使用条件下的评价，不称真实用户期望。Schmitz等TCAD 2005§V—VI提供概率加权功耗与各模式实时约束的直接先例；Schor等RTAS 2012§III—IV提供不确定负载下最坏热界分析。二者并非本题跨模式瞬态热节能方案的现成整体实现；仍需适配工作点、漏电、允许过程及状态衔接。

### S3确认后的评价契约（2026-10-06，E405）

**用户选择：** 按实际使用情况优化平均能耗，同时对声明的允许运行范围保证热安全和期限。最坏能耗最小化不作为当前目标；不增加在线优化、跨轮流水线或切换等待策略。

| 输入／输出 | 用途 | 需要提供的内容 |
|---|---|---|
| 模式任务与服务要求 | 确定必须完成的工作 | 各模式固定工作流、响应、请求释放／周期／期限；不是由节能优化器选择少做哪些工作 |
| 使用统计 | 定义平均能耗目标 | 模式顺序、驻留／轮数及入口条件的运行记录或统计模型；仅有模式占比时，仍需补足影响热历史的信息 |
| 允许运行范围 | 定义硬约束覆盖对象 | 允许转换、驻留／重复范围、初始温度及工作点范围、时间覆盖范围；低频但允许的过程仍纳入 |
| 共同设计结果 | 运行时直接执行 | 同一组各模式设备／工作点／时序方案及给定转换协议下的适用说明；不得按评价过程的未来分别重选方案 |
| 评价结果 | 区分收益与保证 | 平均能耗及使用条件；期限／连续热安全的覆盖范围与证据；未覆盖或未证部分单列 |

**目标的简写：** 记全部模式方案为Π，一段使用过程为h。以同一给定观察时长W评价时，E_W(Π,h)=∫₀ᵂP_sys(t;Π,h)dt，单位J；目标为min_Π E_{h∼D}[E_W(Π,h)]。D描述使用过程的分布；没有统计依据时，采用声明的代表过程与权重只能称加权评价能耗。W是评价时间尺度，不是实际未来已知，也不是模式周期；同W下平均功率目标仅相差常数W，不能把J与W混写。此处给出量纲一致的有限窗口表达，不冻结W数值或把它等同长期稳态目标。

**约束的简写：** 对声明范围H_allow内的每个过程h，完成要求内的请求、遵守资源／频率域规则，并在所声明时间范围内使各节点温度不超过上限。D的支持应在H_allow内；H_allow还可包含代表记录未出现的允许过程。样本上全部安全不等于全范围保证；最坏温度的过程也不必是最耗电的过程。

**状态衔接：** 同模式重复、轮末空闲及跨模式转换均延续温度，空闲工作点按既定规则传递。若未来声明任意次数重复／切换安全，需要证明可达出口仍落入后继方案适用范围；若只完成有限窗口分析，则明确限定为该窗口。安全覆盖时长与节能评价窗口分别登记，不用一个含糊的“全过程”替代两者。

**公平评价：** 对同一h，各比较方案采用相同工作量、实际释放／期限、入口条件与观察窗口；所有要求在窗口内完成的工作都必须完成，不把任务推到窗口外制造节能。工作、空闲、温度漏电及已声明转换成本统一积分。使用分布、权重和服务要求均是输入，不随求解结果调整。

**例子：** 常用A的较省电方案留下较热NPU，随后B即使较少使用也必须安全。离线共同选择可以在“A稍多耗电、使B可用更节能方案”和“A保持原方案、B采用更保守配置”之间比较加权能耗；两组都要满足声明范围的约束。运行时不需要预知未来或再求解。哪组更好由参数与使用条件决定。

**阶段完成：** S3的目标、硬约束含义及所需输入已明确，未冻结实际应用、分布、温区、驻留上下限或无限时间保证。S4随后完成讨论稿，见下；不把补齐实测数据作为构想准入门槛。

### S4讨论稿已交付（2026-10-06，E406）

用户澄清目前仅与助手交流，并要求总分结构、分点表达与例子。新稿约2600汉字，采用“总的想法—A/B贯穿例子—问题变化与文献支撑—拟做工作—验证—待判断事项”的组织；供用户讨论，不是导师意见或正文定稿。区分模式需求与执行配置、平均能耗与安全覆盖、离线共同方案与预知未来的逐轨迹重选；保留不跨轮重叠的重新审查条件。

拟开展的自主工作集中为模式间热状态与能耗的共同表达、评价／保证接口、对应求解与验证，不把借入模块直接称为算法创新。MILP参照与启发式只定职责，温度漏电下旧连续热反馈约束的有效性待适配核查。用户随后认可主线，纠正“必须先选实际应用”的推进建议；当前先做抽象模型定义，见下。

### 模型定义整理：不新增简化（2026-10-06，E407）

在方案讨论稿附录A区分应用模式、Stage执行模式、模式执行方案及使用过程，并整理输入／决策／派生状态／约束。实际应用不是前置条件；不固定模式数、Stage数、频档数或概率，不把定义过程变成继续删减研究范围。

已核查三项接口：外部切换请求不能与派生的模式进入时刻混用；平均能量评价窗口与安全覆盖时长分别定义；R86零Stage交接开销与待定模式准备开销不混写。前者防止通过改变释放或少做工作制造节能，后两项防止自动引入非零开销或无限保证。尚未选择具体的随机过程或安全覆盖表示，不新增马尔可夫假设、稳态假设、在线温度选配或冷却等待控制。下一项只讨论安全范围的有限／持续含义，已有文献核查服务于这个范围判断，不扩展机制。

---

**2026-10-06基于成熟模型适配的推进确认（E399）。** 用户要求模式、转换与热状态范围依据已有文献确定，再核对离线规划、温度感知及MILP／启发式的适配，不能凭空选择。本轮回核Jung正式版§4—5：有限模式及转换图、模式内任务／端口参数、最少驻留迭代、迭代边界转换和状态保持均有原文定义；原目标为吞吐约束下减少处理器。建议先以其任务／转换语义为主参照。关键待确认是“离线生成各模式方案、运行时照表转换”与原“全部请求及到达预先已知”的区别，不能默认两者完全一致。下一小目标只解释并比较这两种输入／执行边界，再选择可继承的模式语义；不改R86、正文或实验。

**2026-10-06研究现状正文改写（E398）。** 按用户指定直接写入[Markdown讨论稿](research/国内外研究现状与本文问题定位_讨论稿.md)，将分类提纲及旧三类叙述改为“总述—四类研究—综合评述”的连贯正文，约4100汉字，选用18篇代表文献。76条材料索引移至附录；文内引文与参考条目对应、本地链接及索引覆盖已核。问题定位按当前优先讨论的多模式方案与转换条件写为拟研究内容，未确定新模型假设或收益；未改LaTeX、程序、参数或运行实验。下一项先审阅正文叙述及问题定位。

**2026-10-06研究现状分类整理（E397）。** 在[国内外研究现状讨论稿](research/国内外研究现状与本文问题定位_讨论稿.md)前部新增“四类主干＋基础／备选索引”：异构推理配置与协同调度、温度感知运行管理与热安全、期限约束下的热感知调度与节能规划、多模式运行与转换共同设计。归类覆盖逐篇笔记的76条材料记录，指定正文代表及段落顺序；保留原三类叙述和固定工作流定位。多模式仍是讨论入口，未改变R86或确定最终题目；不新增检索、实验或正文修改。下一项可按分类压缩代表文献、形成研究现状段落，不自动开展。

**2026-10-06三篇多模式材料连续阅读完成（E394–E396）。** 按用户授权无需逐篇确认，已分别追加[§81多模式节能与迁移](research/逐篇文献阅读笔记.md#modal2017逐篇阅读)、[§82 Omni](research/逐篇文献阅读笔记.md#omni逐篇阅读)、[§83多模式可靠性节能](research/逐篇文献阅读笔记.md#huang多模式节能可靠性逐篇阅读)。第一篇提供运行能耗—转换代价取舍，Omni提供所有前驱及转换残余需求分析，第三篇提供模式使用份额下的共同目标与候选选择。各自实验、无收益条件及离线／在线边界已核，三份本地PDF预检PASS；表述／数值疑点就近登记。第二种“离线设计各模式方案及转换条件”仍优先，已知完整序列为备选；未改R86、正文、程序或参数，未运行实验。三篇已全部完成，下一项仅讨论要保证的转换条件与入口状态范围，不自动扩检索或设计算法。

**2026-10-06讨论优先级与参考核查（E393）。** 用户选择重点讨论“离线设计各模式方案及转换适用条件”，将“给定一条完整已知序列”保留为备选。新增[笔记§80](research/逐篇文献阅读笔记.md#离线多模式方案与转换参考)：2017多准则模式资源分配提供节能—迁移权衡，Omni RTSS 2022提供模式转换可调度分析，DATE 2010提供多模式共同节能目标的组织。下一篇建议先读2017；温度适配仍需讨论入口状态范围、驻留／切换语义及评价权重。此为研究对象讨论优先级，不是已改写R86或批准运行时重新优化；不开展实验、算法设计或新增长报告。

**2026-10-06新下载两篇已读（E392）。** 新增[笔记§78多速率数据链](research/逐篇文献阅读笔记.md#verucchi多速率数据链逐篇阅读)与[§79多模式转换](research/逐篇文献阅读笔记.md#jung多模式转换逐篇阅读)。RTAS 2020共同生成多链实例依赖、分析时效并构造静态安排；TODAES 2017正式25页版补齐模式重叠、转换推导、GA与带反馈的Base对照。两篇均有问题组织价值：前者增加数据时效语义，后者共同处理各模式及其转换。旧§77预印本阅读范围保留，正式版依据转至§79。当前只继续讨论与离线对象的适配，不恢复跨场景、不新增模式／算法或实验。

**2026-10-06研究对象层面的开放补查（E391）。** 按用户要求放宽文献领域，寻找原本分开处理的对象如何形成共同决策，新增[笔记§77](research/逐篇文献阅读笔记.md#决策对象扩展补查)：多速率数据链时效（RTAS 2020）、模式及转换共同规划（TODAES 2017／Omni RTSS 2022）、计算与存储策略联合选择（POET／XEngine），可靠性重执行仅备查。已核关键正文及公开下载入口，非逐篇通读完成。采纳用户判断：§74改成一次性已知请求规划后，候选流程本身不构成新上层问题。建议下一篇先读RTAS 2020，再由用户评价；未选定方向、恢复跨场景或改变R86，没有新实验。

**2026-10-06逐篇阅读继续：RTCSA 2009周期热节能已读（E390）。** 追加[笔记§76](research/逐篇文献阅读笔记.md#wang热约束周期节能逐篇阅读)：单处理器周期工作、首尾热闭合、收敛周期能量和最优控制速度轨迹。恒速安全时已有简单解；热活跃时平滑／分段控制。原例安全能量4.383→4.206 J，约4.0%，属声明模型；实验内部能量比与节能率分开。通过已知作者入口取得9页全文并单独归档，不改原`.crdownload`；只读核发现两者差1个尾字节、全部页面文本一致。持续节能关系有直接价值，执行中调速不直接移入R86。本批三项对应正文已读完，下一步按用户评价比较，不自动扩文献或运行实验。

**2026-10-06逐篇阅读继续：DATE 2016流水线峰温已读（E389）。** 追加[笔记§75](research/逐篇文献阅读笔记.md#cheng流水线峰温逐篇阅读)：持续输入、固定阶段／频率，离线选周期工作／休眠时长；PBOO整体期限分析减少逐阶段重复突发估计，配合温度漏电／热耦合评价及梯度启发式。原文最高15°C为4阶段ARM模型峰温差，不是节能率；GD／穷举一致属测试结果，凸性仅为作者猜测。完整期限分析、持续热积累和对照组织有价值，直接异构节能配置方法有限。两份新完整材料已读完相应范围；RTCSA 2009本地文件仍为`.crdownload`。保持R86，不运行实验或扩展机制。

**2026-10-06逐篇阅读继续：热可组合映射已读（E388）。** 新下载`2019_System-Level_Mapping_Analysis.pdf`实际为Pourmohseni的222页博士论文；本轮完整读取对应RTSS 2019工作的第4章，追加[笔记§74](research/逐篇文献阅读笔记.md#热可组合映射逐篇阅读)。核清TSPD／TSU、组合准入及候选生成中的热安全背景余量目标：价值在单应用保证如何组合、候选适用范围与保守性，不是总节能率。实验为52核建模平台，热准入及热感知DSE分别验证；本章TSU按总活跃核数定义，不混用会议报告口径。当前`papers/`71份完整PDF，下一篇DATE 2016流水线峰温优化；RTCSA 2009仍为`.crdownload`。本轮不改R86或运行实验。

**2026-10-05上层问题角度定向补查（E387）。** 按用户最新要求，寻找类似“单场景→多场景”的研究对象／保证范围变化，整理[笔记§73](research/逐篇文献阅读笔记.md#上层问题角度补查)：应用热保证的组合、可持续重复执行、模型驻留与计算共同组织。热可组合RTSS 2019已补读作者博士论文对应正文；RTCSA 2009／DATE 2016提供周期与流水线工具，SwapNet TMC 2024承接101号复核。明确持续／驻留不是首次讨论，不包装旧入口为新发现。三项用于下一轮阅读讨论，未选定新主线、改变R86或运行实验；建议先读热可组合的问题组织，再决定是否有必要改变保证对象。

**2026-10-05逐篇阅读继续：SensiX++已读（E386）。** 追加[笔记§72](research/逐篇文献阅读笔记.md#sensix逐篇阅读)：共享预处理／特征缓存、部署时设备负载均衡与在线批量调整，目标为时延要求下的有效吞吐和服务效率。保留共享计算与声明式合法设备接口的价值；没有热约束／DVFS优化，总能耗比较没有显著差异，不能归为节能结果。27页本地全文已读，当前`papers/`69份PDF均已有阅读记录（RT-TAS重复文件合并）；下一项按用户评价整理借鉴优先级，不自动新增检索、模型机制或实验。

**2026-10-05逐篇阅读继续：RTAS 2020动态热条件已读（E385）。** 追加[笔记§71](research/逐篇文献阅读笔记.md#动态热条件逐篇阅读)：按环境温度确定可保证的服务等级，以执行预算与冷却余量分离热安全和期限分析；保留最坏功率包络、预算边界连续执行和冷却后恢复的具体价值。它采用固定CPU分配、抢占及低关键任务暂停，不是节能或CPU／GPU／NPU联合配置方法。本地14页全文已读，下一篇SensiX++ TECS 2023，为当前`papers/`队列唯一尚缺独立逐篇卡的材料；不改模型或运行实验。

**2026-10-05阅读队列纠正。** 用户提醒尚有未读材料，重新核对当前`papers/`：69个PDF，其中67个已有逐篇记录（RT-TAS两个文件合为一篇），另有新下载的`2020_On_Dynamic_Thermal_Conditions.pdf`和`2023_SensiX++_Bringing_MLOps_and_Multi-tenant_Model_Serving.pdf`。两篇此前只在笔记§64定向核过部分正文，尚未完成独立逐篇阅读。下一篇优先RTAS 2020动态热条件，再读SensiX++；上一条“七篇读完”仅指该批七篇，不代表当前全部本地材料已读完。

**2026-10-05逐篇阅读继续：MapFormer已读（E384）。** 追加[笔记§70](research/逐篇文献阅读笔记.md#mapformer逐篇阅读)：多DNN划分／映射／组件频率共同搜索，Transformer完整配置分类评价＋LA-MCTS；保留评价／搜索分工与权重实验的价值，不采用其学习器作为当前首选。90.8%定位到10 DNN／10 W相对MOSAIC能效，约23 s为配置搜索。没有温度或请求硬期限。本批七篇已逐篇读完，下一项按用户评价整理借鉴优先级；不改模型、正文、程序或参数，不运行实验。

**2026-10-05逐篇阅读继续：AxoNN已读（E383）。** 追加[笔记§69](research/逐篇文献阅读笔记.md#axonn逐篇阅读)：单NN在能量预算下逐层选择GPU／DLA，profile刻画转换及融合／流水线代价，Z3求低时延映射。保留完整映射评价、合法边界及约束求解的价值；不含温度／DVFS／多请求共同时序，能量计量边界尚不充分。下一篇MapFormer本地全文；本轮只读与记录，不改模型／正文／程序或参数，不运行实验。

**2026-10-05逐篇阅读继续：Huang／Quan DATE 2011已读（E382）。** 追加[笔记§68](research/逐篇文献阅读笔记.md#huang-quan逐篇阅读)：单处理器周期工作量的两工作点交替，闭式温度／能量评价与切换次数搜索，计入电压／温度漏电及转换开销。保留评价工具、净收益权衡和“计算工具—调度效果”分开验证的价值；运行中切频、长周期和单节点不直接移植，原式排版／符号问题登记。下一篇AxoNN本地全文；不修改当前模型、程序或参数，不运行实验。

**2026-10-05逐篇阅读继续：Chantem已读（E381）。** 追加[笔记§67](research/逐篇文献阅读笔记.md#chantem逐篇阅读)：硬实时DAG联合映射／非抢占时序，主目标为峰温；MILP采用分阶段稳态，短任务及等待冷却由瞬态TAB／iTAB处理。保留模式表、MILP表达、余量列表排序及热预测工具价值，登记延迟插入的正例、无收益与负例。下一篇Huang／Quan DATE 2011漏电节能；不改模型、代码或参数，不运行实验。

**2026-10-05逐篇阅读继续：Bao ITD已读（E380）。** 追加[笔记§66](research/逐篇文献阅读笔记.md#bao-itd逐篇阅读)：给定单处理器次序／工作点，在期限及温限下优化空闲分配与漏电能量；离线温度分析和简化优化交替，在线另用预计算LUT。保留同配置不同等待的热能耗关系、切换净收益及对照设计；周期稳态、低功耗空闲语义与本题有限入口／工作点保持需适配。下一篇Chantem TVLSI 2011；本轮不改模型或运行实验。

**2026-10-05逐篇阅读继续：PELSI已读（E379）。** 追加[笔记§65](research/逐篇文献阅读笔记.md#pelsi逐篇阅读)：期限约束下单CNN逐层设备／频率联合选择，GA执行前搜索完整配置，profile评价包含交接及调频生效延迟。保留逐层响应、完整代价评价及成熟框架扩展方式的具体价值；温度与多请求共同安排需要另行适配。阅读队列下一篇Bao TVLSI 2012；其他问题视角讨论记录保留，本轮不改模型、正文、程序或参数，不运行实验。

**2026-10-05问题视角网上补查（E378）。** 用户要求寻找类似“单场景→多场景”的上层研究角度。定向核查Mainstream、SensiX++、Ekya及RTAS 2020动态热条件正文，结果集中在[逐篇笔记§64](research/逐篇文献阅读笔记.md#问题视角变化网上检索)：共享计算图、推理与重训练共同资源、环境条件下的服务保证。前两类会涉及共享工作图或训练范围，热服务原法允许分级暂停；这些差异用于讨论，不自动修改R86或选定新方向。下一项建议精读RTAS 2020的问题组织；原PELSI阅读队列保留。

**2026-10-05逐篇阅读继续：ARM-CO-UP已读（E377）。** 七篇新PDF已在`papers/`，总计67份。首篇记录追加到[逐篇笔记§63](research/逐篇文献阅读笔记.md#arm-co-up逐篇阅读)：区分跨帧流水线与单帧逐层设备切换，保留profile、转换代价、DVFS／宿主CPU及GA接口的借鉴价值；温度与多模型共同规划不是本文范围。下一篇PELSI；只读材料，不改模型／正文／程序或参数，不运行实验。

**2026-10-05文献补充下载清单。** 按用户阅读评价，新增建议ARM-CO-UP、PELSI、Bao TVLSI 2012、Chantem TVLSI 2011及Huang DATE 2011；AxoNN／MapFormer作为已在线核查但未本地归档的补下载项。[清单与全文链接](research/逐篇文献阅读笔记.md#网上补充下载清单)登记目标、变量、借鉴用途和阅读位置。本轮只检索与整理，不改当前路线、模型、正文、程序或参数，不运行实验。

**最新完成（E375）：第三章模型研究稿、方法接口与独立审查。** 按用户goal修改唯一正文[chapter03.tex](research/latex/chapter03.tex)的3.2—3.5，严格沿用R86-v1，统一完整请求、合法模式、共享域、空闲保持、温度漏电与逐CPU单元热评价，目标为E(m,s)。MILP／评价器／启发式的共同接口及未决适配见[检查记录](research/第三章模型与接口检查记录.md)。V0后一次V1修订，独立审查四项意见全部关闭，未使用V2。没有运行实验或修改研究输入／程序／历史结果。

**当前阅读入口与停止点。** 新编译PDF为[main_model_review.pdf](research/latex/build/main_model_review.pdf)，37页；原build/main.pdf被占用，仍为旧版。3.6—3.7保留恒功率、二聚合节点历史特例，不能视作R86验证。下一项仅审阅本稿与接口，再制定工作点保持、漏电能量及多节点连续热评价的最小实现检查；不自动进入实验或重新筛选方向。以下E374等为历史阶段状态。

**最新优先级：完成硕士毕业论文，停止无休止的创新筛选（2026-10-03，用户明确纠正）。** 用户希望借鉴融合几篇成熟论文，以MILP及启发式算法完成模型、方法、实现与实验，接受范围明确的小幅改进；并不要求全新机制或先证明旧方法不足。后续以可完成性、技术正确性、自主工作和可写作性组织推进，真实记录来源、无收益与未决结果，不承诺新颖性或毕业。

**导师反馈后的当前安排（E373）：保留选题，先明确自主工作和有限验证计划。** 导师认为问题有价值、创新尚待落实，要求对照Zhou／Li并补入MEDEA，明确方法、模型适用性及公平实验。用户已与导师确认**后续只做仿真实验，没有实机验证要求**。不把实测响应、真实设备收益写成已经取得，也不重新展开方向筛选。

**当前小目标已完成：Zhou／Li／MEDEA对照及一页自主工作任务卡（E374）。** 用户启动goal后，交付[近邻对照与自主工作任务卡](research/近邻对照与自主工作任务卡.md)，原文事实、算法组织与本题适配分别列明；卡集中在§3，明确共同期限内设备／工作点与执行、等待时序的热能耗协调，以及模型适配、MILP参照、启发式实现和公平仿真的自主工作。共享域和任务响应是约束／代价，不分别凑创新点；没有新增机制或编号长报告。

**当前停止点：审阅任务卡，不自动进入实现或实验。** 三篇均有可读正文，无需补下载。Li本就联合定义映射／速度／起点，其第二阶段固定映射／次序是方法组织；MEDEA的串行配置ILP不能直接代替完整DAG热参照。R86含温度漏电与工作点保持，一般为E(m,s)，现有恒功率MILP仍需明确适配范围。用户确认卡后，下一项仅确定共同模型与MILP／启发式分工；不以必须证明旧方法失效为准入条件。导师提出的争用、切换和预测误差仍属适用性／敏感性需求，不自动改R86。

MEDEA已定向核当前v3正文：单模型、固定内核列表、严格串行，离线选PE／V–F及tiling；§3.3式(10)—(13)的ILP未显式加入温度状态或热上限。其与本文的并行／热评价范围不同，但不替代与Zhou／Li的近邻比较，也不据此直接认定创新。准确出处、版本和参数性质见E373。下列goal交付及旧停止点为历史记录。

**上一goal已完成起草与独立审查：国内外研究现状与本文问题定位讨论稿（E372），已收到导师反馈。** 交付[讨论稿V1](research/国内外研究现状与本文问题定位_讨论稿.md)，按师兄1.2的“总述分类→逐类研究进展与比较→综合评述→本文共同问题”展开，分为协同推理与端到端时限、推理热管理、DAG热能耗调度三类。九项来源定位正文，正面论证研究价值；内部边界和意见集中在[审查记录](research/国内外研究现状与本文问题定位_审查记录.md)。该轮保持协同多模型完整请求及R86-v1，不改论文正文、模型、程序或参数，不运行实验、不设计算法。

**本轮完成与停止记录：V0首稿＋一轮V1修订，未使用V2。** 未参与起草的新智能体直接读取师兄1.2、稿件和九项关键来源，指出五处局部问题；统一修订后直接复读V1，五项既定标准全部通过，无严重阻断。已校正Band小节定位、Tan两方法归属、Li温度目标与硬约束区别，并补齐固定窗口和给定模型结论范围。当前停止于用户审阅，不自行进入算法、实验或新的立意筛选；起草验收不代表最终立意或新颖性获得批准。

**历史E371四段稿未获用户认可。** 用户指出空泛、结构不清及支撑不足；旧稿保留在[文献对照](research/协同多模型研究问题与文献对照.md#立意讨论草稿)，不是本轮讨论稿的主版本。它不代表立意已获批准，也不代替本轮的分类展开和独立审查。

**上一小目标：协同多模型研究问题的一页文献对照（E370）。** 按协同执行、端到端时限、DAG热能耗、预测／恢复四类区分已有能力与本文适配。HaX／Band已经支持协同推理，Zhou／Li已经具备联合热能耗及余量处理，F-DTM／Maity已有预测和反馈；因此立意落在协同完整请求背景下的共同时间空间、合法执行选择与热能耗评价，不以首次增加某个因素或证明旧方法失败为前提。

**上一小目标：师兄1.2的研究问题定位逻辑核查；主背景已由用户选定（E369）。** 用户选择“协同多模型完整请求”，以多个模型共同产生一个结果为背景，突出端到端期限、分支时间空间与热状态协调。当前优先建立“应用需要→已有研究范围→拟共同研究的问题”的立意，不讨论算法新颖性或要求实验反例。师兄1.2位于根目录main.pdf正文3—5页（PDF15—17页），不是本项目当前research/latex/main.pdf。正文与主要引文已核对，出处及范围见[证据E369](research/03_证据与检索记录.md#e369师兄研究现状的论证结构与主背景确认)。

**上一小目标：将“端侧协同多模型推理”试纳入论文故事（E368）。** 用户要求先立研究问题及整体建模的价值，不提前讨论算法创新；当时将E365背景接入现有构想：多个模型共同服务一次应用结果，分支／后继受同一端到端期限约束，设备、工作点和时序共同影响汇合时刻、后继热状态与系统能耗。HaX／Band提供应用结构，Nexus提供时限协调参照，Li／Zhou、Maity与F-DTM提供建模及方法素材。完整依据和措辞边界见[证据E368](research/03_证据与检索记录.md#e368协同多模型背景接入论文故事)。

当前故事为“完整应用结果的端到端要求→分支时间空间与热历史相互关联→设备／工作点／完整时序的热约束节能规划”。任务相关响应解释不同分支调频代价，作为联合模型的组成部分。共同输出是应用组织，端到端硬期限是本研究采用的约束；HaX运动规划是下游示例，不写成已实现测量。此背景与R86一般DAG相容，不新增机制，也不冻结实际模型、支持集合或数值。

**历史立意阶段停止边界。** 该阶段只推进研究问题与建模立意，不进入算法细化或实验。当前已按E374形成自主工作任务卡，尚未实现新模型／方法；具体工作流、支持集合和数值仍未冻结，R86不变。相似文献用于准确归属与设置对照，算法收益仍留待后续实现、实验。

Li／Zhou、Maity、F-DTM与任务相关响应仍是已核素材；本次明确的是论文完成标准和推进方式，没有自动确定具体算法、冻结Li为唯一主基座或修改R86。E367继承卡保留供简短方案取材，其“尚未证明优于简单方法”是证据状态，不再构成继续形成论文方案的门槛。以下停止点及下一步均为历史，不覆盖本段。

**当前小目标已完成：Li两阶段流程的最小联合问题继承卡（E367）。** 完整卡保存在[证据E367](research/03_证据与检索记录.md#e367li两阶段流程的最小联合问题继承卡)。继承虚拟工作点、DAG／资源可用时间传播、LFT以及降频／冷却延迟工具；分层任务期限、初始映射／资源次序和半余量延迟视为候选构造规则，不先锁死完整请求的合法安排。拟共同问题仍为R86内的设备、工作点与起点选择，在完整请求期限和连续温限下最小化完整窗口能量；任务级期限是辅助时间预算，余量是派生空间，不新增独立优化变量。

应用理由是模式时长、资源次序和后继就绪共同决定可用调整空间；执行位置与功率时序共同影响后续热状态和漏电能量。因此，先前形成的配置需在同一完整评价下核对，必要时允许规划重选。Li原问题本就包含映射／速度／起点，不能把重新组织这些变量写成原文从未联合考虑，更不能把降频或冷却等待单独写成新增。Maity动作、F-DTM预测和任务相关响应均为工具来源；不串接在线控制器，不改R86。

**当前停止点：先审阅继承卡是否把研究问题、应用需要和拟共同决策讲清楚。** 卡已形成可讨论的构想，尚未证明它比固定映射／次序＋正确余量调整或已有联合规划更有价值；贡献、匹配数据和方法规则仍未确定。不自动设计算法、检索新机制或运行实验。E362已标为历史背景备选，K3控制契约已标为历史安排暂缓；E365背景仍未选定。以下为历史阶段记录，不覆盖本段当前任务。

**当前小目标已完成：Li等JSA 2019全文覆盖核查（E366）。** 用户提供全文后，核对§3—5及关键公式／算法页，确认ETA-TS已经组合映射／频率选择、期限余量利用和主动冷却延迟。§5.2在降频后仍有离散频点残余余量时，延迟任务一半残余时间以冷却；算法2遍历全部任务，LFT同时受同处理器后邻任务与直接后继约束。因此，不能将该文只归为减少同步等待，更不能将“首次加入降频＋冷却等待”作为本题差异。

该文可作为具体方法基座：任务级期限、虚拟工作点、资源／后继限制的最迟结束时间及余量处理均有正文。其§3.4问题定义本就包括映射、开始时刻和执行速度；实际算法先形成映射／次序，再在既定安排内降频及延迟，不重新映射／换序。时长仍采用统一反比缩放；热模型式(2)已有耦合，但排序指标采用无传热特例和周期稳态平均温度推导；§3.4／算法1—2未建立R86完整窗口连续温限接纳流程。上述是继承／适配边界，不是旧方法错误或创新成立的证据。

**E366原下一小目标已由E367完成：Li两阶段流程的最小联合问题继承卡。** 卡说明继承规则、拟共同处理的决定与应用需要，并保留已有规划足够的条件。任务相关响应、Maity调整及F-DTM预测作为工具，不预定算法，不启动实验。Li全文缺口已关闭，无须重复下载；R86与E365待讨论背景均未改变，没有新增编号长报告。

**历史背景建议（E365，已按用户要求试纳入当前故事，见E368）。** 当时推荐供讨论的是“具有共同输出与端到端期限的端侧协同多模型工作流”：多个必需分支与后继组成一次完整请求，汇合前安排共同决定后继启动条件和设备热状态。HaX-CoNN §5.2 Scenario 2、Band §2支持这一对象；Nexus SOSP 2019 §4.2／§6.2及Harpagon作者稿§III-D提供复合请求时限协调的已有能力。多速率仅作为释放日历来源，不作为独立创新；持续重复的跨窗热保证未采用。

该背景与R86固定工作流、完整输出及有限已知请求相容，一般DAG已能表达，不称新增模型层级或已证创新。潜在研究关系是共同输出期限内的分支／后继执行、等待和工作点怎样与完整热状态及能耗协调。用户尚未选定；背景核查未改R86／正文／代码／参数，未运行实验或新增编号报告。E364近邻记录保留，Li JSA 2019全文缺口已由E366关闭；未因背景建议跳过覆盖核查，也不将资料缺口作为提出构想的前置门槛。

**当前小目标已完成：融合问题的直接近邻覆盖核查（E364）。** Zhou JSA 2018已包含DAG映射、DVFS、期限、瞬态温度及动态／漏电能量；Coskun SIGMETRICS 2009已协调任务频率敏感性、热状态与DVFS／任务管理；TEEM DATE 2019已有逐应用画像、CPU／GPU配置及运行时热反馈。因此，不将“非统一响应＋映射调频＋温度＋能耗”的因素组合认定为新点。当前待审问题仍是：在R86有限已知完整请求中，共同评价工作点、冷却等待和未启动Stage改配对期限余量、后续热轨迹与完整能量的影响。它有方法基座，但尚未核清具体近邻差异，不否定融合构想，也不自动切回实验找旧方法失效。

**E364资料缺口已由E366关闭：** *Minimizing temperature and energy of real-time applications with precedence constraints on heterogeneous MPSoC systems*，DOI [10.1016/j.sysarc.2019.07.001](https://doi.org/10.1016/j.sysarc.2019.07.001)。当时仅摘要／引言可读，未判定等待语义；现有全文明确主动冷却延迟，覆盖结论以E366为准。其他已核全文不重复索取；E362应用背景仍未选定。

**上一小目标：融合候选的决策边界与接口核查（E363）。** 核清Zhou TCAD 2016固定处理器工作点、采用周期可抢占RM任务，分配与余量处理已带热反馈；Maity TECS 2021已有设备／频率／起点调整和时长表，但依赖子任务边界与周期恢复；F-DTM已有配置查表、未来预测和反馈，固定EDF内核序列，同刻只运行一个可在CPU／GPU内部划分的内核。当前建议仍沿R86：在有限已知完整请求中，共同选择合法Stage模式和起点，比较降频、等待及未启动Stage改配对完整期限、瞬态热轨迹与系统能量的影响。余量是给定安排及约束下派生的调整空间，不预设为可独立分配的总量，不新增休眠或在线控制。

这是待审的联合研究问题，不是已证明新颖性的算法；非1/f不等于已有查表方法不能表达，原排序依据／RM期限分析／稳态均温及在线控制器不直接移植。只补充既有状态和证据，未改R86、正文、程序或参数，未运行实验。下一步若继续，仅定向核查这个具体共同问题的近邻覆盖；E362应用背景仍供讨论，不因本轮核查自动选定。

**历史背景备选（E362）：** 当时供讨论的是“多速率持续视觉感知”：多个固定推理工作流按不同已知更新周期产生完整请求，共享CPU／GPU／NPU；期限余量、资源交错和热历史共同影响节能规划。依据F-DTM的ADAS固定内核／不同周期背景及DynCNN的多路端侧视觉与温升测量，但不照搬其在线变化、停止线程或工作组划分。持续服务是应用背景；按R86只优化有限已知释放计划、给定入口状态，不自动主张无限运行保证。此建议尚未获用户选定，未改变R86或确定具体模型／周期／硬件支持，不作为当前推进目标。

**最新讨论：用户提出Zhou余量／能耗处理＋任务相关响应＋Maity热调整＋F-DTM预测的融合候选（E361）。** 初步建议围绕完整请求期限余量在工作点、热等待与设备重选之间的协调使用，而非三个控制器串接。Zhou已有热检查后重新分配，Maity已有逐任务／频率查表，F-DTM已有预测与测量反馈；这些已有能力不能重报为新增。用户尚未批准采用此候选或改变执行规则；本轮按现有离线已知请求讨论预测轨迹与候选调整，不迁入运行中抢占／迁移、跨周期恢复或新在线到达。下一步如继续，只整理原问题与拟共同规划问题的接口对照，不先运行实验或细化算法。

**当前交流重点：继续核查“端侧推理与热感知配合”的具体研究与可继承方法（E359—E360）。** 用户要求不要急于收敛，不能把泛泛应用动机称为技术基座；F-DTM保留为可借鉴材料，不等于已选定路线。本轮补读RT-TAS（EMSOFT／TECS 2019）、热自适应平台管理（EMSOFT／TECS 2021）和DynCNN（COMPASS 2022），重核Zhou TCAD 2016：分别核清CPU–GPU热耦合下的分配／协同排序、基于期限与资源状态的热恢复、应用需求驱动的GPU并发／频率控制，以及动态能量与温度漏电能量的分阶段优化。只在聊天中比较，出处集中登记于既有证据记录，不新增长编号报告。

“以降低能耗为目标”可以区别于某些以峰温或服务质量为目标的来源，但不能作为与整个领域的区别；已有热感知能量最小化研究。固定优先级、子任务划分、周期反馈、允许减少推理工作量等原文规则不能默迁入本题。当前不选定新组合，不改变R86、正文、程序或参数，不运行实验。K3最小控制契约暂缓，以下104号下一步保留为待讨论安排，不自动执行；下一步仍由用户阅读本轮比较后决定。

**最新：[104号K3联合问题与任务相关响应作用定位](research/104_K3联合问题与任务相关响应作用定位.md)已完成（E357—E358）。** 用户要求继续K3，并提出将非统一1/f纳入讨论的期望。本轮完成ASP-DAC 2019原问题与拟共同规划问题对照：共同安排Stage设备／工作点／时序及电源状态，任务相关响应决定实际缩时，完整依赖与控制域决定缩时能否成为可利用的休眠空档。非1/f已在R86 D1允许范围内，新增的是休眠控制候选，不另开响应模型支线。

已给出空档变化与局部休眠门槛的条件推导；局部缩时不等于域空档增加，跨过休眠门槛也不直接证明系统节能或热安全。新核Coskun SIGMETRICS 2009全文，确认任务响应感知DVFS、DPM与热管理已有组合；ECRTS 2017正文确认强制休眠与热耦合／控制同步已有覆盖。PowerFlow-DNN可直接接收逐层状态时长表。故本轮形成可借鉴的联合问题，不认定这些因素组合即创新；TODAES 2026仅取得局部正文，不承担缺口判断。两篇新增全文已归档，无须用户立即下载。

**历史安排，暂缓：K3最小控制契约。** 原拟整理实际电源域休眠、转换／恢复计费及有限窗口首尾要求，供用户选择后再讨论R86变更；目前不执行。R86仍未改；没有默认批准设备独立休眠、非零转换参数或新实验。算法、章节和其他K候选继续暂缓，不用旧60号结果充当K3验证。

**上一轮：用户选择K3“设备忙闲／休眠／唤醒＋完整调度”进行定向文献基座核查；103号已完成（E355—E356）。** [103号](research/103_K3忙闲状态联合调度的文献基座与决策边界.md)建议以Esmaili等ASP-DAC 2019为调度结构基座，PowerFlow-DNN为端侧推理电源状态材料，TECS 2014补充前身，HPCC 2022核查热管理已有覆盖。已取得三篇作者全文并归档；不需要用户立即下载。

核清：ASP-DAC 2019完整模型已有映射、顺序、起点、DVFS和DPM联合优化，固定映射／顺序只是其启发式步骤；不能重报为模型缺失。PowerFlow-DNN v3已有端侧固定层序列的工作状态与转换联合评价；HPCC 2022已有热状态、DVFS与低功耗态，但在线迁移／热应急丢任务不能原样承担全部请求完成。未认定“再加温度／NPU／休眠”构成创新，未将仅有摘要的近邻写成缺口依据。

**103号原下一小目标已由104号完成：** 以ASP-DAC 2019为主形成K3“原问题—拟共同规划问题”对照卡。R86仍不变；K3若被采用，须讨论R6空闲保持、新增入睡／唤醒成本、实际电源控制域及有限窗口边界。选择文献对象不等于批准这些假设变化。其他K1／K2／K4—K6保留目录，未并行深入；原100号后续实现／验证继续暂缓。

**上一轮：用户保留K1—K3并要求再看三种，102号扩为六组（E354）。** 新增K4“模型驻留／装入释放＋完整调度”、K5“CPU占核宽度＋完整调度”、K6“精确公共计算复用＋完整调度”。三者分别决定数据何时可用、一个Stage占多少CPU资源、哪些相同计算可只执行一次；不混同合批、Stage划分或设备休眠。K4承接101号B，K5仅把暂缓的可变核组列作可讨论假设，K6尚缺匹配工作流与文献基座；均不是已确认方向或创新。其“待用户选择”状态已被本次K3选择取代。

**当前小目标完成：[102号研究要素组合与问题选择](research/102_研究要素组合与问题选择.md)（E353）。** 按用户要求从要素组成问题，列出K1“合法Stage划分＋设备／工作点／完整时序”、K2“兼容请求合批＋设备／工作点／完整时序”、K3“设备忙闲／休眠状态＋设备／工作点／完整时序”。共同目标为同功能、同窗口总能耗最小，期限和连续温度为约束；每组只开放一类决策，不叠加成总模型。报告说明条件例子、R86变化及简单方法足够的条件，没有新增文献事实或创新判断。

首轮曾提出K1—K3选择题；用户随后明确要求先保留并增加三组，最新目录和边界以上文为准。不默认继承101号合批优先顺序。K1列入概念表不恢复09号实验，K3不恢复跨场景问题族。R86、正文、程序和历史结果均保持。

**推进方式调整依据（2026-10-03，用户要求，E352）。** 暂缓101号A／B的定向文献扩展，先把题目拆成决策、目标、约束、决策组织／信息条件及评价模型，列清当前已开放、固定但可讨论和范围变化较大的要素。再由有实际联系的要素形成少量问题组合，最后按组合查找成熟框架与已有覆盖。尤其区分“加入更多因素”和“哪些决策跨请求／场景共享、何时作出、哪些共同决定”的组织变化。E352仅在聊天中整理要素；102号记录其后的问题组合，均不自动修改R86或运行实验。

**当前路线与阶段（2026-10-03用户授权重新讨论问题组织）。** 用户认为99—100号与当前正文相比主要是模型细化，允许讨论开放此前固定的决策。优先借鉴成熟框架形成有应用理由的联合问题，不以实验发现旧方法失效为构想前提。允许讨论假设调整不等于批准修改：R86-v1与93—100号保留为参照，原后续数据／验证小目标暂缓，三、四章暂不展开。

**新一轮第1小目标已完成：[101号研究问题重组的候选决策与原文依据](research/101_研究问题重组的候选决策与原文依据.md)（E350—E351）。** 保留两个待审候选：A“请求合批与完整调度共同决定”，以IceEdge的批次／执行模板与热频率控制分工为主要基座；B“模型／块驻留与计算共同安排”，以SwapNet §6的生命周期接口与示例执行政策为基座。分别列出R86变化、简单替代和数据缺口；没有修改R86、正文、程序或参数，没有实验。

已发现明确已有覆盖：S2预印本已联合批处理／DVFS／卸载，IceEdge已有热控制；SwapNet已有内存分配与块划分调度，SwapAdvisor官方摘要已有算子／内存／交换联合优化。因此候选只说明可开放什么，不证明创新。划分粒度不凑作第三项，保留ADMS／Band及09号已有覆盖。SwapAdvisor全文本次访问未成功，只用于官方摘要中的正面能力核对，不据此断言遗漏。

101号原建议下一步比较A／B的已有覆盖和可行性；**此步骤已按用户最新要求暂缓，当前先整理研究问题要素，再形成组合。** A／B仅保留为选项，不强制以后围绕这两个入口收敛。以下100号及此前“下一步”均为历史，以顶部最新安排为准。

**已完成后续第3小目标：[100号联合模型求解路线与适配边界](research/100_联合模型求解路线与适配边界.md)（E348—E349）。** 推荐“约束引导的配置与时序搜索＋完整热能耗评价”：继承HaX的映射／时间线共同表达、Kim的组合／内层评价组织及F-DTM的条件热传播工具。配置内仍须比较完整时序，不能把首个安全见证当作该配置最低能耗；全部合法模式是原始决策域，不默用局部Pareto库裁减。

已明确三项适配：工作点相关漏电需要状态一致的完整评价；旧CTF固定热系数不自动有效；旧配置能量、下界及安全配置关闭规则不直接沿用。路线组织已确定，具体搜索算法／求解器及新评价器的误差保证未确定。保留通用工具已经足够的条件，不声明收益、新颖性或原方法失败；本轮仅只读原文／旧代码和条件推导，没有运行实验或改变R86。

第2小目标：[99号端侧热约束节能联合模型骨架](research/99_端侧热约束节能联合模型骨架.md)（E346—E347）。决策为Stage模式与启动时刻；由同一安排派生资源占用、域保持状态、完整请求完成及热能耗。给出模式／释放／依赖／资源／期限约束、事件式域保持、计量组功率、分开注热及完整窗口目标E(m,s)。模型为符号骨架，未形成可运行数值实例。

关键闭合点：同刻结束／开始且无跨越者时允许域换点；计量组跨域使用状态元组；共享基准与单元活动分开注热；只有明确仿射代表温度映射时才得到分段仿射ODE。按R86 R3登记已有固定资源需求，未明的局部宿主占用保留缺口，不默加全段占用。全部控制、计量及热映射是输入，不是新的优化自由度。稳定性、连续峰温与窗口外保证分开。

第1小目标[98号联合模型继承与修改清单](research/98_联合模型继承与修改清单.md)（E344—E345）保留为构件依据：映射、响应、时间线、资源／频率域、期限／目标、热功耗和空闲计量。首个接合点为工作点选择与完整时间线；不把已有能力或接口适配直接认定为创新。

原后续六目标为：①继承与修改清单；②一致的联合模型；③一条求解路线；④数据与公平验证方案；⑤实现正确性；⑥比较与贡献收敛。①②③已完成；**2026-10-03根据用户新的问题重组要求，④及以后暂缓，尚未执行。** 此路线保持为备选材料，不与101号同时推进。

**阶段四已完成并获用户确认：[97号以HaX为基座的联合问题定位](research/97_以HaX为基座的联合问题定位.md)（E341—E343）。** 用户明确确认主线为“端侧完整请求的热约束节能联合规划”。具体含义：在给定请求期限和入口热状态下，共同决定Stage设备、合法工作点及执行时序，寻找完整请求按时完成、连续热安全且系统总能耗较低的安排。继承HaX映射与时间线共同评价的组织，重心转向期限与温度约束下的完整能耗规划；任务相关响应为模式输入。

HaX原有争用慢化和转换开销未迁入R86，因此是选择性继承与适配，不是“完整HaX＋热约束”或严格超集。工作点、时序、共享域与热能耗须保持同一决策语义；一条安全表不证明固定配置最省能，一条失败表不排除其他安排。已有联合求解可能足够，贡献、收益及匹配数据仍未落实。主线确认不等于算法、贡献或实验方案确认；最新推进位置以上述99号为准。

**阶段三：[96号联合规划近邻覆盖与研究重心选择](research/96_联合规划近邻覆盖与研究重心选择.md)（E339—E340）。** 用户已选择：**保留端侧完整联合规划，以HaX为主框架，明确借入热能耗与工作点后形成什么具体研究问题。** 实际CPU单元／加速器身份保留为内部协调环节，不转为独立方向；任务相关响应为输入组成，不预定候选库、反馈或算法。

定向核查Zhou JSA 2018／TCAD 2016、Hybrid、Gerards、JOSS、AxoNN，确认具体处理器与频率／热能耗、共享DVFS与调度、等待／热反馈及端侧能量映射均有已有能力。不能仅由Kim轮转步骤推出领域空白。原文与R86仍有执行政策、时序组织及完整评价的适配差异，但差异不等于新颖性或收益；没有完全相同规则集合也不是贡献证明。

[94号](research/94_成熟框架固定决策与分阶段边界核查.md)的原文边界与[95号](research/95_联合研究构想与具体协调关系.md)的总体构想继续保留。阶段四已用97号完成原问题、共同决策、应用理由和继承接口的简短定位；本轮未新检索、未改R86／正文／代码／参数、未运行实验。分阶段约束见 `AGENTS.md`；旧模型修正链及 `RESEARCH_METHOD.md`旧流程不自动触发。以下历史“下一步”不覆盖当前停止边界。

**最新完成：93号端侧推理配置选择与完整时序联合规划框架（E332—E334）。** [93号](research/93_端侧推理配置选择与完整时序联合规划框架.md)落实用户进一步选择：**先定义完整联合问题，候选库与反馈重选只是待论证的求解组织。** 以全部合法Stage模式和声明启动域为原始决策域，区分Stage模式、单请求配置、全请求配置与完整安排；单请求候选不固定局部时间表，不强制同工作流不同请求共用映射。

共同目标为R86完整窗口能量E(m,s)，满足资源、依赖、完整请求期限、共享域及连续热安全。93号定义规划／评价／反馈职责与证据范围：一条安全表只给上界；一条表失败不排除配置；完整组合被证不可行不自动删除其中的单请求候选；候选域最优或无解不能扩大为原始全域结论。覆盖、数值及预算状态分列，旧配置关闭和下界不自动继承。

保留HaX的映射／时间约束与Kim候选组合／内层评价能力，不照搬二者配置定义、执行政策或示例限制。H93聚焦局部候选信息与完整请求价值的一致性；以全模式联合规划、完整复核及简单回补为强替代，允许选择不变和无收益。任务相关响应为输入组成，温度参与完整选择，B作为内部评价，不另开方向；配套数据、新实现、具体规则及收益尚待研究。

Kang DAC 2016全文仍缺，已登记系统模型、单图候选、多图组合／反馈的下载用途；不阻挡框架定义，不据二手描述宣布差异。本轮未新检索或运行实验，未改R86、正文、程序、参数及历史报告，未设新网格或预算。**下一步先审阅93号框架的连贯性、接口及两章实质工作，再确定一项方法细化任务。** 以下“下一步”按历史保留，以本段为准。

**最新完成：92号成熟框架决策边界与联合建模入口筛选（E329—E331）。** [92号](research/92_成熟框架决策边界与联合建模入口筛选.md)在R86-v1不变的前提下初筛18篇、定向深读6篇，保留“配置与共同规划”和“热调度与完整时序”两个候选。用户已明确选择**A：以Kim／HaX-CoNN为基座，研究局部保留的配置如何接受完整期限、热状态与能耗评价，并反馈重选**；B只保留为内部评价工具与对照能力，不另开分支。

拟以HaX的完整映射／时间线组织共同问题，借鉴Kim的候选库及组合评价，MEDEA补充局部代价压缩的接口依据。任务相关响应是组成部分，不强制独自承担全文动机；不以先运行实验反例作为构想准入。已核正：Kim组合阶段已有内嵌调频／期限检验，HaX公开代码已有等待和跨DNN次序选择，Zhou TCAD 2016已有热失败后重新分配。不能把这些已有能力重新作为新增贡献。

明确局部候选保留条件与完整评价可能不一致，但尚未证明R86中有价值配置被删、简单回补不足或新方法获益。保留全模式联合规划、完整复核／重新规划、标量成本修正已经足够的条件；不恢复跨场景、精度、争用、关机等R86之外动作。旧L3结果不升级为新模型验证，配套数据缺失限制现实验证层级，不自动否定构想。

**唯一下一步：沿A定义“候选保留—完整评价—反馈重选”的框架接口，收敛一个具体协调关系。** Kang DAC 2016全文仍缺，若需判断两阶段共同调度前身的具体筛选／回访能力，应先补读；其他条件性下载需求已登记。选择A不等于确认新颖性、具体筛选规则或最终算法。本轮仅报告与证据同步，不改正文／程序／参数／历史结果，不运行实验，不自动进入算法设计。以下“下一步”按历史保留，以本段为准。

**最新完成：91号端侧推理联合调度研究构想汇报（E327—E328）。** [91号](research/91_端侧推理联合调度研究构想汇报.md)采用用户选择的导师阅读稿，按“应用需要—核心矛盾—已有研究—两章工作—已有支撑—验证路线”展开。用户接受以A资源选择与完整规划统领、B完整时序与系统能耗评价为内层的汇报组织；这结束90号的叙述重心等待，不等于确认新颖性、具体筛选规则或最终算法。

主线为“局部执行效率怎样转化为满足完整期限与热要求的系统节能”。任务相关响应保留为组成部分；不把加入NPU、温度、查表或模块组合直接当作创新。报告正文约3300个汉字，含贯穿概念例、近邻对照表与方法信息流，假设、数学表达、文献定位和历史证据入口放附录。

精选旧60／55／78号结果，分别支持响应决策影响、热可行集合收缩和限定压力下热反馈作用；保留紧期限无变化、104→80但仍44 mJ、26/32→30/32且共同成功能量相同等条件。旧L3结果不提升为86号三设备／漏电模型验证，候选筛选损失及同配置能耗差尚待验证，旧实现与配套输入仍需适配。

**当前下一步先审阅这份汇报的连贯性与实质工作量，再确定一项证据补齐或验证任务。** R86-v1保持不变，本轮只写汇报及同步记录，未改正文、程序、参数或历史结果，未运行实验、未新增文献筛选。以下“下一步”按历史保留，以本段为准。

**最新完成：90号联合框架证据比较与主线收敛（E325—E326）。** [90号](research/90_联合框架证据比较与主线收敛.md)按同一尺度比较“资源选择与时序协调”和“完整时序与热能耗协调”，重核NeuOS、JOSS、Zhou、F-DTM、HaX-CoNN、Kim正文，定向新增一项Zhou等TCAD 2016原文。任务偏好、共享配置、温度相关功率及通过余量减少漏电均已有处理，不能把这些因素或查表、模块组合直接称为创新。

保留两个待选择的接口候选：**A，局部配置筛选在完整期限／热能耗评价下能否可靠保留有价值的选择；B，同一配置取得安全安排后，是否仍需继续优化时序相关系统能耗。** A更便于组织资源选择的研究故事，B与R86的E(m,s)联系更直接；这不是新颖性或性能排名。两者均保留已有方法足够、选择不变和无收益条件，尚无R86下决策损失或新方法收益证据。

**当前只等待用户选择下一轮深入重心。** R86-v1及其固定工作流、有限已知请求、执行规则和功耗／热假设保持不变；任务相关响应保留为组成部分，不要求独自承担全文动机。任何必要的假设调整先说明并征求意见。88号对照建议及旧实现改造需求保留，待选定对象后适配，不自动执行。本轮只阅读、推导和记录，不改正文／程序／参数，不运行实验；以下“下一步”按历史保留，以本段为准。

**补充核查：89号师兄多场景共享部署已有覆盖（E324）。** [89号](research/89_师兄多场景共享部署的已有覆盖核查.md)重读Kim与Ha的TC正文及师兄原文：激活应用场景、跨场景驻留映射、按场景／期限调频和综合能耗已有直接先例，师兄已引用Kim。因此“场景化／共享映射／加入NPU”不能单独作为独有建模创新；可识别差异在统一数学表达、资源窗口与求解组织，尚未作完整新颖性或正确性认证。此前结构辨识度评价不代表创新性已更强。本次只查资料、记录，不改R86、正文或实验，不恢复跨场景方向；88号后续任务保持原范围。

**最新核查：88号对比算法选择与GA适用性（E322—E323）。** [88号](research/88_对比算法选择与遗传算法适用性审查.md)核对师兄EA-GA直接借鉴Kim，及Kim明确允许其他元启发式替换的原文依据；比较HEFT、PEFT、Zhou、GA、热调度MILP启发式和移动NPU热调度的对照职责。推荐先保留CTF／no-good同实现对照，加一个能耗／热感知列表方法；GA或Zhou适配按额外比较问题二选一，尚未决定正式算法组。

86号R86-v1保持不变。温度漏电、保持工作点的基准及多热节点下，旧MILP和搜索方法均须适配，不只要求文献基线适配。GA只编码设备／频率并固定最早安排时，不能当作完整时序搜索；所有有效输出统一连续热复核。下一步只细化列表基线及共同模型接口，再决定是否需要额外搜索参照；未定实验数值／重复次数，不改正文／程序，不运行实验。

**最新阅读：87号师兄第三章实验设计思路复盘（E321）。** 已重新读取根目录main.pdf §3.7，印刷33—42／PDF45—54页，并视觉核对印36、40、42页。记录见[87号](research/87_师兄第三章实验设计思路复盘.md)：先说明基线、指标与输入规则，再通过五组实验考察结构条件下能耗、方法能耗、期限作用、可行输出及求解成本，最后承接第四章。学习组织与论证，不照搬其场景变量或实验数值，不为原始数据和算法保证背书。

基础规则仍以86号R86-v1为准。本次不改正文／程序／参数，不运行实验；没有确定新样本规模或扫描范围。后续先对应我们的模型验证、热反馈方法对照及求解适用性问题，再单独选工作负载及配套参数；不自动启动实验。师兄现有图文设定、坐标和指标的部分不一致已在87号登记，不用于否定其组织经验，也不直接复制。

**最新完成：86号实验基础模型与假设确认总表，R86-v1（E319—E320）。** [86号](research/86_实验基础模型与假设确认总表.md)是后续实验统一查阅入口：固定工作流、有限已知释放的执行前规划，原子Stage，固定CPU单元及设备级GPU/NPU，合法OPP与共享域规则，空闲保持，确定任务相关响应，频率相关基准／温度漏电、活动可加、零额外交接和切换开销。用户专门选择**CPU按固定执行单元区分热状态**，保留启动前温度感知资源选择；不引入执行中迁移，不默认核组温度等于最高核温。设备、频率域、计量组和热节点分开登记。

假设规则已确认，具体工作流、模式表、功耗系数、功率／温度映射、RC、初温及实验数值尚待填写。86号列出字段、单位、简化边界、来源与一致性要求；85号保存核查及选择过程，并链接到总表。推荐状态不再逐项等待确认，但模型内假设不提升为实机事实或WCET保证。目标一般仍为E(m,s)，旧配置关闭、下界及热反馈须重审；旧实验不升级为新模型验证。

**下一步先依据总表选择并补齐具体工作流、资源、响应和热数据，再单独设计实验。** 本次仅整理记录并作静态检查，不修改正文／程序／历史输入，不运行实验，不自动确定数值或启动算法改造。以下85号及其他“待确认／下一步”均保留为历史，以本段及86号为准。

**85号R85-v1确认与精简审查（历史，E318）。** 用户接受原§6.1前三组：有限已知释放的执行前规划；Stage不可抢占／迁移／执行中改频，固定CPU单元及设备级独占GPU／NPU，域清空换频；频率相关空闲与温度相关漏电。用户将额外交接／搬运／转换及调频切换时间和能量明确简化为零。这是范围选择，不是设备成本实测为零；依赖及既有Stage计算保留。记录见[85号§8](research/85_实验基础建模假设核查与推荐.md#8r85-v1用户确认与主线精简审查)。

零开销不自动恢复E(m)，频率相关基准和漏电仍可使能量依赖时序，旧热行、下界和安全配置关闭须重审。其他精简建议为：不单独优化电压或休眠，采用固定条件下的确定响应及活动可加，温度漏电仅局部线性、同组同工作点共用斜率，热节点优先资源组／设备级聚合；不恢复并发争用或pair支线。空闲保持政策、响应适用条件与热粒度尚为推荐，未替用户自动确认。**当前下一步仅确认这些剩余范围选择，形成统一基础假设清单；不冻结实验数值、不改正文／算法、不运行实验。** 下面v0及各项“下一步”保留为历史，以本段为准。

**85号初始推荐R85-v0（历史，E316—E317）。** 用户要求先确定执行规则与模型假设，再设计实验数值；不因验证便利逐步把简化写成正式边界。已形成[85号整体推荐R85-v0](research/85_实验基础建模假设核查与推荐.md)，定向核查师兄、Band、HaX-CoNN、NeuOS、F-DTM、RT-TAS、Zhou、JOSS、ASPLOS及Linux控制接口，复用82—84号并核对旧代码适用范围。推荐有限已知释放日历的固定工作流规划、Stage边界调度、固定CPU单元与设备级GPU／NPU、工作点相关基准、逐Stage活动增量、温度相关漏电、显式开销及匹配耦合RC。**当时整体方案待确认；尚未替换61号正式模型或论文正文。**

温度／状态相关功率下目标一般为E(m,s)，不能保留旧E(m)而默默删项。原配置安全见证关闭、活动能量下界、固定系数热行和冻结二节点包络须重审；合理基础假设优先于保留旧算法。四Stage双请求、恒定功率与零开销仅保留历史特例，不提升为CPU–GPU–NPU或新功耗验证。工作流已确认，GPU／NPU设备级及数量输入已确认；释放信息、抢占／控制政策、漏电纳入和开销／响应条件仍待确认。

**当前唯一下一步：整体审阅85号并确认§6.1四组实质选择，再登记基础假设版本。** 不冻结数值、不改算法、不运行实验，也不自动继续正文润色。此次只新增报告并同步记录；以下“下一步”按历史保留，以本段为准。

**3.3写作已完成（2026-10-01，E315）：** 按用户确认的六节组织[功耗与温度模型](research/latex/chapter03.tex)：功耗分解与运行状态、CPU、GPU、NPU、统一功率与能耗、瞬态温度。增加Zhou、ASPLOS 2025、F-DTM与Linux OPP的就近引用，分清静态／动态的物理来源与基准／活动增量的计量方式。CPU按控制组去重基准、并发增量求和；GPU采用设备级等效活动参数；NPU沿用相同CMOS物理基础，以合并系数表达负载与温度项，不将三者写成不同物理原理。

本次为用户授权的正文改写，不运行实验。3.3列出可含工作点与温度依赖的一般功率表达，并明确后续3.4—3.8及已有CTF-MILP实验仍使用CPU–NPU、恒定基准与固定模式活动增量特例。未将GPU、温度相关漏电或三设备参数自动纳入原求解保证；3.1—3.2及3.4之后的正文内容保持不变。匹配测量数据与新一般平台的系统模型、求解适配仍待后续确定。预览入口为`research/latex/build/main.pdf`，详细来源及改写边界见E315；以下既有状态按历史保留，本段优先。

**GPU／NPU映射粒度已确认（2026-10-01，E314）：** 采用设备级映射，不逐个调度加速器内部计算核心。一般模型用GPU、NPU可调度设备集合表示，数量不固定为一个；后续实验按声明配置设置。CPU仍沿用固定执行单元抽象。设备数量、频率控制关系、并发容量和热节点分别定义，多个设备不自动意味着独立调频或独立热节点。尚未确认具体数量和三设备参数；本次只更新研究记录，不改正文、程序或历史实验。

执行粒度依据见证据记录E313：Kim、Band、F-DTM及ASPLOS分别提供设备／worker或算子级处理依据。调频范围涉及场景、内核／算子或系统自动变化，不能混同；采用设备级映射不等于同时继承师兄的跨场景映射和场景内固定频率。

**当前优先事项：重审系统、功耗与温度模型的文献基座。** 用户要求借鉴师兄和高水平论文，在相容基座上做必要修改，避免过度简化，也避免为“完备”堆叠变量。已形成[82号审查](research/82_系统功耗与温度模型基座审查.md)：优先核定逐Stage功率、空闲／活动计量、频率／设备状态和热边界；固定Stage和设备级RC等有依据的内容可保留。新正式模型尚未确认，旧61号、正文及历史实验保持原范围。

下一步先形成模型继承与修改确认表，再确定第三章适度版本；此前正文润色、第四章推进及新实验建议暂不自动执行。此次仅核查资料，不改正文、程序或参数，不运行实验。论文因素更多不自动意味着更完备，来源和数据粒度须匹配。

功耗基座补查见[83号](research/83_电压频率与功耗表达的文献依据核查.md)：ASPLOS 2025在Ascend上报告分段V–f关系，并用空闲、测试负载及目标算子测量确定基准、活动和温度项；F-DTM让硬件自动设电压，按频率配置训练模型。暂建议保留离散合法模式接口，按设备登记有依据的工作点和功率，不统一强制线性V(f)或频率幂律。AccelWattch仅取得作者页面，未核对公式正文。新正式模型及三设备数值未确认，本轮不改正文、程序或历史输入，不运行实验。

温度功率项补查见[84号](research/84_温度相关功耗模型的直接文献依据.md)：ASPLOS 2025在基准与活动之外加入\(\gamma\Delta T V\)，F-DTM和Zhou也让温度进入设备功率/漏电公式。可作为温度扩展候选，加入该因素本身不是创新。NPU优先核对ASPLOS，CPU/GPU对照F-DTM和Zhou；匹配系数、参考温度和注热边界未齐，尚未确认正式采用。旧能量分解、下界及CTF热行须在模型变更后单独核查；本轮只读资料，不改正文、程序或实验。

**平台范围调整（用户确认）：** 允许在原多核CPU–NPU对象中加入GPU，研究平台可扩展为CPU–GPU–NPU；用户转述导师允许后期修改题目，但研究核心保持不变。核心仍是任务相关执行响应、资源与依赖、完整请求期限及瞬态热状态共同作用下的映射、频率和时序选择，以系统能耗为目标。此次确认的是允许扩展的平台范围，尚未确定GPU数量、频率控制、合法Stage支持、响应／功率参数及热节点；这些不得自动按CPU或NPU设置继承。

固定工作流的多模型端侧推理仍作为应用组织。61号正式模型及已有CPU–NPU实验保持原范围；旧结果不能改称CPU–GPU–NPU验证。后续纳入GPU时需核对合法模式、资源／频率域、功率与注热边界以及相应评价器；加入设备类型本身不构成贡献。本次只登记范围，不改正文、程序、冻结输入或历史结果，不运行实验。题目尚未正式修改。

**当前正文整理进度：** 已按“给定条件—实际决策—数学约束—求解表达”重组第三章3.4—3.6。3.4集中定义问题，3.5沿模式、时间、依赖、资源和温度建立完整模型，配置与时序关系随后集中解释；网格和独立下界移到3.6，符号表移至章末，部分配置下界与冲突方向传播保存为未编译的第四章素材。3.1—3.3及3.7—3.8正文保持不变，未修改程序、参数或历史结果，未运行实验。当前先审阅这次重组的阅读顺序；后续既有研究建议不自动触发新实验。

**写作规范更新：** 已建立[论文写作风格指南](research/论文写作风格指南.md)，从根目录`main.pdf`及《草稿》的模型、方法、实验段落提炼概念引入、公式解释和段落衔接规则，并以用户修订后的第三章3.1—3.2为本项目范例。指南含出处定位、三组“原段落—改写示范—调整理由”及跨会话重读提示；根目录AGENTS.md已加入论文写作任务的读取要求。具体规则只在指南维护。本轮未改LaTeX正文、模型、程序、参数或实验结果；不运行实验，不修改全局配置。后续按用户指定小节逐节采用，研究对象与以下证据范围保持不变。

**当前研究对象已确认：固定工作流的多模型端侧推理。** 用户在81号比较后同意泛化应用领域，不限定视觉、音频等；以此作为应用与任务组织，保留任务相关频率响应、固定CPU执行单元／NPU、期限、温度与系统能耗的联合调度基础。确认及术语见[81号§12](research/81_任务相关响应的应用背景与研究对象核查.md)。此前“等待选择A”的状态已结束，视觉例子只作来源与应用示例。

采用“应用工作流模板→一次工作流调用／请求实例→模型调用→Stage实例”的区分。“固定”指本次规划图、模型、精度及合法Stage划分确定，不指映射／频率／时序固定，也不默认周期和未来所有到达已知。工作流可展开为原请求DAG；零成本汇合不自动增加耦合，泛化应用背景不自动构成创新或扩展热保证。61号正式假设及历史实验仍保留。

当前下一步：整理第三章3.1—3.2中应用背景、请求含义与任务模型的衔接，再核对全章术语。旧四Stage双请求结果不能改名为新多模型工作流验证；具体模型对和配套数据尚未确定。本次只更新记录，未修改LaTeX、程序、参数或运行实验。以下81号初次推荐及更早状态按历史保留，以本段为准。

最新完成：[81任务相关响应的应用背景与研究对象核查](research/81_任务相关响应的应用背景与研究对象核查.md)。按用户要求重新发散，初筛19项材料，对Kang、Band、MEDEA、NeuOS、ADMS、HaX-CoNN、PED、JOSS八篇定向补读任务、决策与关键方法正文，区分旧下载／摘要／模型／方法阅读范围。MEDEA采用2026年v3，ADMS区分2025在线与2026卷期；摘要材料不作缺口证据。

推荐进入讨论的是**固定视觉工作流中的多DNN协同推理**，主要框架来源为HaX-CoNN：同输入多模型并行后汇合、模型间串接及固定CFG的执行前准备均有正文依据。以业务完成条件解释任务为何共同规划，以Stage相关响应改变路径／资源占用及能量，以完整热轨迹判断配置是否可执行。共同期限下零成本汇合可能与旧双请求等价，不能据此宣称新增耦合。该推荐不预选周期、不改61号，也不将工作流层次或查表本身称为创新。

另外比较NeuOS式异步多模型共享配置、Kang式单应用异质阶段。NeuOS已经研究不同层响应与共享DVFS，HaX已有转换与争用，ADMS已有热状态反馈，均保留为已有能力及强替代。Kang明确指出反比频率校正可能造成预测误差，但核数响应不等于频率曲线，原NPU参数也不是完整实测。新工作流的CPU–NPU支持、同Stage跨频点时长、功率与RC尚未配套；可作显式L3条件研究，不能拼接成设备复现。

本轮提出单一H81：固定工作量、精度、业务完成条件与共同求解能力后，响应刻画是否改变有效配置／安排及能量；保留不变、并列、既有方法足够和未决。旧59—60号响应证据、55号热配置证据与76—78号反馈结果保持原有限L3范围，未被移作新工作流结果。未改正文、程序、参数或历史实验，未运行实验。

当前唯一下一步：**讨论并选定是否采用候选A，再定义一个具体工作流的对象契约。** 不自动冻结数据、改写第三章或启动验证；80号周期推荐退回比较对象，不是既定选题。以下80号及更早下一步按历史保留，以本段为准。

最新完成：[80已有论文思想借鉴与主线框架比较](research/80_已有论文思想借鉴与主线框架比较.md)。按用户授权重新比较任务组织和研究框架，核查Kim、DELIA、F-DTM、RT-TAS及HEFT原文，定向补充Simon等有限DAG运行期求解全文及Ahmed等周期热资源的出版方引言。区分“网络已知、释放规则已知、场景集合已知、场景序列已知”；Kim不提供已知场景时间序列，DELIA连续帧也不自动提供严格周期与逐帧期限。

比较三个框架：A固定采集节奏下的持续推理部署与热安全调度；B多场景共享部署；C现有有限实例执行前规划。**推荐A进入讨论，尚未替换61号正式模型。** 理由是周期任务有明确来源、部署前可生成重复计划、前后轮热状态形成实质关联；不是把周期、RC固定点或已有论文组合认定为创新。B缺场景转换／入口条件及进一步近邻证据，C仍成立但需解释实例取得和规划耗时；原60 s预算不代表在线毫秒级可部署性。

本轮给出释放展开、重复热状态及平均每请求能量的条件推导，登记启动／持续安全、跨周期资源和现有MILP热反馈／有界搜索的适配边界；24—26号仍是旧构思，47号简单完整后缀的成功及76—78号有限L3证据均保留原范围。启动条件不仅包含初温，还包含在途任务和资源状态；未来热对照须固定相同周期结构合法域。未修改论文正文、源码、参数或历史结果，未运行新实验。

当前唯一下一步：讨论并选定是否采用A，再形成周期释放、部署决策与启动／持续热保证的对象契约。选定前不自动恢复旧方向、改写第三章或启动参数扫描。以下79号及更早“下一步”按历史保留，以本段为准。

最新完成：[79第三章连续热反馈方法与实验整合](research/79_第三章连续热反馈方法与实验整合.md)。已将76—78号写入[第三章LaTeX主稿](research/latex/chapter03.tex)，保留师兄八节结构。3.6从完整赋值排除对照引出全选项固定时刻热行，给出响应叠加、可靠系数与右端、有效性及整数域覆盖关系，并更新流程／伪代码与停止条件；3.7分开模型验证、离线覆盖、原输入零触发及16条件压力对照。

正文结论限定为“有效连续热反馈表达＋限定热压力下的求解收益”：安全输出26/32→30/32，部分条件减少外层轮次及耗时；双方共同成功时能量相同，零反馈与无输出条件全部保留。任务相关建模动机、热配置收缩与反馈计算作用分别论证，不将通用约束生成当成新原理或宣布创新充分成立。

本轮仅改正文、参考文献和记录，从保存CSV重绘轮次图，编译并检查PDF；未运行实验，未修改历史方法、输入或结果。第三章仍以LaTeX为唯一正文主版本，新增79号只记录章节、来源、边界与检查。

当前唯一下一步：先审阅第三章3.6—3.8的方法论证、实验解释与贡献措辞，再推进第四章写作及其与强化MILP的衔接。68号旧no-good比较不能改写成已与热反馈MILP比较；本轮不自动补跑、不新增组件、压力点或pair验证。以下78号及更早下一步按历史保留，以本段为准。

最新完成：[78入口热压力下连续热反馈对照](research/78_入口热压力下连续热反馈对照.md)。按用户预定范围，仅改变共同初温：79.45°C发现性诊断两次调用；原四种功率／期限组合×78、79、79.5、79.75°C形成16项，两遍交换方法先后，共64次正式调用。输入和全部66次顺序事先冻结，原b68_method、f77_method、53号输入及第四章源码未改，各调用独立60 s，无扩预算或追加案例。

284项预检通过。79.45°C诊断首选安排的独立1 ms点温度区间约[80.02748339927437,80.02748339928272]°C，安全替代全窗口上界小于79.954687847549°C；证据未传入方法。正常求解中原方法18轮／17条no-good、热反馈3轮／2条热行，均44 mJ；诊断不并入正式统计。

正式组原方法26/32次取得安全U，热反馈30/32次；两遍每次均13项双方安全且能量相同、2项仅反馈取得安全解、1项双方无U。5项案例两遍轮次均减少（3→2、12→2或18→3）且墙钟更短；高功率D10、79.5/79.75°C原方法两遍均超时无U，热反馈分别2／3轮取得42.625 mJ并与L₀闭合。高功率D6、79.75°C原方法超时，反馈3轮后仅solver-reported无解，未升格为独立不可行。

78/79°C共8项仍零反馈，16个配对中反馈耗时8快8慢，不据此宣称收益。正式热行22条，无回退／重复／数值异常；累计轮数272→54，不同候选282→56。原方法独立最优12次，反馈16次；双方均有U时没有能量改善。32个配对首候选一致，结果支持“违规信息复用减少重复求解、部分案例改善预算内安全输出”，但不支持普遍加速、实测节能或新颖性充分成立。两次重复不作统计稳定性证明。

诊断与正式58份安全输出均独立复核通过；6次原方法超时的停止延迟、最终预算标志及原始日志保留，不补记晚证据。122份正式源码／输入快照一致；保护清单3,212份中3,206份未变，6个LaTeX编译产物在正式前发生非本任务写入，已登记前后哈希并保留，LaTeX源文及历史实验文件未变。结果、证书、逐轮日志及19幅保存数据图见pressure78_reports/frozen_20260928_183250_962。

当前唯一下一步：按76—78号证据修订第三章热反馈方法与实验定位，区分有效表达、条件性计算收益和新颖性，并将强化MILP列为第四章后续参照。本轮不自动改正文、不重跑第四章、不追加压力点、组件或pair验证。以下77号及更早“下一步”按历史保留，以本段为准。

最新完成：[77连续热反馈MILP实现与冻结对照](research/77_连续热反馈MILP实现与冻结对照.md)。已新增run_feedback77，将76号固定时刻热行接入完整MILP循环；整数结构／no-good与浮点热行分开检查，缓存命中重新核查当前热行，保留点证书、重复行回退、完整连续热接纳和独立L₀。原b68方法、53号输入及第四章代码未改，未改写第三章贡献结论。

正式前178项预检通过，原8主例＋2校验、两方法共20次独立调用均在60 s内完成。两方主例均8/8安全、并列校验均安全，18份输出独立复核通过，逐例能量与时间表相同。所有调用仅一轮，9项可行输入各只有一个不同候选；热行、no-good、回退、重复事件全部0。4 ms校验两方仅求解器报告无解。每法4项宽期限主例＋并列校验由U=L₀独立证最优，紧期限只保留安全U与内部收敛。

因此本轮结论是“反馈接入成立，但本组未验证其计算收益”。76号离线覆盖扩张继续保留，不将其改写为MILP减少轮次或加速。单次计时有快有慢，固定调用顺序与初始化影响未分离，不能归因于未触发的热反馈。当前证据层级为有效反馈表达、实现与接口验证，尚非条件性计算收益或已充分成立的创新。

正式后补齐超预算时不掩盖原实现错误的防护，当前179项预检通过；该分支未在任何正式调用触发，保存原源码快照和178项凭据，不重跑研究案例。1,750个登记历史文件哈希全部不变，正式116份快照核对通过。输入／源码／环境、MAT／CSV、候选日志、计时区间及界图见正式目录feedback77_reports/frozen_20260928_172132_129。

当前唯一下一步：返回第三章方法定位与措辞审阅，将有效反馈表达与未验证的计算收益分开，再安排与第四章的衔接。不自动追加案例、调参、组件或实验；以下76号及更早“下一步”按历史保留，以本段为准。

最新完成：[76连续热约束反馈方法论证与最小验证](research/76_连续热约束反馈方法论证与最小验证.md)。本轮以第三章具体方法贡献为目标，将“完整温度轨迹违规点→全选项固定时刻热行”落实为条件证明、独立诊断模块及原冷热两例验证；没有改变61号模型、53号参数、第四章算法，也未启动完整MILP反馈求解或改写第三章贡献结论。

20项预检通过。每例原288条合法安排均完整重建；冷态288安全，热态256安全／32违规，无未分辨，最低安全能量均44 mJ。32份热行全部可靠排除源安排且误删安全安排为0；其中CPU 5 ms行单条排除32安排／16个全局CPU换标轨道，6 ms行排除16／8。实际只有2条不同热行、2种违规聚合注热轨迹；不能将32份重复记录写成32项独立强化。热态104配置中80个可保留与55号一致，同配置安全等待均保留。

原理论与实现支持整数域中扩大排除范围，未证明MILP加速或能耗收益。两例离线预算内各约2.5 s；68号原MILP在这两个输入上首轮候选已安全，强化反馈可能不触发。近邻核查明确热MILP、查表与约束生成均有先例；当前增量限定为本题连续耦合RC到离散选项行的数值有效表达与信息复用，不宣称首次或普遍优势。

当前唯一下一步：进入固定时刻热反馈的完整MILP实现与公平性能验证，保留原no-good对照、同输入与总预算；不增加cover、pair、参数点或认证分支。报告只读核对737个保护文件，其中732个未变；5个LaTeX正文／编译文件出现非本任务写入，已保留并记录。登记历史实验源码、输入与55／64／68结果均未改。以下75号及更早“下一步”为历史，以本段为准。

最新完成：[75第三章结构重组与写作说明](research/75_第三章结构重组与写作说明.md)。按师兄论文实际八节结构重写[第三章LaTeX](research/latex/chapter03.tex)，章名改为“任务相关响应下的CPU–NPU热约束调度建模与求解”。正文以“引言—系统模型—功耗与温度—问题定义—形式化—MILP与连续热复核—仿真分析—小结”贯通；补充概念解释、二元选项编码、流程／伪代码与四Stage既有见证时间图。

两章分工正式调整为：第三章给出共同模型、MILP求解参照及模型验证；第四章在相同问题上介绍65号`no_repair`有界搜索、64号消融与68号方法比较。MILP不再仅作为第四章突然出现的工具。第三章保留解析核验（59—60）、枚举配置证据（55）与独立MILP输出（68）的不同来源，未改写为全由MILP完成；紧期限MILP内部收敛不升级为独立证书，原9项可行输入均未触发热排除。

本轮只修改正文、参考文献和写作／研究记录，未运行实验、改变代码或参数。当前唯一下一步是先审阅第三章重写稿，再以同样写作标准撰写第四章LaTeX；是否补做既有四个冷态输入的MILP响应配对在审阅后单独决定，不自动运行、不恢复pair或扩展案例。以下74号及更早“下一步”均为历史，以本段为准。

最新完成：[74第三章论证与贡献措辞审阅](research/74_第三章论证与贡献措辞审阅.md)。直接修订LaTeX主稿：限定只修正Zhou时长假设、并非完整模型包含性扩展；明确R共同评价是条件性机制检验而非实测拟合优越性；补齐连续变量类型、配置／时序集合表达和PDF中的结果追溯入口，分开历史数值核验与严格误差认证。没有发现需重建模型或追加实验才可修复的问题，但未宣称新颖性或学位工作量已获认定。

当前唯一下一步：依据65号`no_repair`主方法及68号工程MILP对照，撰写第四章LaTeX正文初稿。保留同能量、紧期限MILP较快及单次计时限制；不自动运行、扩规模或恢复pair支线。第三章继续以LaTeX为主，73号Markdown保留历史稿。

正文格式已按用户要求调整：第三章主版本为[chapter03.tex](research/latex/chapter03.tex)，统一预览入口为[main.tex](research/latex/main.tex)；第四章后续直接写LaTeX，目前仍只有方法与实验报告，尚无完整正文。研究记录继续Markdown，73号Markdown保留为历史稿及证据索引，避免两份正文并行维护。本次仅格式转换与编译核对，不改变研究模型或实验结果。

当前写作入口：[73第三章正文初稿](research/73_第三章正文初稿.md)。按用户确认，先将61号可加功率模型写成可供导师审阅的完整第三章；71—72号并发功率仅作适用边界，不等待支线数值冻结，也不自动触发其旧下一步。本轮完成3.1—3.8正文、统一符号、21个编号公式、两张结构图、条件性结果表及原文／本研究证据对应，无新实验、参数、程序或外部检索。

正文分别保留60号响应对照与55号热配置收缩：宽期限响应修正可改变共同评价能量，紧期限无差异；高功率紧期限热态104个无热最优配置保留80个，最低仍44 mJ。真实模型工件、作者后端支持报告与L3模式／RC分开，未写成实测节能或已证热协同收益。配置能量—时序可行性分离及下界仅在原加性假设下成立；未将pair扩展并入模型或原算法保证。

本轮后先审阅第三章论证完整性、贡献措辞和与第四章的衔接。现实配套参数及新颖性证据仍为限制；不自动恢复pair验证、参数扫描或实现优化。以下研究步骤与“下一步”保留为历史，以本段当前写作优先级为准。

当前实验路线：用户明确继续采用MATLAB仿真，RK3588只是临时咨询。[70号平台核查](research/70_RK3588研究平台适用性核查.md)仅作备查，停止板卡选型、镜像准入、硬件实测及三核NPU适配；其后续建议不进入当前任务。保留既有模型、L3参数属性、程序与历史结果，不将仿真解释为RK3588设备复现。以下69号研究事项不因这次硬件咨询自动改变。

最新完成：[72双Stage并发功率对照输入契约](research/72_双Stage并发功率对照输入契约.md)。按用户选择采用独立CPU阶段A与NPU阶段B，均0到达；A两档频率、B固定模式，时长不随并发改变，允许网格等待与任意合法重叠。本轮只写字段契约、代数及纸面验收，没有数值冻结、编程、仿真或扩展检索。该对象仅隔离CPU频率和重叠时序，不验证多核分配或替代映射，也不替换原主线。

pair表按CPU模式直接给两节点并发总功率，节点残差及κ从对应solo状态派生；不独立给总残差后任意分摊。四态系统功率、节点注热、状态时长与E_pair=P₀W＋Q_A d_A＋Q_B d_B＋κℓ积分一致。恒定pair功率、无相位／温度记忆、零额外转换脉冲均明确标为L3假设；无匹配实测支持，不自动继承53号参数或旧热评价器保证。

未来add／pair在同一有限域完整枚举，分别规划，再以pair原样回放全部add并列最优安排，报告安全成员、能量范围和模式集合；不挑代表制造收益。总残差为零不推出节点热轨迹相同，负残差不允许直接沿用旧L₀；首个安全见证不替代同模式时序最优或完整并列集合。完整窗口连续热峰、尾段及未分辨单列。

契约在声明假设下自洽，但全部性能／功率／热／时域数值、数值规则及预算仍待冻结，尚未回答H71。唯一下一步：冻结一小组自洽L3输入及比较规则，明确条件覆盖，不要求出现模式翻转；之后再决定实现，不自动运行、扫描或增加算法。以下71号及更早“下一步”按历史保留。

最新完成：[71并发代价与调度决策影响的条件论证](research/71_并发代价与调度决策影响的条件论证.md)。仅来源复核、代数推导和一项模型对照设计，无程序修改、数值冻结或仿真。定向复核BIDENT v2 §III-A/B、IV-A：已有并发时延，仍用solo package功率近似并发能量；这不是匹配活动残差的实测证据。HaX争用与联合规划能力保留，不重新当作遗漏。

结论为状态2：存在条件性决策影响，缺匹配pair功率及节点注热数据。固定模式与时长的并发／错开在可加模型下本来并列，kℓ首先打破时序并列；严格候选换序要求修正差超过原能量差。配置改变还需比较各配置重新安排后的最佳可实现能量，不能由两条代表推全域。热修正按完整节点输入卷积与逐时刻裕量判断，只排除具体安排；package标量不能唯一拆为CPU／NPU注热。

若能量开始依赖时序，旧“该配置已有安全见证即关闭”及独立Stage能量下界须重审；负残差不能直接忽略。但pair查表＋现有联合规划仍可能足够，尚无新算法必要性证据。H71只改变规划功率，两方共用时长、动作和热边界，并在同一pair模型回放；并列、无变化、不可行及覆盖未决均保留。功率修正本身不改变固定时间表完成时刻，不将未经声明的热节流或修复混入模型收益。

唯一下一步建议：定义一项H71最小模型对照的输入契约，限定pair表的重叠适用条件与能量／注热一致性，再决定是否冻结L3输入。当前不运行、不扫描、不推进CARIn、不替换61—68号主线。以下69号及更早“下一步”按历史保留，以71号结论为准。

最新完成：[69基于模型假设的新切入点检索](research/69_基于模型假设的新切入点检索.md)。按用户授权开放备选探索，保留61—68号主线与历史结果；本轮只检索、读正文/公开工件及作条件推导，没有运行实验或修改模型、程序、输入。深入核查6篇（含4篇旧来源），新增筛读去重至多8篇及1项官方说明，未扩大成全面综述。

保留两个条件性候选：①BIDENT v2明确承认并发能量采用solo整包功率近似，优先区分公共基准去重、已有争用时长与活动功率交互；②CARIn目标design选择不依赖当前design，审查驻留/准备状态是否改变转换价值。两者均没有匹配平台的完整决策损失证据；温度—能效关系仍需相容节点注热数据，不能把整包功率任意分入CPU/NPU。HaX并发/交接、CARIn运行时补救、Phoenix低开销与完整后缀等强替代保留。

BIDENT已更新至2026-09-21的v2，采用其限定保证；HaX作者仓库有部分时长/交接数据，但演示脚本的部分数组为dummy。HeteroInfer及PowerBench相关材料已在15号审过，本次仅复核，不作新发现。没有候选达到更换主线或宣称新算法的依据；缺的是配套数据，不是可读论文，目前无需用户下载全文。

唯一下一步：对候选一做一次“基准去重后，并发代价何时改变能量排序及热可行性”的条件论证，保留不变条件与pair查表＋现有联合规划足够的范围。没有匹配数据时只作符号/L3结论；不冻结数值、不运行扫描、不同时推进CARIn，也不自动换题。以下68号及更早“下一步”均按历史保留。

最新完成：[68工程级MILP参照实现与冻结对照](research/68_工程级MILP参照实现与冻结对照.md)。R2023b intlinprog许可与回调已验证，Stage—模式—启动格点MILP和完整连续热复核已实现；53号原8主例＋2校验，与原no_repair共20次独立调用，全部在各自60 s内完成。没有新增案例、热切面、修复、对称剪枝或研究重跑。

两方主例均8/8安全、逐项能量相同：低功率D6/D10为38/37.125 mJ，高功率为44/42.625 mJ；并列校验均42.625 mJ。MILP两项高功率紧期限更快，no_repair其余6项主例更快，仅为本次单次计时。MILP可行输入均一轮、一个不同安全候选、0热排除，求解器报告根节点终止；不能据此主张困难热搜索或热排除开销上的优势。

no_repair在9项可行输入独立证最优；MILP在4项宽期限主例及并列校验U=L₀独立证最优，4项紧期限只记内部收敛＋安全见证。D4中no_repair独立证网格不可行，MILP仅报告无解。认证差距、共同L₀差距与内部gap分列，证据等级差异不当速度优势。

正式前124项预检通过，18份安全输出独立复核通过，93项登记历史哈希未变，no_repair的10项能量／状态与64号一致。正式求解后修复导出容器及回调诊断计时器，失败和原记录保留；当前代码125项预检通过。5项MILP原solver_inclusive分项计时无效，预算／总墙钟／首解不受影响；另用原时间戳给出调用区间，不补造内部成本或重跑案例。

唯一下一步：返回第四章正文，收敛方法贡献与实验结论。可以写同预算条件性有效性、排序消融及可信界管理；不能写普遍优于MILP、新增节能或困难热搜索优势。不继续认证、调参、扩规模或增加算法组件。以下67号及更早“下一步”作为历史保留。

最新完成：[67有限认证接口审查与工程级参照准入](research/67_有限认证接口审查与工程级参照准入.md)。正式接受“独立复核安全上界U＋独立Stage下界L₀＋solver-reported bound”作为第四章工程级通用参照。独立LP验证是可选增强，不是准入前提；完整MILP认证支线到此结束，不再阻挡实现推进。

格值结论：0.25 ms有助于准确表达时间边界，0.0625 mJ可在已有可靠界后作能量格值加强；未知误差下，向下取整内部界仍不保证有效，不设置无依据的保险量。LP结论：完整域放松的已核验对偶／盒约束残差可以给独立下界，但不必认证最终MILP lowerbound；单节点证书不覆盖整棵整数树。未取得可直接使用的完整整数证明接口，按约定停止追索。

同问题、同启动域、同连续热安全接纳和每例每方法60 s不变。独立认证界与内部界、无解证明与solver-reported无解分别记录；统一复核后可以比较安全解质量与时间，不能把证据等级差异单独当效率优势。U=L₀可独立证明最优；其余数值收敛不自动升级。67号只做资料与代数审查，未编程或运行实验。

唯一下一步：制定intlinprog工程参照的实现与预检任务，默认采用U＋L₀＋内部报告，不强制LP认证，不再延长MILP认证审查；不改no_repair、不换求解器、不扩案例或算法组件。以下66号及更早“下一步”均按历史保留，以本次准入口径为准。

最新完成：[66通用精确参照表达能力与保证审查](research/66_通用精确参照表达能力与保证审查.md)。仅审查R2023b intlinprog＋有限网格二元编码＋外层连续热检查。Stage—模式—起点选项及依赖／冲突线性约束与原网格无热合法域双向对应，覆盖非整数结束、共享频率域、全部映射与等待；没有安装、编程或运行求解器／案例。

热安全有可行路径：RC叠加给出固定时刻仿射温度，完整候选用64号连续峰温包络复核；已证违规安排可用整数完整赋值约束仅排除该时间表。同配置其他安排保留，未分辨保留原域或单列Z。固定时刻热切面可作增强，但需要认证系数，当前基础路线不依赖它。

结论为“数学表达可行，但保证接口未闭合”。R2023b有内部lowerbound与事件停止接口，已查输出／可读包装没有提供整个MILP搜索的可独立核验误差证书。安全上界和独立Stage下界L0仍有效，U=L0时可独立证明值最优；内部浮点下界、gap或无解退出状态不能未经补证就升级为64号相同等级的认证结论。该判断不表示求解器错误，也不否定一般数值MILP比较。

唯一下一步：仅审查该路线“数值下界／排除结果→可独立核查证据”的桥接，明确认证与退回界规则；不启动性能比较、不改no_repair、不扩案例或切换求解器。许可及实际回调行为尚未运行验证，留到实现准入。以下65号及更早“下一步”按历史保留。

最新完成：[65第四章主方法收敛与对照需求](research/65_第四章主方法收敛与对照需求.md)。第四章主版本固定为64号no_repair，描述性名称“配置能量下界引导的热安全有界搜索”。保留模式→冲突方向→网格起点分支、能量界、无热必要条件、完整连续热评价、组合候选排序及覆盖／未决管理。单步热修复降为可选扩展，full、simple_order、bare的历史定义与结果不改。

选择依据是简洁性和现有覆盖结果：no_repair与full主例均8/8安全最优、节点均9556，完整版未触发修复，不能从两者单次耗时差推断修复开销。no_repair与bare可隔离组合排序作用；原全库后缀基线混有候选生成与代表覆盖差异，原热参考还承担完整最优配置集合任务。保留紧期限旧基线更快、四新版本能量相同及修复只有条件性正例的结果。

当前可写方法实现、可信证据管理和L3冻结案例的条件性有效性，尚不能主张结构利用带来普适算法效率优势。65号完成主流程、输入输出、规则与保证、保守贡献表述、第四章小节及等能力对照任务卡。本轮只审查文档、代码与保存结果，没有程序修改、新实验或检索。

唯一下一步：核查一个通用精确求解参照能否满足同合法模式、启动域、连续热约束、信息和预算的任务卡，只要求安全见证、有效界与最优值状态，不要求列全并列配置。先核清表达、热保证和计费缺口，不安装求解器、不启动实验、不同时展开多个参照。以下64号及更早“下一步”均按历史保留。

最新完成：[64有界搜索实现与冻结案例对照](research/64_有界搜索实现与冻结案例对照.md)。独立实现63号三层搜索、精确格值能量界、保守连续热包络、有限修复及中断覆盖；MATLAB R2023b完成53号8主例＋2校验、7方法共70次调用，各例各方法独立60 s。原输入、程序与历史结果未变，无新增参数扫描。

四个新版本在8项主例全部取得合法热安全最优值：低功率D6/D10为38/37.125 mJ，高功率D6/D10为44/42.625 mJ，冷热相同。能量并列校验四版均42.625 mJ；4 ms校验均证无热不可行。原完整后缀基线4项紧期限达到参考，4项宽期限超时；三种旧方法含并列校验共15次枚举超时，未改写为方法理论失败。热参考复现104→80配置收缩且44 mJ不变。

消融显示：完整排序减少本组节点，但耗时优势有条件；完整版8项均首个探测安全，修复未触发。简化排序的高功率紧期限热态，单步修复使搜索热评价由7次降至2次、弹出节点4017→3546，能量仍44 mJ。没有新增能耗收益，不据全库实现超时认定普适算法加速或新颖性。

101项预检、184项输出独立复核及40项保存界核对均通过；实施前登记的1,682个历史研究文件哈希未变。连续热认证包装限定于冻结对称RC，启动域仍1 ms；新方法默认不列全并列最优配置。计算调用时间与预算外检查点序列化时间分开，单次运行不作统计显著性推断。

唯一下一步：据64号收缩并固化第四章方法与贡献表述，保留有界搜索主体、条件性排序收益及可选修复；不追加调参寻找优势，不自动扩规模、找新机制或恢复56号。以下63号及更早“下一步”按历史保留。

最新完成：[63第四章有界搜索与启发式协调规则](research/63_第四章有界搜索与启发式协调规则.md)。固定“模式配置→冲突方向→网格起点”的有界搜索，队列按有效能量下界、乐观完成时间之和、已固定项数和生成编号排序；时长／结束不取整，温度仍连续评价。未生成新案例、未写实验程序或运行测试。

每个完整方向先评价最早完整安排；明确超温时，按违规峰点的Stage历史温升贡献作一轮独立单步延迟，并传播必要后继延迟。失败或未分辨后保留全部时刻搜索，不把修复失败当配置排除。可靠排除仅来自无热必要条件、固定承诺热下界违规及有效能量界；已有安全配置可停止等能时序搜索，但不称其他时序无解。不启用一般模式支配或CPU标签剪枝。

明确待查、正在处理、完整叶子未分辨的覆盖责任，父节点在子分支全部就绪前保留；完整安全见证、上下界、最优值、网格不可行、集合／数值／预算状态分别输出。数值区间下另保留已关闭安全配置的能量下界，不能把向上舍入的安全上界当全域下界。修复／排序是启发式，覆盖与排除有条件证明，方法收益尚待验证；原53／55号强基线规则不改。

唯一下一步：审查63号规则的覆盖正确性与方法差异，确定预检和公平对照后再进入实现；不找新机制、不扫描热参数、不自动恢复56号改造。以下62号及更早“下一步”均按历史保留。

最新完成：[62结构性求解困难与第四章任务定位](research/62_结构性求解困难与第四章任务定位.md)。仅数学推导、既有方法记录和s55／thv代码静态审查，无新实验、输入或程序修改。固定完整配置及全部资源／同域异频冲突方向后，证明有向环排除和连续／网格最早开始传播给出无热期限可行性的充要判定；其结论不包含热可行性，也不能用一个方向失败排除整个配置。

明确剩余关系：固定方向仍有等待／重叠选择，最早安排超温不证明该方向无热安全安排。给出部分配置能量下界、上界与最优值／最优集合的不同停止条件；以被动RC正性证明逐点注热及入口不增的温度比较，以及保持单元、注热位置和不增加频率冲突的固定起点替换充分条件。该支配条件对53号H/L和CPU/NPU选择不直接产生删项，不承诺剪枝有效或加速。

第四章任务收敛为“利用配置能量与时序可行性分离，组织低能量配置的安全时序寻找及有依据的排除”。相同预算下完整热安全解质量作为首要待验证指标，成本辅助、全部计费；证明能力是结果可信性要求，不预承诺全局精确。保留每初始动作一个最佳完整后缀强基线及同域热参考，Zhou／F-DTM已有联合与前瞻能力不削弱。结构推导不是已测计算瓶颈、已证方法损失或算法创新。

唯一下一步：围绕62号任务卡细化第四章候选、完整时序、冲突反馈及停止／界输出规则，区分可靠排除和启发式选择；不自动恢复56号实现优化，不追加参数扫描，不重复60号响应核验。以下61号及更早“下一步”均按历史保留。

最新完成：[61第三章正式模型与适用边界](research/61_第三章正式模型与适用边界.md)。正式固定有限已知请求DAG、固定CPU执行单元与固定服务NPU、Stage相关合法模式表，以及模式／启动时刻的联合决策。逐项表达依赖、单元互斥、请求期限、共享频率域及完整窗口连续温度约束；一般模型采用连续启动域，网格是显式受限版本，旧1 ms最优／排除结论不自动外推。

在响应不随并发或温度改变、功率可加、恒定基准与固定窗口、零额外开销的边界下，证明E(m)=P_base W+ΣQ_i d_i，并等价为在具有完整热安全时序的配置上最小化能耗。给出固定配置等待能量不变、单时间表失败不排除配置、最优集合收缩不必提高能量及独立阶段下界四项性质。CPU聚合空闲只计一次，外部公共功率不注入节点；聚合热节点不支持按核热点迁移结论。

60号响应差异与55号热配置收缩分列举证，仍是L3条件性依据，不认定建模新颖性或算法贡献。61号只更新文档，没有新实验、代码或冻结输入变更，没有指定MILP／求解器。唯一下一步：围绕正式模型审查结构性求解困难与可利用性质，确定第四章的具体任务；不自动恢复56号枚举优化，不再重复证明已核实的响应关系。以下60号及更早“下一步”均按历史保留。

最新完成：[60四Stage响应模型解析证书独立核验](research/60_四Stage响应模型解析证书独立核验.md)。MATLAB R2023b仅核验59号四个既有冷态输入，不运行枚举／规划／完整后缀基线。261项检查通过；新增独立合法性、能量及对称二节点共同／差分热模态核验，与旧连续峰温及逐段ODE交叉检查。历史输入／源码／结果均不改。

确认I反比规划共同回放与R任务相关最优：D6为38→38、44→44 mJ；D10为38→37.125、44→42.625 mJ。宽期限以逐Stage下界＋安全见证证明最优值，紧期限另核对低频排除条件。不提供完整最优配置集合，也不补写55号基线自主执行结果。高功率宽期限R更省能但CPU峰温更高（38.008570 vs 37.258995°C），仍均安全；本组不是热约束主动造成收益。

当前第三章建模动机有L3条件性决策证据及无收益条件，但真实Stage响应数据、新颖性与算法贡献仍未确立。唯一下一步：正式固定第三章的输入、变量、目标、合法域和连续热约束，区分一般模型与验证实例；之后再单独审查结构性求解困难。不追加小实验重复证明本关系，不自动恢复56号实现优化或设计第四章算法。以下59号及更早“下一步”均作历史保留。

最新完成：[59主线建模缺口与系统决策影响核查](research/59_主线建模缺口与系统决策影响核查.md)。按用户优先级，先补具体模型假设到系统决策的证据链，暂缓58号第四章规则设计。复核Zhou印刷p.4–7、Da Costa p.3及既有JOSS正文；本轮无调度搜索、热仿真、MATLAB或历史输入／程序修改。

Zhou已有任务活动差异与温度相关泄漏；本次聚焦固定c_i的反比时长。动态能量分离依赖时长与功率共同假设，仅修改响应也不必推翻其原动态功率下的低频偏好。53号Q=1+x²是另一套L3活动增量口径，因此对照称“反比缩放规划变体”，不冒称Zhou完整复现或失败。

新增解析证据：沿用53号两个10 ms冷态输入，逐Stage能量下界及手工合法安排证明R模型最优为P_low 37.125 mJ、P_high 42.625 mJ；反比I模型最优安排共同回放仍38／44 mJ。两个6 ms冷态条件保留无收益结论。这是本轮代数／可行见证证明，不是新实验结果；补充宽期限冷态最优能量证据，但未补齐55号基线执行、全部代表或最优配置集合，热态宽期限仍未决。

当前归类“仅有条件性依据”：四Stage L3对象中的决策意义已具体化，但真实Stage频率与功率数据仍缺，任务相关响应已有先例。完整模式查表＋联合规划足以表达修正，尚无新算法必要性。唯一下一步：对59号四个冷态配对的解析证书做独立验证器核验，服务第三章的模型修正与无收益条件；不扩大参数或自动恢复56号优化。以下58号及更早“下一步”按历史保留。

最新完成：[58建模依据与协调求解结构论证](research/58_建模依据与协调求解结构论证.md)。主线继续推进，用户明确允许按具体证据缺口开展实验；故事优先不等于禁止实验。56号实现改造仍不自动恢复。本轮仅整理既有证据与代数关系，无新增代码、输入或实验。

第三章的核心理由进一步明确：在固定窗口、恒定基准功耗及零额外开销下，配置决定候选能耗，完整时序决定该配置是否存在期限与热安全可行解。统一问题可写成在具有安全安排的配置上最小化能耗。最优集合收缩不必提高最低能量，单条时序违规不足以排除配置；55号104→80且44 mJ不变正是此关系的条件性支撑。

第四章据此组织候选配置、完整安排、全轨迹评价和反馈调整。方法价值尚待具体规则与公平比较兑现；完整候选后缀强基线保持，若已有代表达到无热下界则已获热最优，不制造失败动机。非线性查表不等于求解困难，更多L3实验不能代替匹配设备数据。

唯一下一步：细化第四章的候选与反馈规则，逐项说明信息、动作、保证和验证主张；第三章共同定义保持一致。已有证据足够的关系不重复实验，确有缺口时再做对应验证，不自动扩参数或重跑旧超时点。以下57号及更早“下一步”为历史记录。

最新完成：[57主线研究故事与两章核心工作构想](research/57_主线研究故事与两章核心工作构想.md)。按用户最新优先级，先把论文问题、两章工作和方法理由讲完整；56号实现改造暂停，不以先击败强基线作为构思门槛。本轮仅组织论证与章节，没有新代码、数值输入、调度／热实验或全面文献检索。

暂定题目《面向端侧推理的多核CPU–NPU温度感知高能效任务调度研究》。主线是任务相关执行模式与完整请求时序的热能效协调：局部模式提供时长／能量代价，资源与请求期限决定组合机会，完整热轨迹进一步限制安排或配置。保持固定执行单元、已知请求DAG及固定模式NPU；四Stage作为贯穿例子，不把两个请求、两档频率及旧RC数值写成一般边界，也不恢复可变核组或新增在线机制。

第三章拟完成“任务相关响应下的CPU–NPU热约束联合调度建模与分析”，形成统一问题、条件分析及共同参照；第四章拟完成“面向完整请求的配置与时序协调求解方法”，研究配置候选—完整安排—约束诊断—联合调整。两章共享目标、合法域与评价器；具体规则及质量／成本收益尚待研究，模块串接本身不认定创新，不预定MILP或算法名称。

55号已完成4主例强组合最优、4主例未决及高功率热态104→80的配置收缩全部保留；51号结构证据不改变数值L3属性。57号将模型关系、协调机制、方法质量、计算成本与适用性验证分工，旧枚举工程仅作验证工具，不列论文核心贡献。

唯一下一步：先审阅这份主线与两章工作是否自然、连贯且实质充分，再决定细化哪一章。不自动实施56号、重跑超时点、冻结新参数或用新小实验立即筛掉构想。以下56号及更早“下一步”均为历史记录，不再自动触发。

最新完成：[56枚举成本与等价精确接口审查](research/56_枚举成本与等价精确接口审查.md)。仅静态核查源码、53号冻结模式表和55号已有记录；未修改实验程序、运行MATLAB、调度搜索、热仿真或性能测试。15次超时位于枚举阶段已有证据，但没有各子环节耗时，不能认定逐叶检查、存储或排序为主要瓶颈。

本冻结表的系统能量在0.0625 mJ格上，最大47 mJ；不同格间距远大于比较容差，故整数格的层先后与原固定锚点分层等价。初始动作语法上界13，实际合法动作仍需完整后缀判定。完整遍历后仅保存每动作最佳代表、全局最优层及配置集合，可以替代无热／基线的全库驻留与排序；必须保留完成时间和规范键原计算口径，不能把部分摘要当精确规划。尚未实现或证明60 s内完成。

热参考不能缩减为每配置一个无热代表；等待／重排仍需覆盖，安全见证、配置排除、最优值与集合完整性分别举证。三方法仍独立60 s，不免费共享候选。55号四项主例最优、四项主例未决及高功率热态104→80配置收缩不变，H52没有新结论。

唯一下一步：制定“流式无热精确摘要＋热参考配置存在性接口”的等价实现与预检任务书，优先保留MATLAB、既有有限域遍历与独立检查；按动作精确查询仅保留接口，不同时启动外部求解器路线。不自动重跑超时点、不扩参数、不将实现优化视为论文算法贡献。以下55号及更早状态作为历史保留。

最新完成：[55四Stage任务首轮验证](research/55_四Stage任务首轮验证.md)。已实现run_stage55独立入口及八Stage合法性、有限域枚举、动态设备能耗／连续热评价、单初始动作完整后缀基线与同域热参考；MATLAB R2023b运行53号8主例＋2校验，三方法独立预算，共30次调用，不改参数／网格／窗口。

4项6 ms主案例中基线完整热安全并达到参考：P_low为38 mJ，P_high为44 mJ。P_high热态首选代表CPU峰温80.103114°C；第二代表调整A.S1为NPU、B.S0等待及后续分配／时序，峰温78.698026／78.401247°C，能量仍44 mJ。无热最优配置104个，热态保留80、排除24（含全部16个双S1均CPU配置）；保留CPU标签，不能当异构映射收益或全部原配置失效，不能说最低能耗提高。其余已完成主例最优集合不缩小。

4项10 ms主案例及并列校验在三方法中均于完整枚举阶段60 s超时，共15次，未进入热比较；H52在这些案例未决，不构成基线失败。4 ms校验由5 ms链下界证无热不可行。没有重跑超时点、扩预算或继续调参，耗时不作为论文新算法必要性证据。

正式运行前65项预检通过；全部方法结果已保存后导出结构体初始化失败，保留失败／源码快照，仅修复导出与增加回归。修复后66项预检及57项事后复核通过，从原results.mat后处理，研究方法重跑0次、原数值检查点未改、旧62份MATLAB源码未改。完整CSV／图表及审计见55号链接；计算目录frozen_20260925_173727_619，后处理postprocess_20260925_175539_529。

本轮结束。唯一建议下一步：先审查完整枚举的实现成本及能否用等价精确接口取得同规则的每动作代表和参考证据，处理未决而非追加案例寻找失败；不自动实施新的求解算法或重跑。本轮仍L3条件性验证，不是Lite0平台性能复现。以下54号及更早记录按历史保留。

最新完成：[54四Stage实现接口与预检任务书](research/54_四Stage实现接口与预检任务书.md)。静态核查旧安排库、合法性检查、连续热包装及47号基线／参考；没有写实验程序、运行预检或执行53号案例。新实现须按八Stage显式依赖、实际选中设备和S3完成时间处理；thv_build／thv_step可条件性复用，旧固定CPU/NPU行号包装不能直接使用。

确定首版有限域完整枚举及独立小夹具覆盖核对，保留53号全部模式、等待、控制域和每初始动作一完整代表规则。特别明确：枚举未完的最小已见无热能量是上界，不是下界；代表只有在覆盖／排序完整后才可称最佳；热参考的见证、最优能量、完整最优配置集合和排除状态分别输出。每例每方法独立60 s，超时或资源不足保持未决，不改输入补救。

54号列出字段接口、参考覆盖、能量／注热、连续峰值、动作键、容差排序、上下界与中断等预检要求；它们尚未运行。唯一下一步为实现独立run_stage55入口及预检，通过后运行53号固定8主例＋2校验，保存结果与预算状态。当前未实现该入口，H52仍无新结果；不追加参数、规模或新算法。以下53号及更早记录按历史保留。

最新完成：[53四Stage任务L3参数冻结与比较协议](research/53_四Stage任务L3参数冻结与比较协议.md)。按用户选择显式复用旧抽象RC，冻结新四Stage模式表、8项主案例及2项独立校验。两请求共用响应；S1 NPU固定1 ms，主包增量1/4 W，配对期限6/10 ms、入口30/78°C；并列校验为3.75 W，无热不可行校验期限4 ms。CPU参考时长1/2/2/1 ms、α=1/0.5/1/0.25，Q=1+x²，x=0.5/1；数值均L3，未升级为Lite0平台测量。

输入／规则及SHA256保存在[53冻结包](research/stage53_design/README.md)。窗口20 ms、启动网格1 ms、每例每方法60 s及数值容差已冻结；保留52号全部合法模式、每初始动作一条完整无热代表、全轨迹热复核的能力与覆盖边界。没有运行调度、热仿真、MATLAB或推理，没有修改旧实验代码。

75项静态检查通过，1,029项历史文件未变；快照中的03证据记录另按计划同步。最快隔离时延5 ms、CPU最快6 ms；4 ms校验已由链下界证明无热不可行。RC衰减率20/40 s⁻¹、空闲平衡29.5/30.5°C；冷态所有满足期限的完整合法安排在0–20 ms的温度有44.682809°C充分上界。该界不是实际峰温、算法结果或运行时保证；热态和H52仍未验证。102,400为不含启动时间、未去非法组合的配置上界，不是求解瓶颈证据。

唯一下一步：单独制定四Stage实现与预检任务，适配安排生成、动态设备能耗／注热、完整候选后缀基线及同域参考；先检查合法性和参考覆盖，再运行冻结案例。当前不自动执行、不扩参数、不据结果调参。以下52号及更早“待冻结”等叙述保留为历史状态。

最新完成：[52四Stage输入契约与验证主张](research/52_四Stage任务输入契约与验证主张.md)。固定两个同模型请求、各四Stage，两个对称且占核不重叠的固定CPU单元共享两档频率域，NPU固定单服务模式；S1可CPU／NPU，其余仅CPU。相同Stage跨请求、同频跨CPU共用响应；结构源于51号，资源展开及所有时长／功率／热数值仍L3。首版明确零额外交接／切换开销，不声称设备复现。

已定义字段级输入、动态设备能量／注热、S3完成时间及完整配置输出；W、启动网格、期限、RC、数值容差和预算均待下轮冻结，没有可运行实例。静态核查确认旧代码只支持4个Stage和固定NPU后继：cv_energy总积分思路可保留，但分项按前两CPU／后两NPU；c44_thermal同样固定注热位置。新接口须按实际选中单元归类，未修改旧源码。

H52仅问“允许全部合法模式的联合无热规划＋完整候选后缀热复核，能否达到同域热参考”。保留47号每初始动作一条最佳无热后缀的能力与局限：库含全部模式不等于热复核覆盖全部S1映射；代表耗尽不能判无解。候选排序、等待、完整热复核、能耗界和未决判定已明确，未设计新算法。

唯一下一步：冻结一组参数自洽、覆盖明确条件的L3输入及比较规则；事先确定数值与预算，不据结果调参。当前不运行仿真、不扩文献／图6补证、不恢复可变核组。以下51号及更早状态按历史保留。

最新完成：[51模型分区证据补全](research/51_模型分区证据补全与研究数据边界.md)。找到作者PR #226（2022-12创建、2023-01合并）的EfficientDet-Lite0分区／支持日志；固定头提交`5af78b1…`的模型blob与50号本地文件一致。作者报告四组算子0、1–65、66–265、266；CPU均支持，指定NPU仅支持1–65。静态张量检查确认四Stage链和267算子恰好覆盖一次，选择NPU时为CPU→NPU→CPU→CPU。PR明确NNAPI版本与旧Band不同，不能冒称图6复现；记录属于分区／准备检查，不是完整推理性能测量。

唯一代表对象改为这个可追溯的后续Lite0工件，不再阻塞于图6身份。正式采用“真实模型＋作者报告支持＋静态依赖核验，数值模式表／热平台仍L3”。PR测试为3线程BIG／4线程LITTLE的固定worker，不能当44号两对称单核数据，也不恢复可变核组。频率响应、功率、RC、独占核与完整执行测量仍缺，未取得L1／L2性能参数包。

本条补证支线结束。唯一下一步：制定四Stage对象的条件性输入契约及一项主张，核清固定CPU单元、频率域和S1可替代CPU／NPU模式；再判断完整联合规划＋候选后缀热复核是否足够。先不运行实验、不沿用旧数字凑新案例、不继续索求图6记录。无需新全文；本轮未运行推理／MATLAB，历史材料不变。以下50号及更早状态为历史记录，其“继续补图6”不再是当前任务。

最新完成：[50端侧代表性任务与模式数据边界](research/50_端侧代表性任务与模式数据边界.md)。已锁定Band论文归档`f5e1655…`与当前补充快照`8600d49…`，核对图6、线程／亲和性、设备支持检测、profile计量及SLO接口。图6有EfficientDet的NPU→CPU回退和释放NPU依据，但没有对应模型文件与算子分区；不能等同Distream的Lite2或当前仓库的Lite0。当前Lite0文件已做静态检查（320×320、UINT8输入），不等于论文实验模型或设备分区。MobileNetV1备用也未补齐图示—工件—支持记录的对应关系。

本轮判定：暂不能选定可复核的模型级任务，只保留EfficientDet回退流程作为唯一补证对象及执行结构参考。没有取得目标Stage多频点时长、活动／空闲功率或RC，不能形成部分匹配参数包。单线程BIG worker不等于固定独占物理核；profile接口不等于公开测量表。论文SLO为最快处理器隔离p99×倍率，归档默认helper为最大移动平均profile×倍率，两者分开记录，不推断论文实验配置错误。

唯一建议下一步：补齐图6EfficientDet“模型身份—设备分区对应记录”，含模型SHA／输入与同后端的委托／回退算子、边界张量。目前未找到该包的精确公开下载地址，已有全文无需重下；单独下载当前Lite0或通用MobileNet包不能补齐。缺口保留，不自动启动仿真、移植零散功率或扩展文献方向。本轮仅阅读和静态文件核验，历史实验与参数不变。以下49号及更早状态为历史记录。

最新完成：[49任务相关模式表与Zhou排序依据审查](research/49_任务相关模式表与Zhou排序依据适用性审查.md)。只核查原文和推导条件，没有新实验／参数。模式表表达可保留；原动态能量的“单元因子×任务因子”及统一排序不能无条件继承。不同频率响应可破坏分离，但不必改变偏好；相同α、加性行常数等不变情况已列出。交换比较须满足合法性和完整能耗边界，不把固定负载排列结论扩成任意分组全局最优保证。

原页进一步确认：Zhou算法1已有同一真实处理器各虚拟频点的合并利用率检查，不应描述成把虚拟核当独立硬件。当前44／47号参考本来不依赖其因子排序；完整模式查表＋系统评价是明确的最小适配，仍无新算法必要性证据。本项到此结束，不追加排序反例、异构参数或热扫描，47号完整后缀基线继续保留。

唯一建议下一步：沿既有Band公开材料选定一个端侧代表性任务及模式数据边界，核查固定Stage、合法CPU/NPU实现、时延／功率粒度和频率信息，交付来源表；未匹配项显式L3，不拼成真实平台。此后再决定验证范围，不立即运行新实验或全面扩充方向。目前无需为49号补下载全文。以下48号及更早状态作为历史记录。

最新完成：[48主线剩余问题与配置映射定位](research/48_主线剩余问题清单与配置映射定位.md)。本轮只核查原文、代码和已有结果，未运行实验或改变参数。主线保留固定单元上的Stage分配、合法CPU频率与完整CPU–NPU请求时序协调，不强加异构CPU或可替代CPU/NPU映射。对称CPU的整体标签交换无收益，但同单元串行与跨单元并发不等价；44／47号实际枚举分配，HH等结果字段只记录频率组合，不是完整配置集合。

Band／Kim／JOSS／Zhou已覆盖合法映射、任务响应、频率协调或热联合优化的不同部分；新增单元类型、支持集合或响应表不自动形成算法贡献。端侧匹配参数、异构单元偏好收益和实际求解瓶颈仍未获证。47号支线已结束：其完整后缀对照每个初始动作只检查一条最佳无热代表，成功不能外推一般最优保证，失败不能判定无解；后续保留这一完整预测能力的强对照。

唯一建议下一步：审查任务相关模式表能否保留Zhou §5.1–5.3的配置排序依据。本轮已核对p.5–6原页的动态能量因子分离结构；下一项区分模式可表达与排序可继承，先列适用／不变条件和简单查表替代，不构造新实验、不加异构参数、不预设新算法。若换表即可适配，接受该结论。当前无需下载新全文；可变核组、热参数扫描及规模／加速研究继续暂缓。以下47号及更早记录为历史状态。

最新完成：[47前缀热可完成性配对验证](research/47_前缀热可完成性配对验证.md)。MATLAB R2023b运行46号冻结热／冷两例，未增案例或改参。热态旧C1按原规则在0 ms先提交A，1 ms派发受阻；同域参考证明0 ms实际前缀的两条合法后缀均违规。简单完整后缀见证对照从原始输入自主生成B_CPU₂@0–4、A_CPU₁@1–9、B_NPU@4–5、A_NPU@9–14 ms，完整安全、HH／90 mJ，CPU峰温79.547397°C，达到参考。冷态两方法均AB同时0启动，13／5 ms完成，90 mJ。C1热态未完成，能耗不参与排名。

每例无热18条完整安排，热态6安全／12违规，冷态18安全；两例热最优配置和无热最优均HH、90 mJ，无未决或超时。13预检＋45事后检查通过。两次正式案例前的实施失败（嵌套JSON域解码、测试逐位比较浮点）已修复并保留记录；冻结输入、旧57份MATLAB源码及43／46号哈希不变。正式目录run_20260924_222121_128，新增入口run_prefix47。

本项按46号约定结束：局部热准入的未来可完成性缺口得到解析和执行支持，但简单完整后缀复核已解决这个构造。后续主线应保留这一更强对照，不把该失败当复杂算法必要性，也不追加参数点寻找它的新失败。仍未证明异构映射、非线性响应收益、真实设备代表性或实际求解瓶颈；可变核组／规模／加速研究不自动启动。当前无待自动执行的新实验，无需下载全文。以下46号待运行任务现已完成，冻结报告本身不回写。

最新完成：[46前缀热可完成性条件与最小对照定义](research/46_前缀热可完成性条件与最小对照定义.md)。只做解析推导与输入冻结，没有运行调度／热仿真。保留原两CPU／NPU、功率、RC、网格和窗口，一次构造CPU时长8/4 ms、NPU时长5/1 ms、期限14/6 ms，热／冷入口沿用78/30°C；全部为L3。输入先保存哈希，再作固定闭式公式的有理区间代入，没有扫描或代入后改参。

解析结论：热态AB同时0启动违规；C1按原能量／完成时间排序随后接受安全的A单独0启动，但期限迫使B在1 ms启动，5 ms CPU温度至少80.07374073°C，排除了该实际前缀全部网格后缀。B先0、A后1 ms在4 ms CPU温度至多79.54739667°C，后续进入79.9°C安全不变区域，完整安全且仍HH／90 mJ。先等1 ms也是安全替代。冷态首选AB0直接可行。这是程序规则下的解析预测，尚未通过实际策略运行复核；不改写44号全部成功。

本构造说明局部热准入不普遍保持完整热可完成性，但简单完整后缀见证复核已有解决方案，不支持为此设计复杂算法。非线性响应、异构映射和NPU发热特有机制均未因此获证：本例α=1，直接超温源于双CPU重叠，NPU后缀影响评分与期限。唯一下一步为实施冻结的热／冷配对，核对C1、简单完整后缀见证和同域热参考；预期18条带核标签无热安排、唯一HH和90 mJ，输入及规则见prefix46_design。若吻合便结束这一项，不再追加点找更强失败。可变核组、求解加速与规模实验继续暂缓。目前无需下载全文。以下45号及更早下一步按历史记录保留。

最新完成：[45主线问题边界与求解任务论证](research/45_主线问题边界与求解任务论证.md)。本轮仅核查代码、原文和44号已保存结果，无新实验／参数修改。C1应准确描述为“精确无热联合规划＋局部热准入”：每版先生成全部合法网格安排，派发时按前缀筛选，并非轻量贪心，也不是每步重生成全库。其接受动作保留无热可完成后缀并使已提交轨迹安全，但未检查完整热安全后缀是否仍存在。44号10项全部成功保持不变，实际所经前缀均有最终最优结果作为续接见证，没有新发现的失败。

45号在固定被动RC／非负活动增量下推导：已提交轨迹是完整续接温度的逐时刻下界；明确违规可排除该动作，安全下界本身不能证明未来热可完成。F-DTM已有未来期限／热预测和束搜索，Zhou已有联合热能耗优化，不把“加前瞻”称为新贡献。枚举与重复筛选有潜在成本，尚无本题实际瓶颈证据，暂不转向求解加速。

唯一建议下一步：按45号H45完成“前缀热可完成性”的条件论证与一项对照输入定义，保留完整后缀复核、等待／重排和未启动配置重选等简单办法；进入实验前再冻结相容输入、规则与预算。仅一条后缀超温不能判定动作无安全续接，超时／未分辨不得作反例。当前无新实验自动排期，不扩大44号规模或追加调参，不恢复可变核组／40号支线，不预设新算法。目前无需补下载全文。以下44号及更早“下一步”均作历史记录。

最新完成：[44多CPU单元配置协调验证](research/44_多CPU单元配置协调首轮验证.md)。MATLAB R2023b实际运行43号冻结的8项主案例＋2项域诊断，C1全部热安全并达到同域参考能耗；C0主例6/8安全，S2热／S3热的CPU峰温80.268127°C违规。C1仅将B的CPU阶段从0–4 ms改为1–5 ms，峰温降至79.547397°C；HH配置、82 mJ及A/B完成7/10 ms均保留。热安全派发有作用，没有最优能耗变化或C1剩余差距。

域诊断单列：S2紧期限共享域要求HH、82 mJ，独立域可HL、80.25 mJ；差异在无热问题已存在，不是热算法收益。S1域分离只缩短B完成时间，能耗不变。24＋384＋192=600项检查通过；一次旧字段测试适配错误已修复并保留失败记录，正式目录run_20260924_164721_744。43号三项冻结哈希、41份旧MATLAB源码保持一致，无输入调参、新增案例或超时；本轮没有设备标定。

当前判断：42号的协调关系得到有限数值支持，但这10项仍可由强直接组合解决。本轮按计划结束，保留C1／并发参考作基线，不追加相同参数扫描或进入新算法设计。下一项若继续，应明确固定单元主线中尚未验证的具体决策关系及依据，不以加核数／任务数代替问题论证。无需补下载全文。以下43号“待执行”现已完成；可变核组仍暂缓，40号支线不恢复。

最新完成：[43多CPU单元配置协调最小验证定义](research/43_多CPU单元配置协调最小验证定义.md)。将42号落实为两个对称固定单核CPU单元＋一个固定模式NPU的L3输入，主例共享频率域，保留合法等待、同频错开并发及未启动阶段重新配置。已保存[10项设计输入](research/coordination43_design/inputs_v1.json)：8项主案例覆盖偏好不同／一致、期限紧度和NPU后缀，两项只改频率域的诊断。数值全为合成，显式选用旧二节点L3网络作为数学对照，不是双核设备标定。

冻结C0／C1强适配基线：每步按已提交前缀重新求合法无热联合配置，C1另对整个当前启动集合作连续热检查，拒绝后轮询其他配置／子集／等待；不读取热参考后缀。两版均允许改选剩余配置，不因锁死初选制造差距。共同参考需覆盖新并发语义，旧单CPU最早顺序枚举不能直接沿用。本轮只有文档、输入及静态检查，无代码、仿真或算法贡献；下一阶段可按43号实现检查并执行限定10项，不追加扫描。暂不声称异构映射收益、NPU特有机制或真实硬件节能。目前无需新全文。以下为此前状态。

最新完成：[42主线问题与方法定位](research/42_固定执行单元下的主线问题与方法定位.md)。围绕41号对象收敛为“阶段配置建议与完整CPU–NPU请求安排的一致性”：任务响应给出的配置，需要放进合法频率域、多请求并发、NPU服务顺序和热轨迹共同评价。本轮用共享频率域作条件性接口例子，不把它强制为设备事实或已证创新；没有新实验、完整模型或算法。Band–Crown不再作为主线名称或方法边界，可变核组继续暂缓，40号支线不追加扫描。

定向复核Zhou 2018已有DAG映射／DVFS／热优化；新增公开JOSS 2023和Mei等2021预印本参照，前者已有共享频率协调，后者已有非线性响应与系统能耗折中。因此不能把这些组件本身称为新意。具体近邻差异、控制规则适配和无收益条件见42号。下一项先冻结一个最小任务—固定单元—控制域—响应表及合法直接组合规则，检验其与共同参考是否存在剩余差距；不直接设计第二章算法。端侧配套参数仍缺，可明确采用L3。当前无需补下载全文。以下为此前研究状态，旧“下一步”以本段为准。

当前主线对象已明确：[41固定执行单元边界](research/41_主线研究对象与固定执行单元边界.md)。研究单台抽象多核CPU–NPU端侧设备上的多请求推理：每个Stage选择一个合法执行单元，CPU单元规模与占核集合预先固定且起步互不重叠，多个Stage可跨单元并发；协调映射、合法CPU频率和时序，在期限与瞬态热约束下评价系统能耗。一个执行单元可以是一核或固定多核worker，不默认等于物理单核。可变核组保留为扩展、暂不展开，Crown核组树／宽度选择不再是当前必要组成。

本轮只完成对象与边界文档，没有新实验或完整建模。35–40号CPU资源仅一个固定独占单元，两个CPU阶段串行且CPU/NPU归属预定，尚未验证多CPU单元映射／并发；其基线与结论不能未经适配外推新范围。后续先补任务—合法单元—频率域—响应数据对照及具体协调关系；平台核数、Stage库和参数仍待确认。当前无新实验自动排期，可变核组不自动恢复。下述40号支线结果继续保留。

最新完成：[40二维适用范围验证](research/40_二维适用范围分类与策略对照验证.md)。MATLAB实际运行60项冻结L3条件：36 A、4 B、20 N，无C/D/U；40项无热可行条件全部保留原唯一最优配置与能耗。P0安全最优39项，1项HH完成但峰温80.094822°C违规；P1在0 ms拒绝A、先执行B，峰温79.186639°C，全部40项安全最优，能耗仍94 mJ，无额外等待或改频。热反馈本轮有一次安全派发价值，没有节能收益或新算法缺口。

原15项单列回归，配置、能耗和两版时间表全部与历史一致；补证后由10 A／3 B／2 U变为12 A／3 B，温态HL穷尽118900条网格安排，用时44.24 s，未扩大60 s预算。31项预检查与2067项执行后检查通过，旧35–38号源码及输入未改。正式目录run_20260924_114714_075，初次启动／初始化失败记录保留。

当前判断：39号限定支线已完成，停止追加同一参数族扫描，返回主线。保留“联合无热配置＋P1热过滤派发”为合理基线；本范围未发现要求换配置或尚未解决的派发关系。多核规模选择、端侧匹配参数及更一般CPU–NPU关系仍待主线论证，不因这次结果判整个方向无价值，不自动进入增量／缓存算法。无新的待自动执行实验，目前无需新增全文。以下39号建议执行60项的记录现已完成。

最新完成：[39参数锚定与热约束分类协议](research/39_参数锚定与热约束作用分类协议.md)。本轮为适用范围支线，只做来源、纸面分类和对照协议；没有编写扫描代码、运行仿真或修改历史参数。尚无匹配的端侧阶段时长／功率／RC，保留两套L3历史抽象参数包，不称L1/L2或文献支持的设备数值范围。CPU作者Zenodo v2版本页与文件目录现已可读，CSV数据行仍未核查；下文旧“仅取得项目说明”访问状态以此为准。

36号15项按严格集合判据复核：10项A（不变区域证明）、3项B（安全与违规最优时间表共存）、2项U（冷／温HL仅A/B未分辨，89 mJ下界与配置保留已知）。分类与38号P0/P1表现分开；不能用首条安全见证证明A。建议下一项为两包×6档期限倍率×5档入口热裕度，共60项合成条件的限定验证，范围理由及同域参考要求见39号§5，尚未执行。允许N/D/U，不以出现C为目标；一次分析后返回主线，不追加调参或自动进入算法设计。目前无需补下载全文。

以下38号及更早记录为历史状态；旧“当前／下一步”不覆盖上述最新协议。

最新完成：[38直接组合验证](research/38_直接组合策略与参考见证对照验证.md)。原15项×P0/P1共30条主结果全部自主完成、热安全并达到84／89／71 mJ无热下界；两版时间表完全相同。P1共60次候选热评价、零拒绝，主案例未产生热反馈决策或能耗收益。两项非最优HH诊断中P1通过重排与1 ms CPU等待恢复安全，NPU继续运行，但不改善系统最优能耗。MATLAB R2023b实际运行，269/269检查通过；正式目录run_20260924_101336_425。此前检查变量遮蔽错误已修复并保留失败记录，研究输入不变，35/36号代码未变。

当前判断：H37在冻结范围内得到支持，直接组合已从“存在见证”推进到“策略自主找出”；主案例仅排队／期限反馈已足够。将该组合保留为基线与校验集，降低为同一组小实例另设计热配置算法的优先级，不外推为真实端侧通常如此或整个方向无价值。无待自动执行的新实验，不追加调参、不恢复旧方向、不开展增量算法。目前无需新增全文；若继续，先有具体工作负载或剩余困难依据。以下37号的待执行H37现已完成。

当前阶段：[37原因与现实适用范围审查](research/37_热验证结果的原因与现实适用范围审查.md)已完成，本轮未运行实验或修改参数。R1低频最优与R2受当前网络的安全功率区域保护；R1高频最优由同时已知、未启动请求的重排及宽裕期限保留。2.75 W只是抽象网络的充分边界。36号找到简单安全见证，不等于已验证可部署策略自主找到它。Band已有非FIFO排队、时长更新和热不可用反馈，Crown已有联合配置，F-DTM已有未来期限余量与热控制；现实系统是否通常能保住配置仍未知。

当前建议：优先保留“配置不变时寻找合法时序”的协调问题，方法缺口未决；不把翻转作为研究门槛，也不把反馈本身作为贡献。只提出H37：保留已有反馈能力的直接组合能否在原15项、同信息下自主达到已知无热下界。下一步若推进，先冻结组合语义和公平对照，再决定是否执行；本轮未实现，未新增案例。32号增量方法仍待成本证据，旧方向不恢复。无需补下载全文；CPU作者原始文件仍未核查，服务器数据也不能直接填补端侧子图参数。

以下36号结果保留，其“简单重排／等待足够”均限定为参考见证的存在性，不代表在线方法已验证：

当前阶段：已完成[36热约束下等待与配置选择验证](research/36_热约束下等待与配置选择验证.md)。MATLAB R2023b运行15项预定热案例，40/40检查通过；连续段内峰值与两档启动网格均检查。全部案例保住35号无热最优配置及84／89／71 mJ下界，没有配置或最优能耗翻转。R1高频最优热态中，A先行峰温80.773450°C，改为B先行后同一HL配置安全且仍89 mJ；断耦合对照的非最优HH可经1 ms整体等待恢复安全。热改变部分时间表，可由简单重排／等待处理；未出现F1、未发现新算法需求。全部为抽象参数，不是设备标定或窗口外安全保证。

当前下一步：本轮按预定范围停止，不加参数寻找F1、不自动扩大规模或开展连续时间排除证明。若继续，先核实际端侧负载／期限是否限制现有重排与等待余量，并与已有联合方法对照，再决定新条件；35号响应与系统补偿结论保留。32号局部重评／缓存仍待成本证据，多核规模选择、真实参数与完整Band–Crown基线仍缺。当前无需新增论文全文，旧方向不恢复，不将本轮无翻转外推为整个方向无研究价值。

papers/现有50份PDF文件，其中CoDVFS为608页论文集，不等于50篇独立论文；本轮Crown 2019另存于research证据目录。Band物理p.4–9、Crown p.2–4已目视核查，两者结构预检仍UNAVAILABLE。28号两份论文的核查边界保留。CPU原始数据与CoDVFS代码尚未完成下载/逐行核查，不将跨平台参数拼成真实CPU–NPU系统。

以下为此前阶段记录；其中“补全文”和“下一步”以本段当前状态为准。

最新推进：按导师建议完成[27 CPU/NPU非线性效率建模检索](research/27_CPU与NPU非线性效率建模检索.md)。发现ASPLOS 2025昇腾性能/功率建模主干，全文已下载至证据目录并核验关键页；另找到CPU 2025模型、NPUMeter 2026、CoDVFS近邻。**推荐优先深化任务相关频率响应与瓶颈切换，作为A的可能建模基础或独立联合调度主线；尚未选定最终模型。** CPU/NPU分别采用适用模型，不将换公式自动视为新算法；不因已有先例否决构思。下一步补CPU模型与CoDVFS正文，整理模型接口表。未运行实验，A/B章节稿保留，以下为前阶段状态。

当前阶段：**A/B章节级方案已完成，待选择主线。** 按用户要求先比较问题自然性、论证链条和实质工作量，暂不以相对前人贡献或小实验收益筛选。[A方案](research/24_A持续推理周期调度_章节级方案.md)是“周期联合优化与参考求解→利用重复结构的快速求解”；[B方案](research/25_B执行波动热安全调度_章节级方案.md)是“离线保守可行计划→在线安全回收执行余量”。推荐A，理由是范围清楚、两章衔接及MATLAB实施条件，非新颖性或收益排名；B为独立替代方案，C不展开。详见[比较与推进建议](research/26_A与B主线比较及推进建议.md)。已登记用户补齐的5份PDF并核验相关原页；未运行新实验、未修改实验代码。下一步选一条后写详细研究任务书、变量约束与方法流程，不自动开始实验。已证实创新0，最终选题未定。

最新讨论：[21师兄论文研究链条复盘](research/21_师兄论文研究链条复盘.md)完成。后续将“进入小验证”与“论文贡献成立”的门槛分开：问题、假设、模型及公平基线明确即可做小验证，不要求先证明所有简单方法失效或每个组件全新；方法结合的价值由协调适配与对照结果判断。以下暂停结论保留为既有线索状态，不把旧准入标准作为所有新问题的硬性门槛。本轮未确定新主线、未运行实验。

两份补充全文核查完成：Hailo Rev.2.0补到指定散热方案的稳态热阻和降频恢复滞回；WMDRS补清前作模型、训练和任务约束，但仍未补到实际配额执行器。**Hailo仅保留机制/参数参考，暂停当前队列候选；WMDRS/Yao配额协调线暂停。主线候选0、已证实创新0，无待执行新实验。** 详见[20全文核查与准入结论](research/20_补充全文核查与实验准入结论.md)。本轮未运行MATLAB或拟合热模型。

- 题目：多核CPU-NPU下温度感知的高能效任务调度。
- 已确认条件：无硬件，全部实验依赖MATLAB仿真；本机可用MATLAB R2023b。
- 前阶段结论：20号Hailo/WMDRS两线的自动延伸停止，缺口及旧实验结果保留；这些结论不作为本轮开放构思的统一否决门槛。当前尚无待运行新实验。
- 材料：`papers/`现有48份PDF。本轮登记新增TVM流水线2023、鲁棒调度DATE 2009/TC 2013、两层MPC 2022和NeuOS 2020；均完成文本提取与哈希登记，定向阅读不等于全篇精读。视觉核验流水线物理p.6、TC 2013物理p.4、MPC物理p.13；NeuOS本轮仅登记/提取。预检UNAVAILABLE（缺pypdf），批处理有一条未定位来源的XRef警告，不能声明结构检查通过。此前Hailo/WMDRS及其他读取清单保留；另有`main.pdf`作结构参考。见[证据§22](research/03_证据与检索记录.md)。
- 当前范围：端侧推理，可抽象为DAG；不预设早退、精度可调、独立调频或固定两阶段流水线。
- 归档参考：热约束下合法DNN子图粒度选择、热准入。均不作为待执行候选；此前恢复条件保留，但需新增证据才重启。见[09](research/09_子图粒度候选复核与降级结论.md)和[14](research/14_热准入服务器全文核查.md)。
- 旧方向状态：稳态/瞬态与等待方向暂停扩展，15个实例的差距已被主动等待消除；跨场景共享映射暂缓，不自动升级。保留旧结果和等待基线。
- 求解路线：本机R2023b的时间索引MILP确有耗时，但31例已被简单策略精确解决；余2例追加8/16种CPU配置组合仍未解决，可行性未知。不能推断所有现代求解器都慢；本轮没有新算法需求证据。Kim/Liu/RT-TAS平台适配与参数限制仍见10号。
- 暂缓：访存争用扩展；缺少同平台参数，且OPTiC、MEPHESTO、HaX-CoNN已有较强覆盖。
- 主要反证压力：RT-TAS、POD-TAS、Gao TAS、热可组合映射、Maity动态温度管理、F-DTM和热隔离服务器。不能称“首次考虑温度/瞬态/未来信息”。
- 已完成检查：`research/matlab/thermal_mechanism_check.m`运行成功；合成单节点RC例子中，初始温度改变能耗最优的可行配置。仅为机制检查，不是多核CPU-NPU验证或真实硬件结果。
- 待确认：任务类型与硬/软截止期；具体CPU-NPU平台或抽象平台范围；公开热参数和运行配置数据来源。
- 核查边界：F-DTM已核实固定EDF顺序、单内核执行、工作组比例划分、粗配置加LLC及弱耦合温峰近似。完整时延/热/功率参数库仍未取得；伪代码存在LST的min/max等表述不一致，不能把字面实现当忠实基线。解析例子说明一般耦合下可能有内部峰温，但直接求峰可修正，尚无新调度问题证据。
- 新增结构结论：HPCA 2017改变配置搜索顺序而非实际执行顺序；静态能耗/时间表可用逐阶段标签法作强基线。完整336配置数据未取得，原方法控制开销已低；目前不支持新CPU–NPU算法。
- 后续状态：19号两份补件已到位并核查，不再追加下载清单；不运行12/13/18号设计。重启需要具有独立依据的、简单反馈后仍待解释的具体决策损失，及可验证的数据或明确抽象模型；不要求所有参数实测，也不允许仅靠调参制造收益。保留17号两例未决数据，恢复该线仍需先确认可行性。不将停止结论外推为该领域无研究价值。
- 本轮排除：温度预测误差尚未证明简单反馈不足；CPU–NPU派发/回退虽有2026年实测，但缺热因果和配套参数，不作为当前MATLAB首选。Phoenix动机实验的掉帧不是其最终算法失败，IceEdge高负载失约也不能全归因于温度。
- 六项关键问题的当前结论：MILP可表达固定时间网格上的线性瞬态RC约束；Liu采用稳态有时间尺度假设和计算效率理由。实际调度机会损失与节能比例均未知；现有15 J→14 J仅为合成例子的执行能耗，不是CPU-NPU系统节能证据。见[参数、MILP与收益边界](research/04_热参数与创新成立条件.md)。

详细材料：[文献盘点](research/01_文献盘点.md)、[候选与验证方案](research/02_创新候选与最小验证.md)、[证据与检索记录](research/03_证据与检索记录.md)。

以下保留历次实验历史；旧记录中的“下一步”不代表当前执行优先级。

## 第一次2核CPU＋1个NPU实验审查

- 已审查外部`matlab_thermal_sched`实验。主实验通过独立数值核算：10898个基础合法调度，3094个稳态可行，全部瞬态采样可行；169.5→168.0 mJ，差0.885%。未重跑原MATLAB全流程。
- 当前收益来自稳态排除B1高频、瞬态允许B1高频；固定频率下能耗不随时序变化，瞬态最优有4360个并列调度。移除阶段依赖后收益不变，CPU-NPU特有决策关系仍待证。
- 对报告两条调度进行24 ms周期重放，周期峰温约58.42/58.36°C，仍低于80°C，不能直接归咎于一次冷启动。
- 下一步先寻找有依据参数范围内、热约束活跃且映射/并行关系影响可行最优配置的小实例；暂不扩大算法规模。详见[第一次实验审查](research/05_第一次实验审查.md)。

## 第二轮材料审查（实施前记录）

- 用户补充`research/matlab_thermal_sched_src/`源码与报告。已核对源码和报告，未在本次重新执行MATLAB；更新依据不等于独立复现。
- 热活跃参数（执行功率×1.6、热容×0.25）下，第08组报告：贪心B1@8低频，261.5 mJ；最优B1@13高频，258.5 mJ，其余阶段及映射相同。已有“等待—热可行频率—能耗”决策关系证据，不再停留于第一轮全部瞬态可行的状态。
- 36组中15组穷举可行：贪心9组追平、3组多耗3 mJ、3组失败；另外21组穷举不可行。第08组有208个最优方案，不能将所选B1@13当成唯一目标。
- 首次分歧检测存在等待分支错误和提前比较未来核映射的问题；ready展示错误。现有第08组具体分歧仍可直接解释。
- 下一步已收敛为不改参数的单阶段主动等待基线；必须从t=0独立生成完整调度，不能借用穷举给出的B2@18。基线尚未实现/运行。见[第二轮审查与基线定义](research/06_第二轮实验与等待基线审查.md)。

## 第三轮主动等待基线（已运行，方向现暂停扩展）

- MATLAB R2023b实跑15个预定穷举可行实例：原贪心9组追平、3组多耗3 mJ、3组失败；主动等待全部追平，均258.5 mJ；原先追平的9组无退化。同实现的零等待对照仍为9/3/3。
- 第08组独立生成A1高频@0、A2@4、B1高频@13、B2@18，峰温79.656039°C；第09组为A1高频@2、A2@6、B1高频@16、B2@21，峰温79.867724°C。17/35和18/36分别复现上述结果。
- 预测0.25 ms，最终方案与最优完成集合共同以0.005 ms采样验证，最优能耗不变；均无首次最优分歧。仍仅为合成参数、1 ms调度网格和采样温度约束下的结论。
- 修复等待分支、未来映射提前比较、ready状态和初温峰值统计；回归检查全部通过。原报告保留，新报告及源码快照在`research/matlab_thermal_sched_src/reports_waiting/run_20260920_163834/`。
- 当前判断：这批差距已被单阶段主动等待消除，暂不据此主张新联合算法的必要性。结果及限制见[实施报告](research/07_主动等待基线实施结果.md)。

**D181执行补充（2026-10-21）：** 原第4—40槽37次全部完成，worker／supervisor正常终态；与原三次合计40次，未重跑／延时。40份最终SAFE均完成原定一次post，453项终态存档核查通过；203源和旧工件保持。方法根时钟合10542.234秒、原启动至最终终态12685.815秒＜19200秒。联动相对HEFT四题更低、R3更高，第二阶段五题均有严格改善，0反馈／0全域证明；阶段结束，不自动追加批次。详见E601与p0_resume01/summary.md。

**D182（2026-10-21，本轮授权与建议分开）：** 用户要求读取最新提交并继续目标；先完成0e8a69c建议的P0／R3只读诊断及首批范围审查，不把该要求补成40次新预算。推荐的A=旧response_R、B=旧beta_1.0、C=旧requests_2、D=旧initial_78均记录为助手建议，未据新结果选参数。优先P1接口与必要预检，正式40槽仍需新预算；多副本邻域语义需另行确认。关联D178—181、E602；未更改方向、物理模型、算法或历史结果。

**D183（2026-10-21，用户明确确认P1预算）：** 用户在结构化问题中选择“确认预算，预检通过并冻结后执行”。仅response_R的R1—R5共40槽，各300秒、12000方法秒／19200日历秒，方法及种子沿P0，独立输入和初始化；前提为P1适配、必要预检和事前冻结，不从P0复用调用、claim、候选或缓存。预算不扩展到其余三类，关联D182及后续P1执行记录。


**D184（2026-10-22，用户明确下一项范围）：** 用户要求暂不启动第三批40次，先对P1/R4作只读分析，核查相对P0变化的工作点、闭合锚、阶段时间与最终安排，不修改算法；之后再考虑P2的78°C条件，P2尚无执行授权。承接D183的P1已完成状态。选定本项数据诊断，未选择调参、补跑或立即热批量；适用于已归档P0/P1证据。若拟改算法、改变模型/输入、调用求解或热评价、或执行P2，须另行说明范围并确认相应授权。K159完成记录及E604保留未决，不将内部零gap改写成独立证明。

**D185（2026-10-22，用户确认P2准备范围，未授权研究调用）：** 用户认可R4诊断揭示阶段限制、不算新节能突破，明确不立即针对R4改算法；下一步准备并预检P2，以P0原H响应为基准，仅初温50→78°C、温限80°C及其余条件不变，不叠加P1统一响应。关联D184/E604，本轮K160完成独立输入适配、153项纯预检、218源/五输入快照及29项准备核对。40×300秒、12000方法秒/19200日历秒仅助手预算提案，准备零预留/消费，尚待用户单独确认。若需要改输入、方法、安全标准、增扫温度或研究调用，须另行讨论；纯预检不升级为高初温安全/最优证明。

**D186（2026-10-22，用户明确授权P2执行）：** 用户确认P2共40次、每次300秒，方法总上限12000秒、日历19200秒；先冻结实际启动流程并通过必要预检再执行。仅将P0原H响应初温50→78°C，80°C温限及其余条件不变，不补跑、不延长，遇问题及时沟通。承接D185，K161仅新增独立执行层与预算/声明/claims，旧准备/预算/原218源不改。170项纯预检和25项冻结核对通过后执行本批；范围不扩展至P3/算法修改/温度扫描/额外反馈消融。

**D186执行补充（2026-10-22）：** P2 40次全部消费并完成、40最终SAFE/既定post通过，根时钟10395.472秒、监督日历10779.703秒，无重跑/延时；709项终态核查通过、原224源/旧工件保持。初温改变五个同一HEFT中间候选接纳，最终HEFT五题安排相同，MILP反馈0；联动仅R2低于HEFT，二阶段4/5改善，正反结果均保留。预算已结束，不默认P3或调参新授权；结果见K161完成/E606执行补充。


**D187（2026-10-22，用户确认期限组准备，不含执行预算）：** 在助手按最新d3596c8综合报告第6节评估后，用户回复“继续吧”，承接“完成beta_1.0输入包、终态适配及零研究调用预检”的下一小目标。采用原清单beta1.0，保留H/50/80/auto-L/400ms/5ms、物理模型和当前预消元联动；不叠加P1响应或P2初温，不补跑旧批。不选新增期限扫描/新初始化/方法调参。将本次无完整安全种子视为方法未得解而非模型无解，但必须先有完整存档证据；热/数值未分辨和真故障保持阻断。K162准备234源/五输入/40拟议槽，182项纯预检通过、零消费；40×300秒及12000/19200上限仍是待确认提案，不能把“继续准备”扩大为运行许可。未来多档趋势、方法域/参数变化或需要新初始化时先讨论，关联D186、E607。


**D188（2026-10-22，承接用户继续β=1.0批次）：** 上一条已明确列出正式执行40次×300秒、方法12000秒/日历19200秒及确认后冻结实际启动流程再执行，用户回复“继续吧”。本轮据此推进该具体批，记录自然语言依据，不扩大到其他条件/更多调用。K163新执行层继承K162五输入/234源，205项纯预检/240源冻结，旧准备未授权记录不改写；正式实验由唯一launcher在提交后启动。保持原H/50/80、期限1.0、auto-L/功热/合法域/科学方法，不补跑、不延期，不借历史见证。正常无U、当前期限审计失败、热未分辨和技术故障分别留档；已消费调用不因故障恢复。仅本批授权，完成或技术阻断即结束，关联D187/E608。

**D189（2026-10-22，原D188预算内的管理修正）：** 原期限批在前2槽后因取消文件内容核对产生假技术失败，独立证据链确认无数值拒绝、迟到接纳或期限违规。只修正派生分类，保留全部原件，第二槽既定post另存且不补新能耗。采用原未消费38槽独立续接，前2次不重跑，合计40次/12000方法秒、原绝对截止均不变；不将管理修复写作新授权/新科学方法。当前及未来出现其他真故障、证据不完整、日历到期或预算越界即停；源240不改、范围仍限原beta1.0/H/50/80组，关联D188/E609。

**D189执行补充（2026-10-22）：** 原2+续接14共消费16次，原批在第16槽数值一致性未决时按协议停止；原40次中24未启动，不自动挪用或恢复。15原SAFE、14post可比较，1正常无U，1保留原SAFE但数值状态冲突且未post。源248/旧两槽不变，未重跑、未改参数/容差/安全标准；原期限组没有完成40次。R1质量正例和R2相对SA负例均保留；下一步仅建议只读查冲突，修复和续接需单独明确范围，不把本次停止当模型无解或算法普遍失效。关联E609执行补充。

**D190（2026-10-22，用户确认只读排查）：** 用户明确先只读核查R2整体MILP“初始点检查通过、solver却报告无解”，保持原参数、容差与热安全，不补跑，查清后再讨论24次续接。选择原MAT/原生回执/代码传输和历史定向核对，不选新模型重建、原生重试、容差调整或恢复批次。K165排除初始点漏传/参数索引错位/明显残差漏检，定位通用数值拒绝理由过强与极窄条件双行；内部−2根因未决，未宣布修复。建议复用既有增广仅为待讨论路线，未获实施或调用授权；若需要新计算候选、热评价、原生诊断或更改表达，先单独明确范围。关联D189/E610，原16/40及24未启动保留。

**D191（2026-10-22，用户限定零调用兼容性审查）：** 用户建议先完成whole等价增广表达审查，不将技术诊断扩成大实验；明确后再判断期限剩余24次与机制实验优先级。本轮选择只读既有变换、whole生命周期及旧档案身份，未选择实际适配、原R2重建/变换、原生试跑或续批。K166结论为数学兼容但非即插即用，建议保留whole模型/完整Recorder/反馈，仅补数值投影与证据薄层；这是助手后续建议，尚未实施。若需更改物理/容差、引入新数值策略或启动研究调用，先讨论范围及预算。关联D190/E611，旧16/24状态及所有原件保持。

**D192（2026-10-22，用户授权接口实施与纯夹具）：** 用户确认“先完成整体MILP的增广接口适配和纯夹具预检”，保持原参数、合法调度域、容差和热安全，不调用求解器、不续24次。选择独立可选whole数值薄层、原完整Recorder/反馈，以及手写矩阵/fake session/可控时钟检查，不选原R2重建或转换、原生试跑、参数调整或批次续接。K167最终26项及源码绑定通过；仅formal增加可选hook，其他247旧源/原档案保持，历史run与最终run分列。后续actual whole成本/原生接纳须另定一次范围及预算；纯夹具不提供原生修复、节能或创新证明。关联D191/E612，16/24保留。

**D193（2026-10-22，用户仅授权诊断设计与准备预检）：** 用户要求针对beta_1.0__R2设计/预检一次whole增广原生技术诊断，最多一次300秒研究调用，先提交冻结协议和准确预算供确认。因此本轮仅准备，不将“最多一次”解读为已授权执行。提案为1×300方法/最多1native/实际1轮，40清理、420返回及480整项监督，0预算外热post、不重试、不续24；原物理/合法域/容差/热门保持。助手将次数收窄为1原生请求，避免多轮重启歧义，作为本次待确认配方；未改变原正式方法。K168 prepare与recipe及7项纯预检完成，pending消费0/预留0/claim null；无真实launcher验收或科学调用，独立15项核查通过。获用户明确确认后才能按此预算落实受控启动，不借旧claim或原日历配额。关联D192/E613，原16/24及旧R2未决保持。


**D194（2026-10-22，用户授权零研究调用的机制与创新性核查）：** 同时审查C12设备选择上下文机制与C17安全能量下界，严格以main正式P0原H R1—R5、AB/AC共享部署、400ms/5ms、四热节点和auto-L为准，不移植A03五节点U／1s或新模式。用户允许纯检查脚本，不允许优化求解、热积分、正式候选评价或实机；可提出新算法版本建议，修改及执行再讨论。K169查明完整边际成本上下文依赖、严格热安全翻转尚未证，并重导出强于原L0的可靠热下界；条件高OPP／DAG项不能在根部强加、不能重复收费。助手建议先讨论下界接口与安全分支剪枝纯检查，尚未成为用户确认的实施选择。关联D193/E614，K168原生诊断pending及期限16/24不变。重新审查触发条件：功热计量／入口／响应／控制策略／合法域变化，或后续将界接入实际搜索；原推导数值不自动迁移。


**D195（2026-10-22，用户确认条件下界与安全剪枝纯预检）：** 承接D194/E614，用户授权制定新界部分赋值接口，核是否排除具体条件及计算成本；原模型/参数/热安全不变，不启动优化求解/热积分，不覆盖旧结果或续24。K170助手采用两个完整松弛max以避CPU重计，未知/冲突fail-closed，设备跨副本一致而OPP逐场景，严格LB>U保留并列；新模块只standalone，不接生产。预先固定490一层模式/共享设备条件、5root及单列1个三H链，算术重复3次；与历史安全U后验比较而不借免费初解。9组最终纯预检/19项内部数学核对通过，187项超出旧界与普通期限的新增排除中66设备层兼容，尚未证明实际构模及时有U/模式开放或实际加速。助手建议下一项只读回放同次U@build与真实局部域后再决定接线，用户尚未批准新实现/执行。关联D194/E615；K168pending/16已消费24未启动保持，未来执行需重验新增源码清单。重新审查触发条件：物理/入口/共享/控制语义变更、将界用于生产删项、同次U或部分域身份变化；不把本次后验排除数量升级为算法收益。
