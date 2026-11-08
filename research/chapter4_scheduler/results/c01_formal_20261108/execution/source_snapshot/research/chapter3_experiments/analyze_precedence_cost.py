"""Static K120 option/precedence cost audit from the frozen K119 archive.

Replays single-Stage option loops, never a complete arrangement or a model.
No production module, LP/MILP solver or thermal evaluator is imported/called.
Requires numpy/scipy and the local ignored K119 request_*.mat files; a Git
checkout without those MAT archives cannot reproduce the original-row check.
Outputs must be new: the existing cumulative_precedence_audit01 is preserved.
"""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_ARCHIVE = HERE/'results/cut_pair_diagnostic01'


def analyze(archive,out):
    """Return static facts and write costs.json/csv to a nonexistent out."""
    base,out = Path(archive).resolve(),Path(out).resolve()
    base.relative_to(REPO); out.relative_to(REPO)
    if out.exists(): raise FileExistsError(out)
    invocation = base/'call_10/invocation'
    source_hashes = {}

    def track(path):
        source_hashes[path.relative_to(REPO).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()

    def read(path):
        track(path)
        return json.loads(path.read_text(encoding='utf-8'))

    instance = read(invocation/'input_instance.json')
    config = read(invocation/'input_config.json')
    result = read(invocation/'result.json')
    read(base/'declaration.json')
    for name in ('inputs.py','start_domain.py','milp.py'):
        track(base/'source_snapshot/research/chapter3_experiments'/name)
    fixed = result['shared_deployment']
    window,grid = F(instance['window_ms']),F(instance['start_grid_ms'])
    if (fixed != {'A.pre':'CPU1','A.main':'NPU0','A.post':'CPU1'}
            or result['builder_options']['prefilter_deadlines'] is not True
            or instance['schema_version'] != config['schema_version']):
        raise ValueError('Expected the frozen K119 first shared deployment and input schema')
    rows,scenes_out = [],[]
    for scene in instance['scenarios']:
        sid = scene['id']; saved = result['scenes'][sid]; meta = saved['model_summary']
        first = saved['solver_result']['rounds'][0]['request_number']
        prefix = invocation/'matlab'/f'request_{first:06d}'
        input_record = read(prefix.with_suffix('.input.json'))
        track(prefix.with_suffix('.mat'))
        mat = loadmat(prefix.with_suffix('.mat'),variable_names=['A','b','intcon'])
        A = mat['A'].tocsr(); A.sort_indices(); b = np.asarray(mat['b']).ravel()
        requests = {request['id']:request for request in scene['requests']}
        options_by_stage,stages,offset,rawcount = {},[],0,0
        # Frozen inputs.expand_options loop, applied one Stage at a time;
        # fixed-H filtering precedes it, deadline filtering follows it.
        for stage in scene['stage_instances']:
            request = requests[stage['request_id']]
            release,deadline = F(request['release_ms']),F(request['deadline_ms'])
            first_index = max(0,-((-release)//grid)); maximum_index = window//grid
            options,stage_raw = [],0
            for mode in instance['stage_modes'][stage['shared_stage_id']]:
                if stage['shared_stage_id'] in fixed and mode['unit_id'] != fixed[stage['shared_stage_id']]:
                    continue
                duration = F(mode['duration_ms'])
                last_index = min(maximum_index,(window-duration)//grid)
                if 'start_domain' in instance:
                    starts = [F(value) for value in instance['start_domain']['by_scene_stage_ms'][sid][stage['id']]]
                    indices = [start//grid for start in sorted(starts)
                               if release <= start and start+duration <= window]
                else:
                    indices = range(first_index,last_index+1)
                for index in indices:
                    start = index*grid; end = start+duration; stage_raw += 1
                    if end > deadline: continue
                    options.append({'y_zero_based':offset+len(options),
                        'y_MATLAB_one_based':offset+len(options)+1,
                        'option_id':f"{stage['id']}@{mode['unit_id']}:{mode['opp_id']}:g{index}",
                        'unit_id':mode['unit_id'],'opp_id':mode['opp_id'],
                        'start_ms':str(start),'end_ms':str(end)})
            options_by_stage[stage['id']] = options
            stages.append({'stage_id':stage['id'],'shared_stage_id':stage['shared_stage_id'],
                'before_deadline_filter':stage_raw,'retained_options':len(options),
                'y_zero_based_first':offset if options else None,
                'y_zero_based_last':offset+len(options)-1 if options else None,
                'recovered_unselected_local_options':options})
            offset += len(options); rawcount += stage_raw
        all_options = [option for values in options_by_stage.values() for option in values]
        # Existing scene events are rebuilt only to cross-check old metadata.
        # They are NOT the cumulative-row threshold set used below.
        events = sorted({F(0),window}|{F(o['start_ms']) for o in all_options}
                        |{F(o['end_ms']) for o in all_options})
        integers = np.asarray(mat['intcon'],dtype=int).ravel()
        checks = {'options_match_metadata':offset == meta['options'],
            'before_deadline_count_matches_metadata':rawcount == saved['preprocessing']['options_before_deadline_filter'],
            'events_match_metadata':len(events) == meta['events_per_scene'][sid],
            'intcon_is_exact_first_y_block':bool(np.array_equal(np.sort(integers),np.arange(1,offset+1))),
            'input_model_metadata_has_no_option_catalog':input_record.get('model_metadata') == {}}
        if not all(checks.values()): raise ValueError((sid,checks))
        arc_facts,kept_rows_global = [],{}
        for arc_index,(before,after) in enumerate(scene['dependencies']):
            pre,post = options_by_stage[before],options_by_stage[after]
            expected = {o['y_zero_based']:F(o['end_ms'])/1000 for o in pre}
            expected.update({o['y_zero_based']:-F(o['start_ms'])/1000 for o in post})
            expected = {i:value for i,value in expected.items() if value}
            indices = np.array(sorted(expected),dtype=int)
            coefficients = np.array([float(expected[i]) for i in indices])
            matched = []
            for row_index in np.flatnonzero(np.diff(A.indptr) == len(indices)):
                lo,hi = A.indptr[row_index:row_index+2]
                if (np.array_equal(A.indices[lo:hi],indices)
                        and np.array_equal(A.data[lo:hi],coefficients)):
                    matched.append(int(row_index))
            if len(matched) != 1:
                raise ValueError(('Original dependency row not unique',sid,before,after,matched))
            original_row = matched[0]
            # Main first-version rule: only actual successor start thresholds.
            thresholds = sorted({F(o['start_ms']) for o in post})
            raw_nnz = taut_rows = taut_nnz = dup_rows = dup_nnz = empty_pre_rows = 0
            kept,details = [],[]
            for tau in thresholds:
                pre_prefix = [o['y_zero_based'] for o in pre if F(o['end_ms']) <= tau]
                post_prefix = [o['y_zero_based'] for o in post if F(o['start_ms']) <= tau]
                if not post_prefix: raise ValueError('Successor threshold must have a nonempty prefix')
                nnz = len(pre_prefix)+len(post_prefix); raw_nnz += nnz
                key = tuple(sorted([(i,-1) for i in pre_prefix]+[(i,1) for i in post_prefix]))
                if pre and len(pre_prefix) == len(pre):
                    state = 'TAUTOLOGY_FULL_NONEMPTY_PREDECESSOR_PREFIX'
                    taut_rows += 1; taut_nnz += nnz
                elif key in kept_rows_global:
                    state = 'EXACT_DUPLICATE_COEFFICIENT_ROW'
                    dup_rows += 1; dup_nnz += nnz
                else:
                    state = 'KEEP'; kept_rows_global[key] = (arc_index,str(tau)); kept.append((tau,nnz))
                    if not pre_prefix: empty_pre_rows += 1
                details.append({'tau_ms':str(tau),'predecessor_prefix_size':len(pre_prefix),
                    'successor_prefix_size':len(post_prefix),'raw_nnz':nnz,'decision':state})
            record = {'scene_id':sid,'arc_index':arc_index,'before':before,'after':after,
                'predecessor_options':len(pre),'successor_options':len(post),'original_expected_rows':1,
                'original_expected_nnz':len(expected),'original_MAT_A_row_zero_based':original_row,
                'original_MAT_A_row_one_based':original_row+1,'original_MAT_b':float(b[original_row]),
                'original_expected_exact_rhs':0,'original_nominal_coefficients_match_bitwise':True,
                'cumulative_threshold_rule':'all distinct legal successor start values, inclusive prefixes',
                'cumulative_raw_rows':len(thresholds),'cumulative_raw_nnz':raw_nnz,
                'tautology_deleted_rows':taut_rows,'tautology_deleted_nnz':taut_nnz,
                'exact_duplicate_deleted_rows':dup_rows,'exact_duplicate_deleted_nnz':dup_nnz,
                'cumulative_kept_rows':len(kept),'cumulative_kept_nnz':sum(nnz for _,nnz in kept),
                'kept_empty_predecessor_prefix_rows':empty_pre_rows,
                'add_to_archived_model_rows':len(kept),'add_to_archived_model_nnz':sum(nnz for _,nnz in kept)}
            rows.append(record)
            arc_facts.append(record|{'threshold_decisions':details,
                'original_expected_coefficient_rule':'predecessor end_ms/1000, minus successor start_ms/1000; omit exact zeros',
                'original_outward_rhs_note':'Archived b includes nominal coefficient conversion allowance; exact intended rhs is zero'})
        totals = {key:sum(row[key] for row in rows if row['scene_id'] == sid) for key in (
            'original_expected_rows','original_expected_nnz','cumulative_raw_rows','cumulative_raw_nnz',
            'tautology_deleted_rows','tautology_deleted_nnz','exact_duplicate_deleted_rows',
            'exact_duplicate_deleted_nnz','cumulative_kept_rows','cumulative_kept_nnz','kept_empty_predecessor_prefix_rows')}
        totals.update(archived_model_rows=int(A.shape[0]),archived_model_nnz=int(A.nnz),
            rows_after_adding_kept_cumulative=int(A.shape[0])+totals['cumulative_kept_rows'],
            nnz_after_adding_kept_cumulative=int(A.nnz)+totals['cumulative_kept_nnz'],
            added_row_fraction=totals['cumulative_kept_rows']/A.shape[0],
            added_nnz_fraction=totals['cumulative_kept_nnz']/A.nnz)
        scenes_out.append({'scene_id':sid,'archived_request_number':first,'model_metadata':meta,
            'recovery_checks':checks,'option_count':offset,'original_event_count':len(events),
            'stages':stages,'arcs':arc_facts,'totals':totals})
    aggregate = {key:sum(scene['totals'][key] for scene in scenes_out)
                 for key in scenes_out[0]['totals'] if not key.endswith('_fraction')}
    facts = {'analysis_scope':'static option/row/nonzero counting only; no model, LP, MILP, schedule, thermal trajectory or solver execution',
        'source':'K119 frozen first shared deployment; call_10 archived first request per scene; no reference answer used',
        'shared_deployment':fixed,'source_sha256':source_hashes,
        'reproducer':{'path':Path(__file__).resolve().relative_to(REPO).as_posix(),
            'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'dependencies':'numpy/scipy; existing local ignored K119 request MAT archives required'},
        'recovery_path':{'direct_MAT_catalog_available':False,
            'reason':'request.input.model_metadata is empty; MAT has no option labels',
            'API_recipe':'single-Stage exact loop from frozen inputs.expand_options, after fixed-H mode filter and scene projection; keep end<=request_deadline; accumulate retained Stage counts in original order for y index',
            'option_order':'original Stage instance order, original retained mode order, increasing legal start-grid index',
            'variable_numbering':'option y is the first block, zero-based Python; MATLAB intcon uses index+1',
            'source_locations':{'inputs.py':'268-320','start_domain.py':'18-81','milp.py':'590-600,640-657,705-709'},
            'not_a_complete_schedule':'all recovered records are unselected local options, expanded one Stage at a time'},
        'main_cumulative_rule':{'thresholds':'only each successor Stage distinct legal start values tau',
            'inequality':'sum_{v:start_v<=tau} y_v - sum_{u:end_u<=tau} y_u <= 0',
            'units':'both prefix comparisons use exact rational ms; coefficients are exact +/-1',
            'simplify':'delete only full nonempty predecessor prefix tautologies and exactly identical coefficient rows',
            'empty_predecessor_prefix':'retain successor-prefix <= 0; never silently delete',
            'not_done':['scene-wide threshold grid','before/after breakpoint union','same-prefix dominance',
                        'transitive deletion','solver construction','runtime or speed prediction']},
        'scenes':scenes_out,'aggregate_totals':aggregate,
        'cost_interpretation':'Cumulative rows are additional to the archived expected-time row; static counts/nnz do not establish an actual bottleneck, speedup, cut efficacy or energy improvement'}
    if any(hashlib.sha256((REPO/name).read_bytes()).hexdigest() != digest for name,digest in source_hashes.items()):
        raise RuntimeError('An input archive changed during static counting')
    out.mkdir(parents=True,exist_ok=False)
    with (out/'costs.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (out/'costs.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return facts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,default=DEFAULT_ARCHIVE)
    parser.add_argument('--out',type=Path,required=True,help='new nonexistent cost directory; audit01 is preserved')
    args = parser.parse_args()
    report = analyze(args.archive,args.out)
    print(json.dumps({'out':str(args.out.resolve()),'totals':report['aggregate_totals']},ensure_ascii=False))
