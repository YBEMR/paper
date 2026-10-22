"""K166 archive/label compatibility review only; no numerical model imports."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
ROOT=REPO/'research/chapter3_experiments'
RESULTS=ROOT/'results'
SOURCES={}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(path):
    path=Path(path);SOURCES[path.relative_to(REPO).as_posix()]=sha(path)
    return path.read_text(encoding='utf-8-sig')


def read(path):return json.loads(text(path))


def field_paths(value, wanted, path='$'):
    if isinstance(value,dict):
        for key,item in value.items():
            if key in wanted:yield path+'.'+key
            yield from field_paths(item,wanted,path+'.'+key)
    elif isinstance(value,list):
        for i,item in enumerate(value):yield from field_paths(item,wanted,f'{path}[{i}]')


def main():
    if (HERE/'facts.json').exists():raise FileExistsError('Do not overwrite compatibility evidence')
    declaration=read(RESULTS/'deadline_resume01/declaration.json')
    code=['milp.py','matlab_bridge.py','formal_milp.py','diagnostic_search.py',
          'linked_method.py','augmented_method.py','augmented_payload.py']
    for name in code:text(ROOT/name)
    source_matches=all(sha(ROOT/name)==declaration['source_sha256'][(ROOT/name).relative_to(REPO).as_posix()] for name in code)
    whole=RESULTS/'deadline_resume01/calls/beta_1.0__R2/whole_milp'
    raw=read(whole/'wrapper_raw_result.json')
    checkpoint=read(whole/'initial_receipt_checkpoint.json')
    meta=read(whole/'matlab/request_000001.input.json')
    artifacts=read(RESULTS/'deadline_resume01/claims/beta_1.0__R2__whole_milp_artifact_sha256.json')
    build=[json.loads(line) for line in text(whole/'build_progress.jsonl').splitlines() if line]
    wanted={'names','row_tags','variable_names','labels','matrix_identities','augmented_transport'}
    matches={name:list(field_paths(value,wanted)) for name,value in [
        ('raw',raw),('checkpoint',checkpoint),('request_input',meta),('build_progress',build)]}
    inventory=[p.relative_to(whole).as_posix() for p in sorted(whole.rglob('*')) if p.is_file()]
    label_files=[name for name in inventory if Path(name).name in ('labels.json','mapping.json','matrix_identities.json')]
    linked=RESULTS/'deadline_resume01/calls/beta_1.0__R2/anchor_linked4'
    records=[]
    for scene,index,native_request in [(0,1,3),(1,2,4)]:
        folder=linked/f'pass_02/scene_{scene}/augmented_requests/request_{index:06d}'
        labels=read(folder/'labels.json');mapping=read(folder/'mapping.json')
        identities=read(folder/'matrix_identities.json');admission=read(folder/'admission.json')
        inp=read(linked/f'matlab/request_{native_request:06d}.input.json')
        records.append({'scene_index':scene,'native_request':native_request,
            'original_n':mapping['original_n'],'augmented_n':mapping['augmented_n'],
            'original_rows':mapping['original_inequality_rows'],
            'label_names_count':len(labels['names']),'label_row_tags_count':len(labels['row_tags']),
            'labels_sha256':sha(folder/'labels.json'),
            'physical_rows_rewritten':mapping['physical_rows_rewritten'],
            'retained_nonrepresentable_rows':len(mapping['exact_row_selection']['retained_nonrepresentable_physical_rows']),
            'new_variables':mapping['new_variables'],
            'gate_columns_all_named_w':all(labels['names'][col].startswith('w:') for col in mapping['gate_columns']),
            'all_label_lengths_and_native_dimension_match':len(labels['names'])==mapping['original_n']
                and len(labels['row_tags'])==mapping['original_inequality_rows']
                and inp['initial_point']['length']==mapping['augmented_n'],
            'matrix_identities':identities,
            'admission_check_sources':[entry.get('source') for entry in admission['numerical_checks']],
            'admission_original_augmented_link_pass':all(entry.get('accepted') is True
                and all(entry.get('report',{}).get(key) is True for key in ('accepted','link_accepted'))
                and entry['report']['original']['accepted'] is True
                and entry['report']['augmented']['accepted'] is True
                for entry in admission['numerical_checks']),
            'scope':'fixed device/local second-phase scene, not full shared-deployment two-scene whole model'})
    references={}
    for key,path in [('K132',RESULTS/'numerical_conflict_audit01/summary.md'),
        ('K132_label_provenance',RESULTS/'numerical_conflict_audit01/row_trace/summary.md'),
        ('K133',RESULTS/'augmented_native_check01/summary.md'),
        ('K134',RESULTS/'augmented_method_precheck01/summary.md')]:
        text(path);references[key]=path.relative_to(REPO).as_posix()
    checks={
        'read_sources_match_frozen248_declaration':source_matches,
        'whole_23464_and_143276':raw['model_summary']['variables']==23464 and raw['model_summary']['rows']==143276,
        'whole_no_archived_label_mapping_identity_files':not label_files,
        'selected_whole_readable_receipts_no_semantic_label_tables':not any(matches.values()),
        'whole_request_has_no_semantic_metadata':meta['model_metadata']=={},
        'linked_two_trusted_label_lengths_and_native_dimensions':all(r['all_label_lengths_and_native_dimension_match'] for r in records),
        'linked_mapping_gates_identified_by_archived_names':all(r['gate_columns_all_named_w'] for r in records),
        'linked_saved_original_augmented_link_checks_pass':all(r['admission_original_augmented_link_pass'] for r in records),
        'no_whole_semantic_reconstruction_or_transform_executed':True}
    assert all(checks.values()),checks
    facts={'protocol':'K166-whole-augmented-archive-compatibility-evidence-v1',
        'conclusion':'The existing whole R2 archive is not sufficient for direct trusted-label augmentation. Its numeric payload lacks a bound names/row_tags table, and the live adapter is wired to PartialRecorder, not the whole Recorder lifecycle.',
        'whole':{'variables':raw['model_summary']['variables'],'rows':raw['model_summary']['rows'],
            'options':raw['model_summary']['options'],'initial_point_length':meta['initial_point']['length'],
            'model_metadata':meta['model_metadata'],'readable_semantic_field_matches':matches,
            'inventory':inventory,'label_mapping_identity_files':label_files,
            'stored_numeric_MAT_sha256':artifacts.get('matlab/request_000001.mat'),
            'MAT_arrays_loaded_or_examined':False,
            'MAT_serialization_scope':'Bound source as_solver_dict/_prepare exports numerical arrays and x0, without names or row_tags; MAT binary was not parsed in this review.'},
        'linked_second_phase':records,'existing_references':references,
        'source_locators':{
            'milp.py':'Model.as_solver_dict:456-470 exports arrays only; Model owns live names/rows elsewhere',
            'matlab_bridge.py':'_prepare:195-224 and solve:607-636 serialize numbers and model_metadata',
            'formal_milp.py':'solve_formal_diagnostic creates diagnostic_search.Recorder, then exports model and calls native session',
            'augmented_method.py':'AugmentedMethodContext.prepare:226-249 needs bound PartialRecorder.model; AugmentedPartialRecorder:262 onward; AugmentedSession:394 onward',
            'augmented_payload.py':'build_augmented_payload:83 onward requires already provenance-matched labels; validate_projected_vector:215 onward checks original prefix too'},
        'checks':checks,'checks_run':len(checks),'passed':True,'source_sha256':SOURCES,
        'script_sha256':sha(Path(__file__)),
        'new_solver_calls':0,'new_model_constructions':0,'new_thermal_evaluations':0,
        'new_post_or_numeric_vector_checks':0,'transforms_executed':0,
        'old_files_modified':False,'model_or_tolerance_changed':False,
        'scope':'Paper/archive compatibility and future minimum acceptance criteria only; not proof of present root cause, transformation count, native compatibility or speedup.'}
    with (HERE/'facts.json').open('x',encoding='utf-8') as stream:json.dump(facts,stream,ensure_ascii=False,indent=2);stream.write('\n')
    report='''# K166：完整whole能否直接继承既有增广载荷

**已有R2 whole档案不能直接作可信语义增广；工具有继承基础，但缺标签来源和完整方法接入。** 本轮没有构模、加载MAT数组、变换载荷、数值向量复检、求解或热评价。

## 1．存档中实际有什么

|对象|原维数／不等式行|原生维数|可信语义与接纳证据|
|---|---:|---:|---|
|R2 whole，完整双场景与共享部署域|23464／143276|23464|有数值MAT、输入、初始点、回执及规模摘要；未保存names/row_tags绑定表、mapping或matrix_identities|
|R2 linked第二阶段AB，固定设备局部域|4086／18581|5163|完整labels、mapping、原/增广数组身份、原坐标与链接接纳|
|R2 linked第二阶段AC，固定设备局部域|4643／24257|6323|同上|

whole的Model在运行内存中有names和逐行tag，但`as_solver_dict`只导出数值数组，桥接`_prepare`也不序列化标签。当前可读raw、初始checkpoint、请求元数据与构模进度没有所需标签表；归档文件清单亦无对应标签/映射文件。本项未解析MAT二进制，以上MAT内容范围依据绑定生产序列化源码。不能从[0,1]界推断w列，也不能用linked局部标签填补whole列号。

linked只有第二阶段经增广，首阶段N1仍是原数值载荷。局部mapping的名字、行标签、维数和原生请求相符，不代表它们覆盖whole的两个场景、共享部署选择及全部物理行；维数不同不是方法效果的因果配对。

## 2．缺少的不是新公式，而是两个接口

**标签—数组同源绑定。** 既有转换明确要求调用者先证明标签与数组匹配。当前whole没有23464个变量名和143276个行标签及其数组身份，不能仅凭长度、边界或推测排序启动转换。未来若从同一次live whole导出捕获标签，须绑定同一源、输入、场景、反馈轮次和八组原数组；若要恢复旧档标签，需另行授权并证明恢复后的八数组与旧档一致，不能把这种恢复当成本轮已经完成。

**完整方法的接纳与反馈链。** K134的`AugmentedMethodContext.prepare`取的是已绑定`PartialRecorder.model`，而whole在`solve_formal_diagnostic`中直接创建`diagnostic_search.Recorder`。只把whole的session_factory换成现有AugmentedSession并不能完成接入：需要适配whole的callback/final先原坐标接纳、再完整解码与连续评价，以及全场景热反馈后的重新导出和映射绑定。不得让增广向量直接进入原维数解码器。

## 3．已有依据能继承到哪里

|已有材料|可继承|不能替代的whole检查|
|---|---|---|
|K132：单gate物理条件行的实数投影与精确b−M审查|v+w=1的代数关系、不可无损行不近似改写|当前whole语义标签、物理行结构及实际可转换范围|
|K133：存档AB的原生接纳与原前缀检查|初始点追加、回调/最终向量原坐标门、目标一致性与失败锁存经验|23464维whole的原生兼容性；旧62.960 s并非严格60 s内完成|
|K134：60项局部方法预检与混合保留行规则|逐请求mapping、无损行选取、其他行逐bit保留、反馈后重建、预算与生命周期测试类型|whole Recorder适配、双场景共享变量与全局能耗/反馈/SAFE保留生命周期|

已有代数与小域测试可以复用，不能把旧“60项通过”当作whole新增接口已经通过。需要的是范围明确的表达与接纳适配，不是改变物理模型或为当前结果补作证明。

## 4．以后技术诊断的最小验收

1. 标签与同轮原数组绑定，变量名唯一、长度准确、原坐标前缀保留；不从界或列号猜语义。所有原c/A/b/Aeq/beq/lb/ub/intcon先保存身份。
2. 仅在已标注物理行中检查唯一w gate、正M及合法类型；精确b−M可表示才改写，否则原位逐bit保留。结构歧义或零合格行按原拒绝语义处理。当前尚无whole转换行数或成本。
3. 新增变量仅为连续补变量，原整数索引、原目标和原前缀不变；消元恢复原行。数值候选仍须同时过增广行、链接和原矩阵原容差，投影后才进入whole原有合法性和连续评价。
4. 新whole专用接入应先覆盖callback/final、重复候选、错误维数/映射、目标不一致、反馈新增行、拒绝锁存、截止与已成SAFE保留；包含双场景共享变量，而非仅复制单场景fixture结果。
5. 接入、变换、元数据和接纳成本属于原单一方法时钟；native MaxTime与实际调用时长分列。以后即使返回原x0，也只说明技术接纳，不等于节能改善、当前冲突同因或全域最优。任何实际技术调用及其预算需后续另行决定。

结论：可保留whole增广适配作为后续工程候选；本轮不能直接变换旧R2，也不能宣布已修好。当前最先缺的是可信whole标签—数组绑定和whole Recorder接入方案，而不是新的温度条件或参数扫描。

出处：facts.json列出源码定位、原档案路径、标签/映射维数和各文件hash。检查仅核既有记录与结构，不运行其中模型或验证器。
'''
    with (HERE/'summary.md').open('x',encoding='utf-8') as stream:stream.write(report)
    manifest={'protocol':'K166-compatibility-evidence-manifest-v1','facts_sha256':sha(HERE/'facts.json'),
        'summary_sha256':sha(HERE/'summary.md'),'script_sha256':sha(Path(__file__)),
        'all_read_sources_unchanged':all(sha(REPO/name)==digest for name,digest in SOURCES.items()),
        'read_file_count':len(SOURCES),'checks_run':len(checks),'new_scientific_calls':0,
        'new_transforms_or_vector_checks':0,'old_files_modified':False}
    assert manifest['all_read_sources_unchanged']
    with (HERE/'manifest.json').open('x',encoding='utf-8') as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print({'passed':True,'checks':len(checks),'no_trusted_whole_label_table':True,
        'transforms_executed':0,'new_scientific_calls':0,'output':str(HERE)})


if __name__=='__main__':main()
